"""Plotting utilities for Electro Analyzer."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np


def _save_figure(path: Path) -> None:
    """Persist the current matplotlib figure to disk and close it."""
    plt.tight_layout()
    plt.savefig(path, dpi=200)
    plt.close()


def plot_waveform(audio: np.ndarray, sample_rate: int, path: Path) -> None:
    """Save a waveform plot for the audio signal."""
    duration = audio.shape[0] / sample_rate
    time_axis = np.linspace(0, duration, audio.shape[0])
    plt.figure(figsize=(10, 4))
    plt.plot(time_axis, audio, linewidth=0.8)
    plt.title("Waveform")
    plt.xlabel("Time (s)")
    plt.ylabel("Amplitude")
    plt.grid(alpha=0.3)
    _save_figure(path)


def plot_spectrogram(audio: np.ndarray, sample_rate: int, path: Path) -> None:
    """Save a log-scaled Mel spectrogram plot."""
    mel_spec = librosa.feature.melspectrogram(y=audio, sr=sample_rate, n_mels=128)
    log_mel_spec = librosa.power_to_db(mel_spec, ref=np.max)
    plt.figure(figsize=(10, 4))
    librosa.display.specshow(log_mel_spec, sr=sample_rate, x_axis="time", y_axis="mel")
    plt.title("Mel Spectrogram (dB)")
    plt.colorbar(format="%+2.0f dB")
    _save_figure(path)


def plot_chroma(audio: np.ndarray, sample_rate: int, path: Path) -> None:
    """Save a chromagram plot."""
    chroma = librosa.feature.chroma_cqt(y=audio, sr=sample_rate)
    plt.figure(figsize=(10, 4))
    librosa.display.specshow(chroma, sr=sample_rate, x_axis="time", y_axis="chroma")
    plt.title("Chromagram")
    plt.colorbar()
    _save_figure(path)


def generate_plots(audio: np.ndarray, sample_rate: int, paths: Iterable[Tuple[str, Path]]) -> None:
    """Generate all plots based on a mapping order defined by the caller."""
    for name, path in paths:
        if name == "waveform":
            plot_waveform(audio, sample_rate, path)
        elif name == "spectrogram":
            plot_spectrogram(audio, sample_rate, path)
        elif name == "chroma":
            plot_chroma(audio, sample_rate, path)
        else:
            raise ValueError(f"Unknown plot type: {name}")
