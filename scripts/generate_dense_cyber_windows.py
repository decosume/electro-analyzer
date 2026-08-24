#!/usr/bin/env python3.11
"""Generate dense random cyberflash windows across a full timeline."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=17)
    parser.add_argument("--min-gap", type=float, default=3.2)
    parser.add_argument("--max-gap", type=float, default=8.8)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    mag: list[dict[str, float | str]] = []
    cyan: list[dict[str, float | str]] = []
    glitch: list[dict[str, float | str]] = []

    cursor = 6.0
    while cursor < args.duration - 1.0:
        burst_count = rng.randint(1, 3)
        burst_spacing = rng.uniform(0.12, 0.32)
        base = cursor + rng.uniform(-0.2, 0.2)

        for idx in range(burst_count):
            start = max(0.0, base + idx * burst_spacing)
            mag_len = rng.uniform(0.06, 0.14)
            cyan_len = rng.uniform(0.06, 0.14)
            glitch_len = rng.uniform(0.14, 0.34)

            mag.append(
                {
                    "kind": "mag",
                    "start": round(start, 3),
                    "end": round(min(args.duration, start + mag_len), 3),
                }
            )
            cyan_start = start + rng.uniform(0.05, 0.13)
            cyan.append(
                {
                    "kind": "cyan",
                    "start": round(cyan_start, 3),
                    "end": round(min(args.duration, cyan_start + cyan_len), 3),
                }
            )
            glitch.append(
                {
                    "kind": "glitch",
                    "start": round(start, 3),
                    "end": round(min(args.duration, start + glitch_len), 3),
                }
            )

        cursor += rng.uniform(args.min_gap, args.max_gap)

    payload = {
        "duration": args.duration,
        "accent_count": len(mag),
        "riser_count": len(glitch),
        "windows": {
            "mag": mag,
            "cyan": cyan,
            "glitch": glitch,
        },
    }
    args.out.write_text(json.dumps(payload, indent=2))
    print(args.out)


if __name__ == "__main__":
    main()
