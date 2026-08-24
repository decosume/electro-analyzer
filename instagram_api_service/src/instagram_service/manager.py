"""Thin Instagram Graph API client for publishing and account inspection."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class InstagramServiceConfig:
    """Configuration required to interact with the Instagram Graph API."""

    instagram_account_id: str
    access_token: str
    graph_api_version: str = "v23.0"
    app_id: str | None = None
    app_secret: str | None = None

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{self.graph_api_version}"

    @classmethod
    def from_env(cls) -> "InstagramServiceConfig":
        try:
            instagram_account_id = os.environ["INSTAGRAM_ACCOUNT_ID"]
            access_token = os.environ["INSTAGRAM_ACCESS_TOKEN"]
        except KeyError as exc:
            raise RuntimeError(
                f"Missing Instagram configuration: {exc.args[0]}"
            ) from exc

        return cls(
            instagram_account_id=instagram_account_id,
            access_token=access_token,
            graph_api_version=os.environ.get("META_GRAPH_API_VERSION", "v23.0"),
            app_id=os.environ.get("META_APP_ID"),
            app_secret=os.environ.get("META_APP_SECRET"),
        )


class InstagramGraphService:
    """Minimal helper around the official Instagram Graph API."""

    def __init__(
        self,
        config: InstagramServiceConfig,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.config = config
        self.client = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        self.client.close()

    def account_profile(self) -> dict[str, Any]:
        """Fetch basic metadata for the configured Instagram professional account."""
        return self._get(
            f"{self.config.instagram_account_id}",
            params={"fields": "id,username,name,profile_picture_url"},
        )

    def create_media_container(
        self,
        *,
        image_url: str | None = None,
        video_url: str | None = None,
        media_type: str | None = None,
        caption: str | None = None,
        share_to_feed: bool | None = None,
    ) -> dict[str, Any]:
        """Create an Instagram media container for later publishing."""
        payload: dict[str, Any] = {}
        if image_url:
            payload["image_url"] = image_url
        if video_url:
            payload["video_url"] = video_url
        if media_type:
            payload["media_type"] = media_type
        if caption:
            payload["caption"] = caption
        if share_to_feed is not None:
            payload["share_to_feed"] = str(share_to_feed).lower()
        return self._post(f"{self.config.instagram_account_id}/media", payload)

    def publish_media(self, *, creation_id: str) -> dict[str, Any]:
        """Publish a previously-created container."""
        return self._post(
            f"{self.config.instagram_account_id}/media_publish",
            {"creation_id": creation_id},
        )

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_params = dict(params or {})
        request_params["access_token"] = self.config.access_token
        response = self.client.get(f"{self.config.base_url}/{path.lstrip('/')}", params=request_params)
        response.raise_for_status()
        return response.json()

    def _post(self, path: str, data: dict[str, Any]) -> dict[str, Any]:
        payload = dict(data)
        payload["access_token"] = self.config.access_token
        response = self.client.post(f"{self.config.base_url}/{path.lstrip('/')}", data=payload)
        response.raise_for_status()
        return response.json()
