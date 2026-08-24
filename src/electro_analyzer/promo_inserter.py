"""Utility helpers for inserting promo audio clips into longer mixes."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from pydub import AudioSegment
from pydub.utils import mediainfo


def insert_promos(
    mix_path: str | Path,
    promo_path: str | Path,
    *,
    interval_minutes: float = 20.0,
    promo_gain_db: float = -3.0,
    fade_ms: int = 150,
    output_path: str | Path | None = None,
) -> Path:
    mix_path = Path(mix_path)
    promo_path = Path(promo_path)
    output_path = (
        Path(output_path)
        if output_path is not None
        else mix_path.with_name(f"{mix_path.stem}_with_promos.mp3")
    )

    def _ext(path: Path) -> str | None:
        return path.suffix.lower().lstrip('.') or None

    # Load promo once and resample to match target format
    promo_clip = AudioSegment.from_file(promo_path, format=_ext(promo_path))
    promo_clip = promo_clip.set_frame_rate(44100).set_channels(2)
    promo_clip = promo_clip + promo_gain_db
    if fade_ms > 0:
        promo_clip = promo_clip.fade_in(fade_ms).fade_out(fade_ms)

    total_duration_sec = float(mediainfo(str(mix_path))["duration"])
    total_ms = int(total_duration_sec * 1000)

    temp_dir = Path(tempfile.mkdtemp(prefix="promo_insert_"))
    promo_processed_path = temp_dir / "promo_processed.mp3"
    promo_clip.export(promo_processed_path, format="mp3")

    chunk_paths: list[Path] = []
    interval_ms = int(interval_minutes * 60_000)
    start_ms = 0
    chunk_index = 0
    ext = _ext(mix_path)

    while start_ms < total_ms:
        end_ms = min(start_ms + interval_ms, total_ms)
        duration_sec = max((end_ms - start_ms) / 1000.0, 0.01)
        chunk = AudioSegment.from_file(
            mix_path,
            format=ext,
            start_second=start_ms / 1000.0,
            duration=duration_sec,
        )
        chunk = chunk.set_frame_rate(44100).set_channels(2)
        chunk_path = temp_dir / f"chunk_{chunk_index:04d}.mp3"
        chunk.export(chunk_path, format="mp3")
        chunk_paths.append(chunk_path)
        if end_ms < total_ms:
            chunk_paths.append(promo_processed_path)
        start_ms = end_ms
        chunk_index += 1

    concat_file = temp_dir / "concat.txt"
    with open(concat_file, "w") as fh:
        for path in chunk_paths:
            fh.write(f"file '{path.as_posix()}'\n")

    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_file),
                "-c",
                "copy",
                str(output_path),
            ],
            check=True,
        )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path
