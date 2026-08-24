from pathlib import Path

import librosa
import numpy as np
import pytest
import soundfile as sf

from electro_analyzer.analyzer import AnalysisReport, analyze_track
from electro_analyzer.validators import validate_audio_path


def _synthesize_audio(tmp_path: Path, filename: str = "synth.wav", sr: int = 44100) -> Path:
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = 0.5 * np.sin(2 * np.pi * 110 * t) + 0.25 * np.sin(2 * np.pi * 220 * t)
    clicks = librosa.clicks(times=np.linspace(0, duration, num=8, endpoint=False), sr=sr, length=audio.shape[0])
    audio = audio + 0.2 * clicks
    path = tmp_path / filename
    sf.write(path, audio, sr)
    return path


def test_analyze_track_produces_report(tmp_path):
    audio_path = _synthesize_audio(tmp_path)
    report = analyze_track(audio_path)

    assert isinstance(report, AnalysisReport)
    assert report.track == audio_path.name
    assert report.sample_rate == 44100
    assert pytest.approx(report.duration, rel=0.05) == 2.0
    assert report.bpm > 0
    assert report.rms["max"] >= report.rms["min"]
    assert len(report.sections) >= 1
    assert report.quality is not None
    assert isinstance(report.quality.loudness_lufs, float)


def test_analyze_track_rejects_unknown_backend(tmp_path):
    audio_path = _synthesize_audio(tmp_path)
    with pytest.raises(NotImplementedError):
        analyze_track(audio_path, backend="essentia")


def test_validate_audio_path_checks_extension(tmp_path):
    audio_path = _synthesize_audio(tmp_path)
    # Extension supported
    assert validate_audio_path(audio_path) == audio_path

    unsupported = tmp_path / "track.aiff"
    unsupported.write_bytes(audio_path.read_bytes())
    with pytest.raises(ValueError):
        validate_audio_path(unsupported)

    missing = tmp_path / "missing.wav"
    with pytest.raises(FileNotFoundError):
        validate_audio_path(missing)
