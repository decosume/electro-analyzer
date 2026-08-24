#!/usr/bin/env python
"""CLI helper to insert promo clips into a long mix."""

from __future__ import annotations

import argparse
from pathlib import Path

from electro_analyzer.promo_inserter import insert_promos


def main() -> None:
    parser = argparse.ArgumentParser(description="Insert promo clips into a long MP3.")
    parser.add_argument("mix", type=Path, help="Path to the long mix (e.g., DuquesBarbershop-April.mp3)")
    parser.add_argument("promo", type=Path, help="Path to the short promo clip (e.g., promo.mp3)")
    parser.add_argument("--interval-minutes", type=float, default=20.0, help="Minutes between promos (default: 20)")
    parser.add_argument("--gain-db", type=float, default=-3.0, help="Gain adjustment for promo (default: -3 dB)" )
    parser.add_argument("--fade-ms", type=int, default=150, help="Fade in/out applied to promo edges (default: 150 ms)")
    parser.add_argument("--out", type=Path, default=None, help="Optional output filename")
    args = parser.parse_args()

    output = insert_promos(
        args.mix,
        args.promo,
        interval_minutes=args.interval_minutes,
        promo_gain_db=args.gain_db,
        fade_ms=args.fade_ms,
        output_path=args.out,
    )
    print(f"Promo mix written to {output}")


if __name__ == "__main__":
    main()
