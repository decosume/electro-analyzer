#!/usr/bin/env python3
"""Print all tracks in a Spotify playlist (name, artist, URI)."""

from __future__ import annotations

import argparse

import spotipy
from spotipy.oauth2 import SpotifyOAuth

DEFAULT_SCOPE = "playlist-read-private"


def list_tracks(sp: spotipy.Spotify, playlist_id: str) -> None:
    limit = 100
    offset = 0
    while True:
        data = sp.playlist_items(
            playlist_id,
            limit=limit,
            offset=offset,
            fields="items(track(name,artists(name),uri)),total,next",
        )
        for item in data["items"]:
            track = item["track"]
            if not track:
                continue
            name = track.get("name", "?")
            artist = track.get("artists", [{}])[0].get("name", "?")
            uri = track.get("uri", "")
            print(f"{name} – {artist} -> {uri}")
        if not data.get("next"):
            break
        offset += limit


def main() -> None:
    parser = argparse.ArgumentParser(description="List tracks in a Spotify playlist.")
    parser.add_argument("playlist", help="Playlist ID or URI")
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help="Spotify OAuth scope")
    args = parser.parse_args()

    playlist_id = args.playlist.split(":")[-1]
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=args.scope))
    list_tracks(sp, playlist_id)


if __name__ == "__main__":
    main()
