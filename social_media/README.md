## Social Media Workspace

This folder holds local assets and briefs for social-network content creation.

Suggested workflow:

1. Create a reel brief in `briefs/`
2. Render a local draft with `scripts/build_instagram_reel.py`
3. Review the MP4 in `outputs/`
4. Publish manually or later through the Instagram service

Example:

```bash
.venv/bin/python scripts/build_instagram_reel.py \
  social_media/briefs/spotify_curated_playlists_service.json \
  --out social_media/outputs/spotify_curated_playlists_service.mp4
```
