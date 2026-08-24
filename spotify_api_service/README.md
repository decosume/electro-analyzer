## Spotify Playlist Service

This folder holds a minimal Python project that reuses the Spotify automation logic from Electro Analyzer.  The goal is to evolve it into an API that can be deployed on AWS (Lambda, ECS, etc.) without disturbing the original CLI.

### Layout

- `src/spotify_service/manager.py` – core service that signs into Spotify, creates playlists, and rotates tracks.
- `src/spotify_service/api.py` – FastAPI shim with `/playlists` endpoints so the service can be exposed as HTTP.

### Local Usage

```bash
cd spotify_api_service
python -m venv .venv
source .venv/bin/activate
pip install -e .
export SPOTIFY_CLIENT_ID=...
export SPOTIFY_CLIENT_SECRET=...
export SPOTIFY_REDIRECT_URI=http://127.0.0.1:8080/callback
uvicorn spotify_service.api:app --reload
```

### Deploying

For AWS Lambda or ECS Fargate:

1. Package this folder as its own repo or artifact.
2. Provide the Spotify secrets via AWS Secrets Manager or SSM Parameters.
3. Run `uvicorn` (ECS) or use a Lambda adapter (e.g., Mangum) to expose the FastAPI app.

The code shares no state with Electro Analyzer apart from relying on Spotipy, so updating one project will not break the other.
