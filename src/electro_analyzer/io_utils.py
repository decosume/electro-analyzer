"""Utilities for interacting with the filesystem."""

from __future__ import annotations

from pathlib import Path


def ensure_directory(directory: Path) -> Path:
    """Create the directory if it does not already exist and return the path."""
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def derive_output_stem(audio_path: Path) -> str:
    """Return a filesystem-friendly stem to use for generated artifacts."""
    return audio_path.stem.replace(" ", "_").lower()


def resolve_plot_paths(audio_path: Path, output_dir: Path) -> dict[str, Path]:
    """
    Compute the paths for waveform, spectrogram, and chroma images.

    Args:
        audio_path: The source audio file.
        output_dir: Directory where plots should be written.

    Returns:
        Mapping of artifact name to filesystem path.
    """
    stem = derive_output_stem(audio_path)
    return {
        "waveform": output_dir / f"{stem}_waveform.png",
        "spectrogram": output_dir / f"{stem}_spectrogram.png",
        "chroma": output_dir / f"{stem}_chroma.png",
    }
