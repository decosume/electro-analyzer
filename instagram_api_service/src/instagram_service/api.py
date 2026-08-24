"""FastAPI surface for the Instagram Graph API service scaffold."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from .manager import InstagramGraphService, InstagramServiceConfig

app = FastAPI(title="Instagram Service", version="0.1.0")


class MediaContainerRequest(BaseModel):
    image_url: Optional[str] = Field(default=None, examples=["https://example.com/post.jpg"])
    video_url: Optional[str] = Field(default=None, examples=["https://example.com/reel.mp4"])
    media_type: Optional[str] = Field(default=None, examples=["REELS"])
    caption: Optional[str] = None
    share_to_feed: Optional[bool] = True


class PublishRequest(BaseModel):
    creation_id: str


@lru_cache(maxsize=1)
def get_service() -> InstagramGraphService:
    config = InstagramServiceConfig.from_env()
    return InstagramGraphService(config)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/config")
def config_summary(service: InstagramGraphService = Depends(get_service)) -> dict[str, str | bool]:
    config = service.config
    return {
        "instagram_account_id": config.instagram_account_id,
        "graph_api_version": config.graph_api_version,
        "has_app_id": bool(config.app_id),
        "has_app_secret": bool(config.app_secret),
    }


@app.get("/account")
def account(service: InstagramGraphService = Depends(get_service)) -> dict:
    try:
        return service.account_profile()
    except Exception as exc:  # pragma: no cover - runtime API path
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/media/container")
def create_container(
    payload: MediaContainerRequest,
    service: InstagramGraphService = Depends(get_service),
) -> dict:
    if not payload.image_url and not payload.video_url:
        raise HTTPException(status_code=400, detail="Provide image_url or video_url.")
    try:
        return service.create_media_container(
            image_url=payload.image_url,
            video_url=payload.video_url,
            media_type=payload.media_type,
            caption=payload.caption,
            share_to_feed=payload.share_to_feed,
        )
    except Exception as exc:  # pragma: no cover - runtime API path
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/media/publish")
def publish_container(
    payload: PublishRequest,
    service: InstagramGraphService = Depends(get_service),
) -> dict:
    try:
        return service.publish_media(creation_id=payload.creation_id)
    except Exception as exc:  # pragma: no cover - runtime API path
        raise HTTPException(status_code=502, detail=str(exc)) from exc
