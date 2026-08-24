"""FastAPI surface for the Spotify playlist service."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .manager import PlaylistProfile, SpotifyPlaylistService

app = FastAPI(title="Spotify Playlist Service", version="0.1.0")


class PlaylistRequest(BaseModel):
    playlist_name: str = Field(..., example="Duques Sta Fe")
    description: str = Field(..., example="Barbershop rotation")
    public: bool = True
    curated_queries: List[str] = Field(default_factory=list)
    rotation_queries: List[str] = Field(default_factory=list)
    max_tracks: Optional[int] = Field(default=None, ge=1)
    force: bool = False


@lru_cache(maxsize=1)
def get_service() -> SpotifyPlaylistService:
    try:
        client_id = os.environ["SPOTIFY_CLIENT_ID"]
        client_secret = os.environ["SPOTIFY_CLIENT_SECRET"]
        redirect_uri = os.environ["SPOTIFY_REDIRECT_URI"]
    except KeyError as exc:
        raise RuntimeError(f"Missing Spotify credential: {exc.args[0]}") from exc

    return SpotifyPlaylistService(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )


def _profile_from_request(payload: PlaylistRequest) -> PlaylistProfile:
    return PlaylistProfile(
        playlist_name=payload.playlist_name,
        description=payload.description,
        public=payload.public,
        curated_queries=payload.curated_queries,
        rotation_queries=payload.rotation_queries,
        max_tracks=payload.max_tracks,
    )


@app.post("/playlists/ensure")
def ensure_playlist(
    payload: PlaylistRequest, service: SpotifyPlaylistService = Depends(get_service)
) -> dict:
    """Create the playlist if it does not exist."""
    profile = _profile_from_request(payload)
    playlist = service.ensure_playlist(profile)
    return {
        "id": playlist["id"],
        "name": playlist["name"],
        "url": playlist["external_urls"]["spotify"],
    }


@app.post("/playlists/rotate")
def rotate_playlist(
    payload: PlaylistRequest, service: SpotifyPlaylistService = Depends(get_service)
) -> dict:
    """Replace playlist tracks with the curated rotation list."""
    profile = _profile_from_request(payload)
    try:
        result = service.rotate_playlist(profile, force=payload.force)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "playlist_id": result.playlist_id,
        "playlist_name": result.playlist_name,
        "playlist_url": result.playlist_url,
        "track_count": result.track_count,
        "snapshot_id": result.snapshot_id,
        "preview": list(result.preview),
        "runtime_hours": (result.runtime_ms or 0) / 3600000,
    }
