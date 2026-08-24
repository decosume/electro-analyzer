## Instagram Service

This folder holds a minimal Python project for Instagram Graph API work related to social-network content publishing.

It is intentionally separate from the main CLI so we can evolve social automation independently from the music-analysis code.

### What This Service Assumes

- You are using the official Instagram Graph API from Meta.
- The Instagram account is a Professional account (`Business` or `Creator`).
- The Instagram account is linked to a Facebook Page that your Meta app can access.
- You have a valid long-lived access token and the Instagram account ID.

### Layout

- `src/instagram_service/manager.py` – thin Graph API client and publishing helpers
- `src/instagram_service/api.py` – FastAPI shim for health, config inspection, and publishing

### Environment Variables

```bash
export INSTAGRAM_ACCOUNT_ID=...
export INSTAGRAM_ACCESS_TOKEN=...
export META_GRAPH_API_VERSION=v23.0
export META_APP_ID=...
export META_APP_SECRET=...
```

`META_APP_ID` and `META_APP_SECRET` are optional in the current scaffold. They become useful once you add OAuth/token refresh flows.

### Local Usage

```bash
cd instagram_api_service
python -m venv .venv
source .venv/bin/activate
pip install -e .
uvicorn instagram_service.api:app --reload
```

### Current Scope

The scaffold currently focuses on:

- validating local configuration
- creating media containers
- publishing media containers
- fetching basic account metadata

It does not yet implement:

- OAuth login flow
- token refresh automation
- webhook subscriptions
- comment moderation
- reel template generation

### Official References

- Instagram API overview: <https://developers.facebook.com/docs/instagram-platform>
- Content publishing: <https://developers.facebook.com/docs/instagram-platform/content-publishing>
- Insights: <https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/insights>
