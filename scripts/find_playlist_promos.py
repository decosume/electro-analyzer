#!/usr/bin/env python3
"""Helper to list playlist tracks that start with a specific prefix."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable

from electro_analyzer.spotify_playlist import BarberShopPlaylistManager


def iter_playlist_tracks(manager: BarberShopPlaylistManager, playlist_id: str) -> Iterable[dict]:
    """Yield each track entry from the playlist, paging through Spotify results."""
    offset = 0
    while True:
        page = manager.client.get(
            f"playlists/{playlist_id}/tracks",
            params={"limit": 100, "offset": offset},
        )
        items = page.get("items") or []
        for item in items:
            yield item.get("track") or {}
        if not page.get("next"):
            break
        offset += len(items)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--playlist",
        default="Duques Sta Fe",
        help="Spotify playlist name to inspect (default: %(default)s).",
    )
    parser.add_argument(
        "--prefix",
        default="promo",
        help="Match track titles that start with this text (case-insensitive).",
    )
    args = parser.parse_args()

    try:
        spotify_client_id = os.environ["SPOTIFY_CLIENT_ID"]
        spotify_client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
        spotify_redirect_uri = os.environ["SPOTIFY_REDIRECT_URI"]
    except KeyError as exc:  # pragma: no cover - CLI ergonomics
        missing = exc.args[0]
        print(f"Missing required environment variable: {missing}", file=sys.stderr)
        return 1

    manager = BarberShopPlaylistManager(
        client_id=spotify_client_id,
        client_secret=spotify_client_secret,
        redirect_uri=spotify_redirect_uri,
    )

    playlist = manager._find_playlist_by_name(args.playlist)
    if not playlist:  # pragma: no cover - runtime guard
        print(f"Playlist '{args.playlist}' was not found.", file=sys.stderr)
        return 1

    prefix = args.prefix.strip().lower()
    matches: list[str] = []
    for track in iter_playlist_tracks(manager, playlist["id"]):
        name = (track.get("name") or "").strip()
        if not name or (prefix and not name.lower().startswith(prefix)):
            continue
        artist = (track.get("artists") or [{}])[0].get("name", "Unknown")
        matches.append(f"{artist} – {name} ({track.get('id')})")

    if matches:
        print("\n".join(matches))
    else:
        print("No matching tracks found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
