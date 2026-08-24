#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

try:
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    print("spotipy is required to resolve track IDs. Install with `pip install spotipy`.", file=sys.stderr)
    sys.exit(1)

from electro_analyzer.spotify_playlist import DEFAULT_SCOPES
from electro_analyzer.spotify_playlist import _SpotifyCurlClient  # type: ignore


def load_profile(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def save_profile(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def ensure_id(
    entry: dict[str, Any],
    *,
    client: _SpotifyCurlClient,
    cache: dict[str, tuple[str, int | None]],
) -> bool:
    query = entry.get("query")
    if not query:
        return False
    normalized = query.strip().lower()
    cached = cache.get(normalized)
    if entry.get("id"):
        if cached is None:
            cache[normalized] = (entry["id"], entry.get("duration_ms"))
        return False
    if cached:
        entry["id"] = cached[0]
        if cached[1] is not None:
            entry["duration_ms"] = cached[1]
        return True
    retries = 20
    backoff = 2.0
    attempt = 0
    while attempt < retries:
        try:
            payload = client.get(
                "search",
                params={"q": query, "type": "track", "limit": 1},
            )
            items = payload["tracks"]["items"]
            if not items:
                print(f"[WARN] No results for '{query}'", file=sys.stderr)
                return False
            first = items[0]
            entry["id"] = first["id"]
            duration = first.get("duration_ms")
            if isinstance(duration, (int, float)):
                entry["duration_ms"] = int(duration)
            cache[normalized] = (entry["id"], entry.get("duration_ms"))
            break
        except RuntimeError as exc:
            message = str(exc)
            attempt += 1
            if "429" in message and attempt < retries:
                sleep_time = backoff
                backoff = min(backoff * 1.5, 60.0)
                print(
                    f"[INFO] Rate limit hit for '{query}'. Sleeping {sleep_time:.1f}s...",
                    file=sys.stderr,
                )
                time.sleep(sleep_time)
                continue
            if "403" in message and attempt < retries:
                sleep_time = backoff * 2
                print(
                    f"[INFO] Received 403 for '{query}'. Sleeping {sleep_time:.1f}s before retry...",
                    file=sys.stderr,
                )
                time.sleep(sleep_time)
                continue
            raise
    else:
        print(f"[WARN] Unable to resolve '{query}' after many attempts.", file=sys.stderr)
        return False
    entry["query"] = query
    return True


def batched(iterable: list[Any], size: int) -> Iterable[list[Any]]:
    for idx in range(0, len(iterable), size):
        yield iterable[idx : idx + size]


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve and persist track IDs for profile entries.")
    parser.add_argument("profile", type=Path, help="Path to the profile JSON (e.g., profiles/duques.json).")
    parser.add_argument("--client-id", required=False, help="Spotify client ID (defaults to SPOTIFY_CLIENT_ID env).")
    parser.add_argument("--client-secret", required=False, help="Spotify client secret.")
    parser.add_argument("--redirect-uri", required=False, help="Spotify redirect URI.")
    args = parser.parse_args()

    profile_data = load_profile(args.profile)
    playlist_name = profile_data.get("playlist_name", args.profile.stem)
    print(f"Resolving track IDs for '{playlist_name}' ({args.profile})")

    oauth = SpotifyOAuth(
        client_id=args.client_id,
        client_secret=args.client_secret,
        redirect_uri=args.redirect_uri,
        scope=" ".join(DEFAULT_SCOPES),
        cache_path=str(Path.home() / ".cache-barbershop-playlist"),
    )
    client = _SpotifyCurlClient(oauth)

    resolve_cache: dict[str, tuple[str, int | None]] = {}
    for key in ("curated_queries", "rotation_queries"):
        items = profile_data.get(key) or []
        for entry in items:
            if isinstance(entry, dict):
                query = entry.get("query")
                track_id = entry.get("id")
                if query and track_id:
                    resolve_cache[query.strip().lower()] = (
                        track_id,
                        entry.get("duration_ms"),
                    )

    modified = False
    max_batch = 15
    for key in ("curated_queries", "rotation_queries"):
        items = profile_data.get(key) or []
        batch_iter = batched(items, max_batch)
        enriched = []
        for chunk in batch_iter:
            for item in chunk:
                if isinstance(item, str):
                    entry = {"query": item}
                else:
                    entry = dict(item)
                changed = ensure_id(entry, client=client, cache=resolve_cache)
                modified = modified or changed
                enriched.append(entry)
                if changed:
                    time.sleep(0.1)
            if len(chunk) == max_batch:
                print("[INFO] Batch complete, pausing 5s to respect rate limits...", file=sys.stderr)
                time.sleep(5)
        profile_data[key] = enriched

    if modified:
        save_profile(args.profile, profile_data)
        print(f"Profile updated with IDs: {args.profile}")
    else:
        print("Nothing to update; all entries already have IDs.")


if __name__ == "__main__":
    main()
