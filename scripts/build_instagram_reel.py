#!/usr/bin/env python
"""Render a simple vertical reel locally using FFmpeg."""

from __future__ import annotations

import argparse
from pathlib import Path

from electro_analyzer.social_video import (
    build_reel_command,
    format_command,
    load_reel_spec,
    render_reel,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "brief",
        type=Path,
        help="Path to the reel JSON brief.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("social_media/outputs/spotify_curated_playlists_reel.mp4"),
        help="Output MP4 path.",
    )
    parser.add_argument(
        "--audio",
        type=Path,
        default=Path("background_music.mp3"),
        help="Optional background audio file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the FFmpeg command without rendering.",
    )
    args = parser.parse_args()

    spec = load_reel_spec(args.brief)
    audio_path = args.audio if args.audio.exists() else None
    cmd = build_reel_command(spec=spec, output_path=args.out, audio_path=audio_path)
    if args.dry_run:
        print(format_command(cmd))
        return
    result = render_reel(spec=spec, output_path=args.out, audio_path=audio_path)
    print(f"Reel written to {result}")


if __name__ == "__main__":
    main()
