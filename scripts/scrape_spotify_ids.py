#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Safari/605.1.15"
SPOTIFY_REGEX = re.compile(r"https://open\.spotify\.com/track/([A-Za-z0-9]+)")


def fetch_spotify_url(query: str) -> str | None:
    search = f'site:open.spotify.com/track "{query}"'
    url = f"https://duckduckgo.com/html/?q={quote_plus(search)}&num=5"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=10) as resp:  # noqa: S310
        html = resp.read().decode("utf-8", errors="ignore")
    match = SPOTIFY_REGEX.search(html)
    if not match:
        return None
    return f"https://open.spotify.com/track/{match.group(1)}"


def ensure_id(entry: dict[str, Any]) -> bool:
    if entry.get("id"):
        return False
    query = entry.get("query")
    if not query:
        return False
    url = fetch_spotify_url(query)
    if not url:
        print(f"[WARN] No Spotify URL found for '{query}'", file=sys.stderr)
        return False
    entry["id"] = f"spotify:track:{url.rsplit('/', 1)[-1]}"
    print(f"[INFO] {query} -> {entry['id']}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve Spotify IDs via Bing search scraping.")
    parser.add_argument("profile", type=Path, help="Profile JSON file to update.")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds).")
    args = parser.parse_args()

    data = json.loads(args.profile.read_text())
    modified = False

    for key in ("curated_queries", "rotation_queries"):
        items = data.get(key) or []
        normalized = []
        for item in items:
            entry = {"query": item} if isinstance(item, str) else dict(item)
            changed = ensure_id(entry)
            modified = modified or changed
            normalized.append(entry)
            if changed:
                time.sleep(args.delay)
        data[key] = normalized

    if modified:
        args.profile.write_text(json.dumps(data, indent=2))
        print(f"[OK] Updated {args.profile} with Spotify IDs.")
    else:
        print("Nothing changed; all entries already have IDs.")


if __name__ == "__main__":
    main()
