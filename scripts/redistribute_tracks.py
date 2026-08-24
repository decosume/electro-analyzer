#!/usr/bin/env python3
"""Interleave new Spotify tracks across an existing playlist."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

import spotipy
from spotipy.oauth2 import SpotifyOAuth

DEFAULT_SCOPE = "playlist-read-private playlist-modify-private playlist-modify-public"


def read_track_uris(path: Path) -> List[str]:
    return [line.strip() for line in path.read_text().splitlines() if line.strip()]


def fetch_playlist_track_uris(sp: spotipy.Spotify, playlist_id: str) -> List[str]:
    uris: List[str] = []
    limit = 100
    offset = 0
    while True:
        items = sp.playlist_items(
            playlist_id,
            limit=limit,
            offset=offset,
            fields="items(track(uri)),next",
        )
        for item in items["items"]:
            track = item["track"]
            if track and track.get("uri"):
                uris.append(track["uri"])
        offset += limit
        if not items.get("next"):
            break
    return uris


def interleave_tracks(original: List[str], new_tracks: List[str], interval: int) -> List[str]:
    result: List[str] = []
    orig_idx = 0
    new_idx = 0
    while orig_idx < len(original) or new_idx < len(new_tracks):
        # add up to interval original tracks
        for _ in range(interval):
            if orig_idx < len(original):
                result.append(original[orig_idx])
                orig_idx += 1
            else:
                break
        # add one new track if available
        if new_idx < len(new_tracks):
            result.append(new_tracks[new_idx])
            new_idx += 1
    # append any remaining originals
    if orig_idx < len(original):
        result.extend(original[orig_idx:])
    return result


def replace_playlist_tracks(sp: spotipy.Spotify, playlist_id: str, uris: List[str]) -> None:
    sp.playlist_replace_items(playlist_id, [])  # clear playlist
    chunk_size = 100
    for start in range(0, len(uris), chunk_size):
        sp.playlist_add_items(playlist_id, uris[start:start + chunk_size])


def main() -> None:
    parser = argparse.ArgumentParser(description="Interleave new Spotify tracks into a playlist.")
    parser.add_argument("playlist", help="Playlist ID or URI")
    parser.add_argument("new_tracks", type=Path, help="Text file with new track URIs")
    parser.add_argument("--interval", type=int, default=10, help="Insert one new track after this many originals.")
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help="Spotify OAuth scope")
    args = parser.parse_args()

    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=args.scope))
    playlist_id = args.playlist.split(":")[-1]
    original = fetch_playlist_track_uris(sp, playlist_id)
    new_tracks = read_track_uris(args.new_tracks)
    if not new_tracks:
        raise SystemExit("No new tracks provided.")
    reordered = interleave_tracks(original, new_tracks, args.interval)
    replace_playlist_tracks(sp, playlist_id, reordered)
    print(f"Playlist {playlist_id} updated with {len(reordered)} tracks (interval {args.interval}).")


if __name__ == "__main__":
    main()
