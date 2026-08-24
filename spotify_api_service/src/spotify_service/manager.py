"""Standalone Spotify playlist helper suitable for API deployments."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, List, Sequence
from urllib.parse import urlencode

from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)

DEFAULT_SCOPES = (
    "playlist-read-private playlist-modify-public playlist-modify-private user-read-private user-library-read".split()
)


@dataclass
class PlaylistProfile:
    """Data contract describing how to build/rotate a playlist."""

    playlist_name: str
    description: str
    public: bool = True
    curated_queries: Sequence[Any] = field(default_factory=tuple)
    rotation_queries: Sequence[Any] = field(default_factory=tuple)
    max_tracks: int | None = None


@dataclass
class PlaylistRotationResult:
    playlist_id: str
    playlist_name: str
    playlist_url: str
    track_count: int
    snapshot_id: str
    preview: Sequence[str] = field(default_factory=tuple)
    runtime_ms: int | None = None


class SpotifyPlaylistService:
    """Reusable Spotify helper that can back an AWS API."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        cache_path: Path | None = None,
        scopes: Sequence[str] | None = None,
    ) -> None:
        self.cache_path = cache_path or Path.home() / ".cache-spotify-service"
        scope_text = " ".join(scopes or DEFAULT_SCOPES)
        self._oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope_text,
            cache_path=str(self.cache_path),
        )
        self.client = _SpotifyCurlClient(self._oauth)

    def ensure_playlist(self, profile: PlaylistProfile) -> dict:
        """Return the playlist object, creating it when missing."""
        existing = self._find_playlist_by_name(profile.playlist_name)
        if existing:
            return existing
        logger.info("Creating Spotify playlist '%s'.", profile.playlist_name)
        playlist = self.client.post(
            "me/playlists",
            data={
                "name": profile.playlist_name,
                "description": profile.description,
                "public": profile.public,
            },
        )
        return playlist

    def rotate_playlist(
        self,
        profile: PlaylistProfile,
        *,
        cooldown: timedelta = timedelta(days=1),
        force: bool = False,
    ) -> PlaylistRotationResult:
        """Replace playlist tracks with the curated+rotation set."""
        playlist = self.ensure_playlist(profile)
        if not force and self._should_skip_refresh(playlist, cooldown):
            refreshed = playlist.get("description", "")
            raise RuntimeError(f"Cooldown active for '{profile.playlist_name}': {refreshed}")

        curated_ids = self._resolve_track_queries(profile.curated_queries)
        rotation_ids = self._resolve_track_queries(profile.rotation_queries)
        track_ids = self._unique_ordered(curated_ids + rotation_ids)
        if profile.max_tracks is not None:
            track_ids = track_ids[: profile.max_tracks]

        snapshot_id = self._write_playlist(
            playlist_id=playlist["id"],
            track_ids=track_ids,
            profile=profile,
            refreshed_at=datetime.now(timezone.utc),
        )
        preview = self._resolve_track_names(track_ids[:10])
        runtime_ms = self._sum_track_durations(track_ids)
        return PlaylistRotationResult(
            playlist_id=playlist["id"],
            playlist_name=profile.playlist_name,
            playlist_url=playlist["external_urls"]["spotify"],
            track_count=len(track_ids),
            snapshot_id=snapshot_id,
            preview=preview,
            runtime_ms=runtime_ms,
        )

    # --- Internals copied from the CLI implementation ---

    def _find_playlist_by_name(self, name: str) -> dict | None:
        limit = 50
        offset = 0
        while True:
            payload = self.client.get(
                "me/playlists",
                params={"limit": limit, "offset": offset},
            )
            for playlist in payload["items"]:
                if playlist["name"].lower() == name.lower():
                    return playlist
            offset += limit
            if payload["next"] is None:
                return None

    def _write_playlist(
        self,
        *,
        playlist_id: str,
        track_ids: Sequence[str],
        profile: PlaylistProfile,
        refreshed_at: datetime,
    ) -> str:
        uris = [f"spotify:track:{track_id}" for track_id in track_ids]
        response = self.client.put(
            f"playlists/{playlist_id}/items",
            data={"uris": uris[:100]},
        )
        snapshot_id = response["snapshot_id"]
        for chunk in _chunked(uris[100:], size=100):
            resp = self.client.post(
                f"playlists/{playlist_id}/items",
                data={"uris": chunk},
            )
            snapshot_id = resp["snapshot_id"]
        refreshed_on = refreshed_at.strftime("%Y-%m-%d")
        description = f"{profile.description.strip()} (Refreshed on {refreshed_on})"
        self.client.put(
            f"playlists/{playlist_id}",
            data={
                "name": profile.playlist_name,
                "description": description,
                "public": profile.public,
            },
        )
        return snapshot_id

    def _should_skip_refresh(self, playlist: dict, cooldown: timedelta) -> bool:
        description = playlist.get("description") or ""
        marker = "(Refreshed on "
        if marker not in description:
            return False
        try:
            stamp = description.split(marker)[-1].split(")")[0]
            last_refresh = datetime.strptime(stamp, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        elapsed = datetime.now(timezone.utc) - last_refresh
        return elapsed < cooldown

    def _resolve_track_queries(self, queries: Sequence[Any]) -> List[str]:
        results: List[str] = []
        for entry in queries:
            payload = {"query": entry} if isinstance(entry, str) else dict(entry)
            track_id = payload.get("id")
            if not track_id:
                query = payload.get("query")
                if not query:
                    continue
                track_id = self._search_track(query)
            if track_id:
                results.append(track_id)
        return results

    def _resolve_track_names(self, track_ids: Sequence[str]) -> List[str]:
        names: List[str] = []
        for track_id in track_ids:
            track = self.client.get(
                f"tracks/{track_id}",
                allow_failure=True,
                default=None,
            )
            if not track:
                continue
            artist = track["artists"][0]["name"]
            names.append(f"{artist} – {track['name']}")
        return names

    def _sum_track_durations(self, track_ids: Sequence[str]) -> int:
        if not track_ids:
            return 0
        durations: dict[str, int] = {}
        for chunk in _chunked(track_ids, size=50):
            payload = self.client.get(
                "tracks",
                params={"ids": ",".join(chunk)},
                allow_failure=True,
                default={"tracks": []},
            )
            for track in payload.get("tracks", []):
                if track and "id" in track:
                    duration = track.get("duration_ms")
                    if isinstance(duration, (int, float)):
                        durations[track["id"]] = int(duration)
        total = 0
        for track_id in track_ids:
            total += durations.get(track_id, 0)
        return total

    def _search_track(self, query: str) -> str | None:
        payload = self.client.get(
            "search",
            params={"q": query, "type": "track", "limit": 1},
        )
        items = payload.get("tracks", {}).get("items", [])
        if not items:
            return None
        return items[0]["id"]

    @staticmethod
    def _unique_ordered(values: Iterable[str]) -> List[str]:
        seen: set[str] = set()
        unique: List[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                unique.append(value)
        return unique


def _chunked(values: Sequence[str], *, size: int) -> Iterable[Sequence[str]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


class _SpotifyCurlClient:
    """Minimal curl-based client (matches the CLI for reliability)."""

    API_BASE = "https://api.spotify.com/v1"

    def __init__(self, oauth: SpotifyOAuth) -> None:
        self.oauth = oauth
        self._token_info: dict[str, Any] | None = None

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        allow_failure: bool = False,
        default: Any = None,
    ) -> Any:
        return self._request(
            "GET",
            path,
            params=params,
            allow_failure=allow_failure,
            default=default,
        )

    def post(self, path: str, *, data: dict[str, Any]) -> Any:
        return self._request("POST", path, data=data)

    def put(self, path: str, *, data: dict[str, Any]) -> Any:
        return self._request("PUT", path, data=data)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        allow_failure: bool = False,
        default: Any = None,
    ) -> Any:
        token = self._access_token()
        url = f"{self.API_BASE}/{path.lstrip('/')}"
        if params:
            query = urlencode(params, doseq=True)
            url = f"{url}?{query}"
        cmd = [
            "curl",
            "-sS",
            "-f",
            "-X",
            method.upper(),
            "-H",
            f"Authorization: Bearer {token}",
        ]
        if data is not None:
            body = json.dumps(data)
            cmd.extend(["-H", "Content-Type: application/json", "--data", body])
        cmd.append(url)
        backoff = 2.0
        max_attempts = 6
        attempt = 0
        while True:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                break
            message = result.stderr.strip() or result.stdout.strip()
            if "429" in message and attempt < max_attempts - 1:
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30.0)
                attempt += 1
                continue
            if allow_failure:
                logger.debug("curl %s %s failed: %s", method, path, message)
                return default
            raise RuntimeError(f"curl {method} {path} failed: {message}")
        output = result.stdout.strip()
        if not output:
            return None
        return json.loads(output)

    def _access_token(self) -> str:
        if self._token_info is None or self.oauth.is_token_expired(self._token_info):
            self._token_info = self.oauth.get_access_token(as_dict=True)
        return self._token_info["access_token"]
