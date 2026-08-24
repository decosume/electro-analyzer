"""Spotify playlist automation utilities tailored for a barber shop vibe."""

from __future__ import annotations

import json
import logging
import random
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, List, Sequence, Tuple
from urllib.parse import urlencode

from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger(__name__)

DEFAULT_SCOPES = (
    "playlist-read-private playlist-modify-public playlist-modify-private user-library-read user-read-private".split()
)
_REFRESH_PATTERN = re.compile(r"Refreshed on (\d{4}-\d{2}-\d{2})")


@dataclass
class BarberShopVibeProfile:
    """Configuration describing the playlist's tone and seed material."""

    playlist_name: str = "Fresh Fade Fridays"
    description: str = (
        "Confident soul, funk, and modern R&B for a relaxed, repeat-worthy shop vibe."
    )
    public: bool = True
    curated_queries: Sequence[str] = field(
        default_factory=lambda: [
            "Marvin Gaye Mercy Mercy Me",
            "Al Green Love and Happiness",
            "The Spinners Could It Be I'm Falling in Love",
            "Stevie Wonder Sir Duke",
            "Earth Wind & Fire Shining Star",
            "Prince Kiss",
            "Sade Sweetest Taboo",
            "Anderson .Paak Come Down",
            "H.E.R. Slide",
            "Leon Bridges Smooth Sailin'",
        ]
    )
    rotation_queries: Sequence[str] = field(
        default_factory=lambda: [
            "Common The Light",
            "GoldLink Crew",
            "Snoh Aalegra Woah",
            "Tom Misch It Runs Through Me",
            "FKJ Ylang Ylang",
            "Robert Glasper Afro Blue",
            "Bruno Mars Versace on the Floor",
            "Miguel Pineapple Skies",
        ]
    )
    seed_track_queries: Sequence[str] = field(
        default_factory=lambda: [
            "Anderson .Paak Come Down",
            "Snoh Aalegra Woah",
            "Sade Sweetest Taboo",
            "Marvin Gaye Got To Give It Up",
            "Earth Wind & Fire September",
        ]
    )
    seed_artist_queries: Sequence[str] = field(
        default_factory=lambda: [
            "Marvin Gaye",
            "Prince",
            "Stevie Wonder",
            "H.E.R.",
            "Anderson .Paak",
        ]
    )
    seed_genres: Sequence[str] = field(
        default_factory=lambda: ["neo-soul", "funk", "r-n-b", "hip-hop", "soul"]
    )
    danceability_range: tuple[float, float] = (0.55, 0.82)
    energy_range: tuple[float, float] = (0.5, 0.8)
    valence_range: tuple[float, float] = (0.45, 0.85)
    min_popularity: int = 45
    block_config: Sequence[dict[str, int]] | None = None
    max_tracks: int | None = None
    target_duration_minutes: int | None = None
    local_item_positions: Sequence[int] | None = None
    excluded_artists: Sequence[str] = field(default_factory=tuple)
    weekday_profiles: dict[str, dict[str, Any]] | None = None


@dataclass
class PlaylistRefreshResult:
    """Return payload for CLI feedback or logging."""

    playlist_id: str
    playlist_name: str
    playlist_url: str
    track_count: int
    snapshot_id: str | None = None
    skipped: bool = False
    reason: str | None = None
    preview: Sequence[str] = field(default_factory=tuple)
    runtime_ms: int | None = None


@dataclass(frozen=True)
class PlaylistItemRef:
    """Minimal playlist item metadata used to preserve local-file entries."""

    position: int
    uri: str
    is_local: bool


class BarberShopPlaylistManager:
    """Small helper around Spotipy to build and refresh a barber shop playlist."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        cache_path: Path | None = None,
        scopes: Sequence[str] | None = None,
    ) -> None:
        self.cache_path = cache_path or Path.home() / ".cache-barbershop-playlist"
        self.track_cache_path = Path.home() / ".cache-electro-track-ids.json"
        self._id_cache = self._load_id_cache()
        self._duration_cache: dict[str, int] = self._id_cache.setdefault("duration", {})
        scope_text = " ".join(scopes or DEFAULT_SCOPES)
        self._oauth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            scope=scope_text,
            cache_path=str(self.cache_path),
        )
        self.client = _SpotifyCurlClient(self._oauth)
        self.user_id: str = self.client.get("me")["id"]

    def refresh_playlist(
        self,
        profile: BarberShopVibeProfile,
        *,
        rotation_tracks: int = 12,
        rotation_seed: int | None = None,
        cooldown: timedelta = timedelta(days=3),
        dry_run: bool = False,
        force: bool = False,
        max_tracks: int | None = None,
        target_duration: timedelta | None = None,
    ) -> PlaylistRefreshResult:
        """Create (or update) the playlist while respecting a cooldown window."""
        playlist = self._get_or_create_playlist(profile)
        playlist_url = playlist["external_urls"]["spotify"]
        if not dry_run and not force and self._should_skip_refresh(playlist, cooldown):
            reason = (
                "Cooldown active; use --force or wait until the next refresh window."
            )
            logger.info(reason)
            return PlaylistRefreshResult(
                playlist_id=playlist["id"],
                playlist_name=profile.playlist_name,
                playlist_url=playlist_url,
                track_count=self._playlist_track_total(playlist),
                skipped=True,
                reason=reason,
            )

        curated_ids = self._resolve_track_queries(profile.curated_queries)
        rotation_ids = self._resolve_track_queries(profile.rotation_queries)
        selected_rotation_ids = _select_rotation_tracks(
            rotation_ids,
            limit=rotation_tracks,
            week_seed=rotation_seed,
        )
        top_pick_ids = self._pull_user_favorites(limit=5)

        track_pool = self._unique_ordered(
            curated_ids + selected_rotation_ids + top_pick_ids
        )
        track_pool = self._exclude_artists(track_pool, profile.excluded_artists)
        final_tracks = track_pool
        runtime_ms: int | None = None
        if max_tracks is not None:
            final_tracks = final_tracks[:max_tracks]
        if target_duration is not None:
            final_tracks, runtime_ms = self._limit_tracks_by_duration(
                final_tracks, target_duration
            )
        else:
            runtime_ms = self._sum_track_durations(final_tracks)
        preview = self._resolve_track_names(final_tracks[:10])

        if dry_run:
            logger.info("Dry run: resolved %s candidate tracks.", len(final_tracks))
            return PlaylistRefreshResult(
                playlist_id=playlist["id"],
                playlist_name=profile.playlist_name,
                playlist_url=playlist_url,
                track_count=len(final_tracks),
                skipped=True,
                reason="Dry run",
                preview=preview,
                runtime_ms=runtime_ms,
            )

        timestamp = datetime.now(timezone.utc)
        snapshot_id = self._write_playlist(
            playlist_id=playlist["id"],
            track_ids=final_tracks,
            profile=profile,
            refreshed_at=timestamp,
        )
        return PlaylistRefreshResult(
            playlist_id=playlist["id"],
            playlist_name=profile.playlist_name,
            playlist_url=playlist_url,
            track_count=len(final_tracks),
            snapshot_id=snapshot_id,
            preview=preview,
            runtime_ms=runtime_ms,
        )

    def _get_or_create_playlist(self, profile: BarberShopVibeProfile) -> dict:
        existing = self._find_playlist_by_name(profile.playlist_name)
        if existing:
            return existing
        logger.info("Creating playlist '%s'.", profile.playlist_name)
        playlist = self.client.post(
            "me/playlists",
            data={
                "name": profile.playlist_name,
                "public": profile.public,
                "description": profile.description,
            },
        )
        return playlist

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
        playlist_id: str,
        track_ids: Sequence[str],
        profile: BarberShopVibeProfile,
        refreshed_at: datetime,
    ) -> str:
        uris = [f"spotify:track:{track_id}" for track_id in track_ids]
        preserved_locals = self._fetch_local_playlist_items(playlist_id)
        if preserved_locals:
            target_local_positions = self._resolve_local_item_positions(
                preserved_locals,
                profile.local_item_positions,
            )
            snapshot_id = self._rewrite_playlist_preserving_locals(
                playlist_id=playlist_id,
                track_uris=uris,
                preserved_locals=target_local_positions,
            )
        else:
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

    def _fetch_playlist_items(self, playlist_id: str) -> list[PlaylistItemRef]:
        """Return ordered playlist item references, including local-file entries."""
        items: list[PlaylistItemRef] = []
        position = 0
        page = self.client.get(
            f"playlists/{playlist_id}/items",
            params={"limit": 100, "offset": 0, "fields": "items(is_local,item(uri,is_local)),next"},
        )
        while True:
            page_items = page.get("items") or []
            for item in page_items:
                track = item.get("track") or item.get("item") or {}
                uri = track.get("uri")
                if not uri:
                    continue
                items.append(
                    PlaylistItemRef(
                        position=position,
                        uri=uri,
                        is_local=bool(item.get("is_local") or track.get("is_local")),
                    )
                )
                position += 1
            next_url = page.get("next")
            if not next_url:
                break
            page = self.client.get_url(next_url)
        return items

    def _fetch_local_playlist_items(self, playlist_id: str) -> list[PlaylistItemRef]:
        """Return local-file playlist entries in their current order and positions."""
        return [item for item in self._fetch_playlist_items(playlist_id) if item.is_local]

    @staticmethod
    def _resolve_local_item_positions(
        preserved_locals: Sequence[PlaylistItemRef],
        configured_positions: Sequence[int] | None,
    ) -> list[PlaylistItemRef]:
        """Return local items with either configured or current positions."""
        if not configured_positions:
            return list(preserved_locals)
        if len(configured_positions) != len(preserved_locals):
            logger.warning(
                "Configured local item positions (%s) do not match detected locals (%s); using current positions.",
                len(configured_positions),
                len(preserved_locals),
            )
            return list(preserved_locals)
        resolved: list[PlaylistItemRef] = []
        for item, configured in zip(preserved_locals, configured_positions):
            resolved.append(
                PlaylistItemRef(
                    position=max(0, int(configured) - 1),
                    uri=item.uri,
                    is_local=item.is_local,
                )
            )
        return resolved

    def _rewrite_playlist_preserving_locals(
        self,
        *,
        playlist_id: str,
        track_uris: Sequence[str],
        preserved_locals: Sequence[PlaylistItemRef],
    ) -> str:
        """Replace non-local tracks while keeping local-file entries at their positions."""
        existing_items = self._fetch_playlist_items(playlist_id)
        removable = [item.uri for item in existing_items if not item.is_local]
        snapshot_id: str | None = None
        if removable:
            for chunk in _chunked(removable, size=100):
                response = self.client.delete(
                    f"playlists/{playlist_id}/items",
                    data={"items": [{"uri": uri} for uri in chunk]},
                )
                snapshot_id = response["snapshot_id"]

        insertion_plan = _build_insertion_plan(
            local_positions=[item.position for item in preserved_locals],
            total_track_count=len(track_uris),
        )
        inserted = 0
        for position, count in insertion_plan:
            chunk = list(track_uris[inserted : inserted + count])
            inserted += count
            if not chunk:
                continue
            for offset, uri_chunk in enumerate(_chunked(chunk, size=100)):
                response = self.client.post(
                    f"playlists/{playlist_id}/items",
                    params={"position": position + offset * 100},
                    data={"uris": list(uri_chunk)},
                )
                snapshot_id = response["snapshot_id"]
        if snapshot_id is None:
            current = self.client.get(f"playlists/{playlist_id}")
            snapshot_id = current["snapshot_id"]
        return snapshot_id

    def _should_skip_refresh(self, playlist: dict, cooldown: timedelta) -> bool:
        if self._playlist_track_total(playlist) == 0:
            return False
        description = playlist.get("description") or ""
        match = _REFRESH_PATTERN.search(description)
        if not match:
            return False
        last_refresh = datetime.strptime(match.group(1), "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
        elapsed = datetime.now(timezone.utc) - last_refresh
        return elapsed < cooldown

    def _resolve_track_queries(self, queries: Sequence[Any]) -> List[str]:
        results: List[str] = []
        cache_updated = False
        for entry in queries:
            if isinstance(entry, str):
                payload = {"query": entry}
            else:
                payload = dict(entry)
            track_id = payload.get("id")
            if not track_id:
                query = payload.get("query")
                if not query:
                    logger.warning("Skipping entry without query: %s", payload)
                    continue
                track_id = self._search_entity(query, entity="track")
                if track_id:
                    payload["id"] = track_id
            if track_id:
                duration = payload.get("duration_ms")
                if isinstance(duration, (int, float)):
                    self._duration_cache[track_id] = int(duration)
                    cache_updated = True
                results.append(track_id)
            else:
                logger.warning("Track entry '%s' returned no results.", payload.get("query"))
        if cache_updated:
            self._save_id_cache()
        return results

    def _resolve_artist_queries(self, queries: Sequence[str]) -> List[str]:
        results: List[str] = []
        for query in queries:
            artist_id = self._search_entity(query, entity="artist")
            if artist_id:
                results.append(artist_id)
            else:
                logger.warning("Artist query '%s' returned no results.", query)
        return results

    def _search_entity(self, query: str, *, entity: str) -> str | None:
        cache_key = query.strip().lower()
        cache_bucket = self._id_cache.setdefault(entity, {})
        if cache_key in cache_bucket:
            return cache_bucket[cache_key]

        retries = 8
        for attempt in range(retries):
            try:
                time.sleep(0.15)
                payload = self.client.get(
                    "search",
                    params={"q": query, "type": entity, "limit": 1},
                )
                break
            except RuntimeError as exc:
                message = str(exc)
                if "429" in message and attempt < retries - 1:
                    time.sleep(3.0)
                    continue
                raise
        data = payload[f"{entity}s"]["items"]
        if not data:
            return None
        entity_info = data[0]
        entity_id = entity_info["id"]
        cache_bucket[cache_key] = entity_id
        if entity == "track":
            duration = entity_info.get("duration_ms")
            if isinstance(duration, (int, float)):
                self._duration_cache[entity_id] = int(duration)
        self._save_id_cache()
        return entity_id

    def _recommend_tracks(
        self,
        profile: BarberShopVibeProfile,
        *,
        seed_tracks: Sequence[str],
        seed_artists: Sequence[str],
        limit: int,
    ) -> List[str]:
        if not seed_tracks and not seed_artists and not profile.seed_genres:
            return []
        logger.warning(
            "Spotify deprecated the recommendations endpoint; skipping seed-driven suggestions."
        )
        return []

    def _pull_user_favorites(self, limit: int) -> List[str]:
        payload = self.client.get(
            "me/top/tracks",
            params={"limit": limit, "time_range": "medium_term"},
            default={},
            allow_failure=True,
        )
        if not payload:
            logger.debug("Top tracks scope missing; skipping personal favorites.")
            return []
        return [track["id"] for track in payload.get("items", [])]

    def _fetch_track_metadata(self, track_ids: Sequence[str]) -> dict[str, dict[str, Any]]:
        if not track_ids:
            return {}
        metadata: dict[str, dict[str, Any]] = {}
        cache_updated = False
        for chunk in _chunked(track_ids, size=50):
            pending: list[str] = []
            for track_id in chunk:
                duration = self._duration_cache.get(track_id)
                if isinstance(duration, int):
                    metadata[track_id] = {"duration_ms": duration}
                else:
                    pending.append(track_id)
            if not pending:
                continue
            payload = self.client.get(
                "tracks",
                params={"ids": ",".join(pending)},
                allow_failure=True,
                default={"tracks": []},
            )
            tracks: list[dict[str, Any]] = []
            if isinstance(payload, dict):
                tracks = payload.get("tracks") or []
            still_missing: list[str] = []
            if tracks:
                for track in tracks:
                    if not track or "id" not in track:
                        continue
                    track_id = track["id"]
                    metadata[track_id] = track
                    duration_ms = track.get("duration_ms")
                    if isinstance(duration_ms, (int, float)):
                        self._duration_cache[track_id] = int(duration_ms)
                        cache_updated = True
            else:
                still_missing = pending
            if still_missing:
                for track_id in still_missing:
                    track = self.client.get(
                        f"tracks/{track_id}",
                        allow_failure=True,
                        default=None,
                    )
                    if track and "id" in track:
                        metadata[track["id"]] = track
                        duration_ms = track.get("duration_ms")
                        if isinstance(duration_ms, (int, float)):
                            self._duration_cache[track["id"]] = int(duration_ms)
                            cache_updated = True
        if cache_updated:
            self._save_id_cache()
        return metadata

    def _limit_tracks_by_duration(
        self, track_ids: Sequence[str], target_duration: timedelta
    ) -> tuple[List[str], int]:
        if not track_ids:
            return [], 0
        metadata = self._fetch_track_metadata(track_ids)
        target_ms = int(target_duration.total_seconds() * 1000)
        total_ms = 0
        selected: List[str] = []
        for track_id in track_ids:
            selected.append(track_id)
            info = metadata.get(track_id) or {}
            duration_ms = info.get("duration_ms")
            if isinstance(duration_ms, (int, float)):
                total_ms += int(duration_ms)
            if target_ms and total_ms >= target_ms:
                break
        if target_ms and total_ms < target_ms:
            logger.warning(
                "Target duration %.2fh not reached; playlist totals %.2fh.",
                target_ms / 3600000,
                total_ms / 3600000,
            )
        return selected, total_ms

    def _sum_track_durations(self, track_ids: Sequence[str]) -> int:
        if not track_ids:
            return 0
        metadata = self._fetch_track_metadata(track_ids)
        total_ms = 0
        for track_id in track_ids:
            info = metadata.get(track_id) or {}
            duration_ms = info.get("duration_ms")
            if isinstance(duration_ms, (int, float)):
                total_ms += int(duration_ms)
        return total_ms

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

    def _exclude_artists(
        self,
        track_ids: Sequence[str],
        excluded_artists: Sequence[str],
    ) -> List[str]:
        if not track_ids or not excluded_artists:
            return list(track_ids)
        excluded_terms = [
            artist.strip().lower()
            for artist in excluded_artists
            if artist and artist.strip()
        ]
        if not excluded_terms:
            return list(track_ids)

        metadata = self._fetch_track_metadata(track_ids)
        filtered: List[str] = []
        for track_id in track_ids:
            track = metadata.get(track_id) or {}
            artists = track.get("artists") or []
            artist_names = [
                str(artist.get("name", "")).strip().lower()
                for artist in artists
                if isinstance(artist, dict)
            ]
            if any(
                excluded in artist_name
                for excluded in excluded_terms
                for artist_name in artist_names
            ):
                continue
            filtered.append(track_id)
        return filtered

    @staticmethod
    def _unique_ordered(values: Iterable[str]) -> List[str]:
        seen: set[str] = set()
        unique: List[str] = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                unique.append(value)
        return unique

    def _load_id_cache(self) -> dict[str, dict[str, str]]:
        path = self.track_cache_path
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return {
                    "track": dict(data.get("track", {})),
                    "artist": dict(data.get("artist", {})),
                    "duration": {
                        key: int(value)
                        for key, value in (data.get("duration") or {}).items()
                        if isinstance(value, (int, float))
                    },
                }
        except FileNotFoundError:
            pass
        return {"track": {}, "artist": {}, "duration": {}}

    def _save_id_cache(self) -> None:
        try:
            self.track_cache_path.write_text(json.dumps(self._id_cache, indent=2))
        except OSError:
            logger.debug(
                "Unable to persist track cache at %s.", self.track_cache_path
            )

    @staticmethod
    def _playlist_track_total(playlist: dict) -> int:
        items_meta = playlist.get("items")
        if isinstance(items_meta, dict):
            total = items_meta.get("total")
            if isinstance(total, int):
                return total
        tracks_meta = playlist.get("tracks")
        if isinstance(tracks_meta, dict):
            total = tracks_meta.get("total")
            if isinstance(total, int):
                return total
        return 0


def _chunked(values: Sequence[str], *, size: int) -> Iterable[Sequence[str]]:
    for idx in range(0, len(values), size):
        yield values[idx : idx + size]


def _build_insertion_plan(
    *, local_positions: Sequence[int], total_track_count: int
) -> list[tuple[int, int]]:
    """
    Compute insertion windows that preserve local-item positions.

    Each tuple is (position, count), where `count` Spotify tracks should be inserted
    at the given playlist position after non-local items have been removed.
    """
    if total_track_count <= 0:
        return []
    if not local_positions:
        return [(0, total_track_count)]

    sorted_positions = sorted(max(0, pos) for pos in local_positions)
    plan: list[tuple[int, int]] = []

    before_first = min(total_track_count, sorted_positions[0])
    if before_first > 0:
        plan.append((0, before_first))
    inserted = before_first

    for previous, current in zip(sorted_positions, sorted_positions[1:]):
        if inserted >= total_track_count:
            break
        gap = max(0, current - previous - 1)
        count = min(gap, total_track_count - inserted)
        if count > 0:
            plan.append((previous + 1, count))
            inserted += count

    remaining = total_track_count - inserted
    if remaining > 0:
        final_position = min(sorted_positions[-1] + 1, total_track_count + len(sorted_positions))
        plan.append((final_position, remaining))
    return plan


def _select_rotation_tracks(
    rotation_ids: Sequence[str],
    *,
    limit: int,
    week_seed: int | None = None,
) -> List[str]:
    """Pick a deterministic weekly subset from the configured rotation pool."""
    if limit <= 0 or not rotation_ids:
        return []
    unique_rotation_ids = list(dict.fromkeys(rotation_ids))
    if len(unique_rotation_ids) <= limit:
        return unique_rotation_ids

    if week_seed is None:
        iso = datetime.now(timezone.utc).isocalendar()
        week_seed = iso.year * 100 + iso.week

    shuffled_indices = list(range(len(unique_rotation_ids)))
    random.Random(week_seed).shuffle(shuffled_indices)
    selected_indices = set(shuffled_indices[:limit])
    return [
        track_id
        for idx, track_id in enumerate(unique_rotation_ids)
        if idx in selected_indices
    ]


class _SpotifyCurlClient:
    """Thin wrapper around curl so we hit the same endpoints proven to work manually."""

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

    def get_url(
        self,
        url: str,
        *,
        allow_failure: bool = False,
        default: Any = None,
    ) -> Any:
        return self._request(
            "GET",
            url,
            allow_failure=allow_failure,
            default=default,
            absolute_url=True,
        )

    def post(
        self,
        path: str,
        *,
        data: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self._request("POST", path, params=params, data=data)

    def put(
        self,
        path: str,
        *,
        data: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> Any:
        return self._request("PUT", path, params=params, data=data)

    def delete(self, path: str, *, data: dict[str, Any]) -> Any:
        return self._request("DELETE", path, data=data)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        allow_failure: bool = False,
        default: Any = None,
        absolute_url: bool = False,
    ) -> Any:
        token = self._access_token()
        url = path if absolute_url else f"{self.API_BASE}/{path.lstrip('/')}"
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
            if (
                "429" in message
                and attempt < max_attempts - 1
            ):
                sleep_time = backoff
                backoff = min(backoff * 1.5, 30.0)
                logger.debug(
                    "Spotify rate limit hit on %s %s; sleeping %.1fs.",
                    method,
                    path,
                    sleep_time,
                )
                time.sleep(sleep_time)
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
