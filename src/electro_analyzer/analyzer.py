"""Core analysis utilities for Electro Analyzer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

import librosa
import numpy as np

from .quality import QualityMetrics, assess_quality
from .validators import validate_audio_path

KEY_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


@dataclass(slots=True)
class Section:
    """Represents a coarse musical section within the track."""

    label: str
    start: float
    end: float
    energy: float


@dataclass(slots=True)
class AnalysisReport:
    """Container for all analysis metrics produced by the analyzer."""

    track: str
    sample_rate: int
    duration: float
    bpm: float
    key: str
    drop_time: float
    rms: Dict[str, float]
    sections: List[Section]
    quality: QualityMetrics | None = None

    def to_dict(self) -> Dict[str, object]:
        """Serialize the report to a JSON-friendly dictionary."""
        payload = asdict(self)
        payload["sections"] = [asdict(section) for section in self.sections]
        if self.quality is not None:
            payload["quality"] = self.quality.to_dict()
        return payload


def _estimate_key(audio: np.ndarray, sample_rate: int) -> str:
    """Estimate the musical key using a simple chroma profile."""
    chroma = librosa.feature.chroma_cqt(y=audio, sr=sample_rate)
    profile = chroma.mean(axis=1)
    tonic_index = int(np.argmax(profile))

    # Distinguish between major / minor using tonal centroid energy.
    tonnetz = librosa.feature.tonnetz(y=audio, sr=sample_rate)
    tonnetz_energy = np.abs(tonnetz).mean()
    mode = "major" if tonnetz_energy >= 0.02 else "minor"
    return f"{KEY_NAMES[tonic_index]} {mode}"


def _segment_sections(audio: np.ndarray, sample_rate: int, num_sections: int = 4) -> List[Section]:
    """
    Produce coarse sections by aggregating RMS energy into equal-duration bins.

    This prioritizes stability and keeps the implementation lightweight while
    still surfacing relative energy differences across the track.
    """
    hop_length = 1024
    rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sample_rate, hop_length=hop_length)

    if len(rms) == 0:
        duration = float(len(audio) / sample_rate)
        return [Section(label="Section 1", start=0.0, end=duration, energy=0.0)]

    section_indices = np.array_split(np.arange(len(rms)), min(num_sections, len(rms)))
    sections: List[Section] = []
    for idx, indices in enumerate(section_indices, start=1):
        section_rms = rms[indices]
        start_time = float(times[indices[0]])
        end_index = indices[-1]
        if end_index >= len(times):
            end_index = len(times) - 1
        end_time = float(times[end_index])
        sections.append(
            Section(
                label=f"Section {idx}",
                start=start_time,
                end=end_time,
                energy=float(section_rms.mean()),
            )
        )
    return sections


def _detect_drop_time(audio: np.ndarray, sample_rate: int) -> float:
    """Locate the drop as the time with the highest short-term energy."""
    hop_length = 512
    rms = librosa.feature.rms(y=audio, hop_length=hop_length)[0]
    if len(rms) == 0:
        return 0.0
    drop_index = int(np.argmax(rms))
    return float(librosa.frames_to_time(drop_index, sr=sample_rate, hop_length=hop_length))


def _compute_rms_stats(audio: np.ndarray, sample_rate: int) -> Dict[str, float]:
    """Return summary statistics for the RMS energy envelope."""
    hop_length = 512
    rms = librosa.feature.rms(y=audio, hop_length=hop_length)[0]
    if len(rms) == 0:
        return {"mean": 0.0, "max": 0.0, "min": 0.0, "dynamic_range": 0.0}
    return {
        "mean": float(np.mean(rms)),
        "max": float(np.max(rms)),
        "min": float(np.min(rms)),
        "dynamic_range": float(np.max(rms) - np.min(rms)),
    }


def analyze_track(audio_path: Path, sample_rate: int = 44100, backend: str = "librosa") -> AnalysisReport:
    """
    Analyze an audio track and return a structured analysis report.

    Args:
        audio_path: Location of the audio file to analyze.
        sample_rate: Target sampling rate for analysis.
        backend: Reserved for future alternative analyzers (unused for now).
    """
    if backend != "librosa":
        raise NotImplementedError(f"Backend '{backend}' is not implemented yet.")

    validated_path = validate_audio_path(audio_path)
    audio, sr = librosa.load(validated_path, sr=sample_rate, mono=True)

    tempo, _ = librosa.beat.beat_track(y=audio, sr=sr)
    estimated_key = _estimate_key(audio, sr)
    sections = _segment_sections(audio, sr)
    drop_time = _detect_drop_time(audio, sr)
    rms_stats = _compute_rms_stats(audio, sr)
    duration = float(librosa.get_duration(y=audio, sr=sr))
    quality_metrics = assess_quality(audio, sr)

    return AnalysisReport(
        track=validated_path.name,
        sample_rate=sr,
        duration=duration,
        bpm=float(np.round(tempo, 2)),
        key=estimated_key,
        drop_time=float(np.round(drop_time, 2)),
        rms={name: float(np.round(value, 4)) for name, value in rms_stats.items()},
        sections=[
            Section(
                label=section.label,
                start=float(np.round(section.start, 2)),
                end=float(np.round(section.end, 2)),
                energy=float(np.round(section.energy, 4)),
            )
            for section in sections
        ],
        quality=quality_metrics,
    )
