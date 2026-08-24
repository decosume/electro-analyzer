"""Audio mastering helpers powered by ffmpeg filters."""

from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

import librosa
import numpy as np
import soundfile as sf

from .quality import bass_energy_ratio


@dataclass(slots=True)
class MasteringSettings:
    """Configuration for the ffmpeg-based mastering chain."""

    sample_rate: int = 44100
    pre_emphasis: float = 0.97
    compressor_threshold_db: float = -18.0
    compressor_ratio: float = 4.0
    target_peak_db: float = -1.0
    limiter_ceiling_db: float = -0.3
    bass_balance_target: float | None = None
    bass_cutoff_hz: float = 120.0
    preserve_bass_ratio: bool = True
    gentle: bool = False


def _determine_bass_gain(
    audio_path: Path, config: MasteringSettings
) -> tuple[float, float]:
    """
    Compute the gain (in dB) required to reach the desired bass ratio.

    Returns:
        current_ratio: Measured bass energy ratio for the source.
        gain_db: Gain to apply via EQ (0 if no adjustment requested).
    """
    audio, sr = librosa.load(audio_path, sr=config.sample_rate, mono=True)
    current_ratio = bass_energy_ratio(audio, sr, config.bass_cutoff_hz)

    if config.bass_balance_target is not None:
        target_ratio = float(np.clip(config.bass_balance_target, 0.05, 0.9))
    elif config.preserve_bass_ratio:
        target_ratio = current_ratio
    else:
        return current_ratio, 0.0

    if current_ratio <= 0.0 or np.isclose(current_ratio, target_ratio, atol=1e-4):
        return current_ratio, 0.0
    gain_db = float(np.clip(20 * np.log10(target_ratio / current_ratio), -12.0, 12.0))
    return current_ratio, gain_db


def _build_filter_chain(config: MasteringSettings, bass_gain_db: float) -> str:
    """Assemble the ffmpeg audio filter chain."""
    filters: list[str] = []

    if not config.gentle and config.pre_emphasis > 0:
        emphasis_gain = np.clip(config.pre_emphasis * 6.0, 0.0, 9.0)
        filters.append(
            f"equalizer=f=3500:t=h:width_type=o:width=2:g={emphasis_gain:.2f}"
        )

    threshold = (
        config.compressor_threshold_db + 6.0 if config.gentle else config.compressor_threshold_db
    )
    ratio = 2.0 if config.gentle else config.compressor_ratio
    filters.append(
        "acompressor="
        f"threshold={threshold}dB:"
        f"ratio={ratio}:attack=5:release=100"
    )

    if abs(bass_gain_db) >= 0.1:
        filters.append(
            "equalizer="
            f"f={config.bass_cutoff_hz}:t=h:width_type=o:width=2:"
            f"g={bass_gain_db:.2f}"
        )

    filters.append(f"alimiter=limit={config.limiter_ceiling_db}dB:level=1")

    extra_gain = config.target_peak_db - config.limiter_ceiling_db
    if abs(extra_gain) >= 0.1:
        filters.append(f"volume={extra_gain:.2f}dB")

    return ",".join(filters)


def _run_ffmpeg(input_path: Path, output_path: Path, sample_rate: int, filters: str) -> None:
    """Invoke ffmpeg with the assembled filter chain."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ar",
        str(sample_rate),
    ]
    if filters:
        cmd.extend(["-af", filters])
    cmd.append(str(output_path))
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def master_track(audio_path: Path, settings: MasteringSettings | None = None) -> Tuple[np.ndarray, int]:
    """
    Master the audio using ffmpeg filters and return the processed waveform and sample rate.
    """
    config = settings or MasteringSettings()
    _, bass_gain_db = _determine_bass_gain(audio_path, config)
    filters = _build_filter_chain(config, bass_gain_db)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        temp_output = Path(handle.name)
    try:
        _run_ffmpeg(audio_path, temp_output, config.sample_rate, filters)
        audio, sr = sf.read(temp_output, dtype="float32", always_2d=True)
    finally:
        temp_output.unlink(missing_ok=True)

    return audio.T, int(sr)
