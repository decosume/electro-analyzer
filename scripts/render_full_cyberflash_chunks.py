#!/usr/bin/env python3.11
"""Apply full-length cyberflash/glitch overlays to pre-rendered pulse chunks."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nw=1:nk=1",
        str(path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def build_enable_expr(windows: list[dict[str, float]], start: float, end: float) -> str:
    parts: list[str] = []
    for window in windows:
        local_start = max(0.0, float(window["start"]) - start)
        local_end = min(end - start, float(window["end"]) - start)
        if local_end <= 0.0 or local_start >= (end - start) or local_end <= local_start:
            continue
        parts.append(f"between(t,{local_start:.3f},{local_end:.3f})")
    return "+".join(parts) if parts else "0"


def render_chunk(
    input_path: Path,
    output_path: Path,
    start: float,
    duration: float,
    windows: dict[str, list[dict[str, float]]],
    crf: int,
    preset: str,
) -> None:
    mag_expr = build_enable_expr(windows["mag"], start, start + duration)
    cyan_expr = build_enable_expr(windows["cyan"], start, start + duration)
    glitch_expr = build_enable_expr(windows["glitch"], start, start + duration)

    # The glitch layer stays full-frame so it cannot expose a colored border.
    filter_graph = ";".join(
        [
            "[0:v]split=4[base][magbase][cyanbase][glitchbase]",
            "[magbase]format=rgba,colorchannelmixer=rr=1:gg=0.18:bb=1:aa=0.56[mag]",
            "[cyanbase]format=rgba,colorchannelmixer=rr=0.12:gg=1:bb=1:aa=0.50[cyan]",
            (
                "[glitchbase]crop=iw-20:ih-10:10:5,"
                "scale=iw:ih:flags=bicubic,"
                "eq=contrast=1.28:brightness=0.035,"
                "format=rgba,colorchannelmixer=aa=0.34[glitch]"
            ),
            f"[base][mag]overlay=0:0:enable='{mag_expr}'[v1]",
            f"[v1][cyan]overlay=0:0:enable='{cyan_expr}'[v2]",
            f"[v2][glitch]overlay=0:0:enable='{glitch_expr}'[vout]",
        ]
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-filter_complex",
        filter_graph,
        "-map",
        "[vout]",
        "-map",
        "0:a",
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "copy",
        str(output_path),
    ]
    run(cmd)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--windows", type=Path, required=True)
    parser.add_argument("--chunk-out-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--crf", type=int, default=22)
    parser.add_argument("--preset", default="ultrafast")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    windows_payload = json.loads(args.windows.read_text())
    args.chunk_out_dir.mkdir(parents=True, exist_ok=True)

    concat_lines: list[str] = []
    for chunk in manifest["chunks"]:
        source = Path(chunk["file"])
        duration = ffprobe_duration(source)
        rendered = args.chunk_out_dir / f"cyber_{chunk['index']:02d}.mp4"
        render_chunk(
            input_path=source,
            output_path=rendered,
            start=float(chunk["start"]),
            duration=duration,
            windows=windows_payload["windows"],
            crf=args.crf,
            preset=args.preset,
        )
        concat_lines.append(f"file '{rendered.resolve()}'")

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as handle:
        handle.write("\n".join(concat_lines) + "\n")
        concat_path = Path(handle.name)

    try:
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-c",
                "copy",
                str(args.output),
            ]
        )
    finally:
        concat_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
