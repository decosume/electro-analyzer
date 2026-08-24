"""Input validation helpers for Electro Analyzer."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

SUPPORTED_AUDIO_EXTENSIONS: tuple[str, ...] = (".wav", ".mp3", ".flac")


def is_supported_audio_file(path: Path) -> bool:
    """Return True if the path exists and uses a supported audio extension."""
    return path.is_file() and path.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS


def validate_audio_path(path: Path) -> Path:
    """
    Validate that the given path points to an existing audio file we support.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file extension is not supported.
    """
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")
    if path.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
        supported = ", ".join(SUPPORTED_AUDIO_EXTENSIONS)
        raise ValueError(
            f"Unsupported audio format '{path.suffix}'. Expected one of: {supported}"
        )
    return path


def validate_extension_list(paths: Iterable[Path]) -> None:
    """Ensure every path in the iterable is supported; raise ValueError otherwise."""
    unsupported = [p for p in paths if p.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS]
    if unsupported:
        supported = ", ".join(SUPPORTED_AUDIO_EXTENSIONS)
        joined = ", ".join(str(p) for p in unsupported)
        raise ValueError(
            f"Unsupported audio formats detected for: {joined}. Expected: {supported}"
        )
