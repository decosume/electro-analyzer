"""Simple techno collage generator using beat-sliced segments."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

import librosa
import numpy as np


@dataclass(frozen=True)
class AudioSegment:
    """Beat-aligned slice of audio with an energy score."""

    audio: np.ndarray
    energy: float
    source: Path


def _time_stretch_to_bpm(audio: np.ndarray, *, current_bpm: float, target_bpm: float) -> np.ndarray:
    if target_bpm <= 0 or current_bpm <= 0:
        return audio
    rate = target_bpm / current_bpm
    if np.isclose(rate, 1.0):
        return audio
    return librosa.effects.time_stretch(audio, rate=rate)


def _beat_segments(
    audio: np.ndarray,
    *,
    sr: int,
    bars: int,
    hop_length: int = 512,
    beats_per_bar: int = 4,
) -> tuple[float, list[np.ndarray]]:
    tempo, beats = librosa.beat.beat_track(y=audio, sr=sr, hop_length=hop_length)
    if beats.size < bars * beats_per_bar + 1:
        return tempo, []
    beat_samples = librosa.frames_to_samples(beats, hop_length=hop_length)
    beats_per_segment = bars * beats_per_bar
    step = max(1, beats_per_segment // 2)
    slices: list[np.ndarray] = []
    for start in range(0, len(beat_samples) - beats_per_segment, step):
        start_sample = beat_samples[start]
        end_sample = beat_samples[start + beats_per_segment]
        if end_sample <= start_sample or end_sample > audio.shape[0]:
            continue
        snippet = audio[start_sample:end_sample]
        if snippet.size == 0:
            continue
        slices.append(snippet)
    return tempo, slices


def _extract_segments(
    path: Path,
    *,
    target_sr: int,
    target_bpm: float | None,
    bars: int,
) -> list[AudioSegment]:
    audio, _ = librosa.load(path, sr=target_sr, mono=True)
    tempo, beats = librosa.beat.beat_track(y=audio, sr=target_sr)
    tempo_value = float(np.asarray(tempo).squeeze()) if tempo is not None else 0.0
    if target_bpm and tempo_value > 0.0:
        audio = _time_stretch_to_bpm(audio, current_bpm=tempo_value, target_bpm=target_bpm)
        tempo, beats = librosa.beat.beat_track(y=audio, sr=target_sr)
    hop_length = 512
    _, slices = _beat_segments(audio, sr=target_sr, bars=bars, hop_length=hop_length)
    segments: list[AudioSegment] = []
    for snippet in slices:
        energy = float(np.sqrt(np.mean(snippet**2)))
        segments.append(AudioSegment(audio=snippet, energy=energy, source=path))
    return segments


def _split_by_energy(segments: Sequence[AudioSegment]) -> list[list[AudioSegment]]:
    if not segments:
        return [[]]
    energies = np.array([seg.energy for seg in segments])
    quantiles = np.quantile(energies, [0.0, 0.35, 0.6, 0.85, 1.0])
    buckets: list[list[AudioSegment]] = [[] for _ in range(len(quantiles) - 1)]
    for segment in segments:
        placed = False
        for idx in range(len(quantiles) - 1):
            low, high = quantiles[idx], quantiles[idx + 1]
            if (idx == len(quantiles) - 2 and segment.energy <= high) or (low <= segment.energy < high):
                buckets[idx].append(segment)
                placed = True
                break
        if not placed:
            buckets[-1].append(segment)
    return buckets


def _phase_lengths(total_samples: int) -> list[int]:
    proportions = [0.2, 0.3, 0.3, 0.2]
    lengths = [int(total_samples * p) for p in proportions]
    diff = total_samples - sum(lengths)
    lengths[-1] += diff
    return lengths


def _crossfade_concat(existing: np.ndarray, addition: np.ndarray, fade_samples: int) -> np.ndarray:
    if existing.size == 0:
        return addition.copy()
    if addition.size == 0 or fade_samples <= 0:
        return np.concatenate([existing, addition])
    fade_samples = min(fade_samples, existing.size // 2, addition.size // 2)
    if fade_samples <= 0:
        return np.concatenate([existing, addition])
    fade_in = np.linspace(0.0, 1.0, fade_samples)
    fade_out = 1.0 - fade_in
    cross = existing[-fade_samples:] * fade_out + addition[:fade_samples] * fade_in
    body = np.concatenate([existing[:-fade_samples], cross, addition[fade_samples:]])
    return body


def compose_mix(
    sources: Iterable[Path],
    *,
    duration: float = 300.0,
    target_sr: int = 44100,
    target_bpm: float | None = 128.0,
    bars: int = 8,
    crossfade_seconds: float = 0.05,
    seed: int | None = None,
) -> tuple[np.ndarray, int]:
    """Generate a techno collage from source tracks."""

    source_paths = [path for path in sources if path.exists()]
    if not source_paths:
        raise ValueError("No valid source audio files provided.")
    all_segments: list[AudioSegment] = []
    for path in source_paths:
        segments = _extract_segments(path, target_sr=target_sr, target_bpm=target_bpm, bars=bars)
        all_segments.extend(segments)
    if not all_segments:
        raise ValueError("Unable to extract beat segments from the provided sources.")
    rng = random.Random(seed)
    buckets = _split_by_energy(all_segments)
    target_samples = int(duration * target_sr)
    fade_samples = int(crossfade_seconds * target_sr)
    phase_targets = _phase_lengths(target_samples)
    assembled: list[np.ndarray] = []
    current_total = 0
    cumulative = 0
    for idx, phase_len in enumerate(phase_targets):
        cumulative += phase_len
        pool = buckets[min(idx, len(buckets) - 1)] or all_segments
        while current_total < cumulative:
            segment = rng.choice(pool)
            assembled.append(segment.audio)
            current_total += segment.audio.shape[0]
            if len(assembled) > 500:
                break
    output = np.array([], dtype=np.float32)
    for segment_audio in assembled:
        output = _crossfade_concat(output, segment_audio, fade_samples)
        if output.size >= target_samples + fade_samples:
            break
    if output.size < target_samples:
        pad = np.zeros(target_samples - output.size, dtype=output.dtype)
        output = np.concatenate([output, pad])
    elif output.size > target_samples:
        output = output[:target_samples]
    max_val = np.max(np.abs(output))
    if max_val > 0:
        output = output / max(1.0, max_val)
    return output.astype(np.float32), target_sr
