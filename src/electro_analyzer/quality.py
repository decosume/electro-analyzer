"""Audio quality metrics and heuristics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

import librosa
import numpy as np
import pyloudnorm as pyln


@dataclass(slots=True)
class QualityMetrics:
    """Computed metrics describing perceived loudness and balance."""

    loudness_lufs: float
    true_peak_db: float
    crest_factor_db: float
    bass_ratio: float
    dynamic_range_db: float
    alerts: List[str]

    def to_dict(self) -> Dict[str, float | List[str]]:
        return {
            "loudness_lufs": float(self.loudness_lufs),
            "true_peak_db": float(self.true_peak_db),
            "crest_factor_db": float(self.crest_factor_db),
            "bass_ratio": float(self.bass_ratio),
            "dynamic_range_db": float(self.dynamic_range_db),
            "alerts": self.alerts,
        }


def _true_peak_amplitude(audio: np.ndarray, sample_rate: int, oversample: int = 4) -> float:
    """Approximate true peak via oversampled resampling."""
    if oversample <= 1:
        return float(np.max(np.abs(audio)))
    high_rate = sample_rate * oversample
    upsampled = librosa.resample(audio, orig_sr=sample_rate, target_sr=high_rate)
    return float(np.max(np.abs(upsampled)))


def _compute_loudness(audio: np.ndarray, sample_rate: int) -> tuple[float, float]:
    """Estimate integrated loudness and approximate true peak."""
    meter = pyln.Meter(sample_rate)
    loudness = float(meter.integrated_loudness(audio))
    true_peak = _true_peak_amplitude(audio, sample_rate)
    true_peak_db = float(20 * np.log10(true_peak)) if true_peak > 0 else -np.inf
    return loudness, true_peak_db


def bass_energy_ratio(audio: np.ndarray, sample_rate: int, cutoff_hz: float = 120.0) -> float:
    """Ratio of bass-band energy to total energy."""
    stft = np.abs(librosa.stft(audio))
    freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
    bass_band = stft[freqs <= cutoff_hz]
    total_energy = float(np.sum(stft))
    bass_energy = float(np.sum(bass_band))
    if total_energy == 0.0:
        return 0.0
    return bass_energy / total_energy


def _crest_factor_db(audio: np.ndarray) -> float:
    """Return crest factor in decibels."""
    peak = float(np.max(np.abs(audio)))
    if peak == 0.0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms == 0.0:
        return 0.0
    crest = peak / rms
    return float(librosa.amplitude_to_db([crest], ref=1.0)[0])


def assess_quality(audio: np.ndarray, sample_rate: int) -> QualityMetrics:
    """Compute quality metrics and heuristic alerts."""
    loudness_lufs, true_peak_db = _compute_loudness(audio, sample_rate)
    crest = _crest_factor_db(audio)
    bass_ratio = bass_energy_ratio(audio, sample_rate)

    rms = librosa.feature.rms(y=audio)[0]
    dynamic_range = float((np.max(rms) - np.min(rms)) if len(rms) else 0.0)

    alerts: List[str] = []
    if loudness_lufs > -9:
        alerts.append("Track is quite loud; watch for over-compression.")
    elif loudness_lufs < -16:
        alerts.append("Track is quieter than typical streaming targets (-14 LUFS).")

    if crest < 6:
        alerts.append("Low crest factor indicates aggressive limiting.")
    elif crest > 15:
        alerts.append("High crest factor; consider more compression for consistency.")

    if bass_ratio > 0.4:
        alerts.append("Bass dominates the mix; check low-end balance.")
    elif bass_ratio < 0.15:
        alerts.append("Bass may be lacking; consider boosting low frequencies.")

    if true_peak_db >= -0.3:
        alerts.append("True peak near 0 dBFS; risk of clipping.")

    return QualityMetrics(
        loudness_lufs=loudness_lufs,
        true_peak_db=true_peak_db,
        crest_factor_db=crest,
        bass_ratio=bass_ratio,
        dynamic_range_db=float(librosa.amplitude_to_db([dynamic_range], ref=1.0)[0])
        if dynamic_range > 0
        else 0.0,
        alerts=alerts,
    )
