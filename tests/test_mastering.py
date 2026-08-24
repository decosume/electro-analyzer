import numpy as np
import pytest
import soundfile as sf
from typer.testing import CliRunner

import librosa

from electro_analyzer.cli import app
from electro_analyzer.mastering import MasteringSettings, master_track
from electro_analyzer.quality import bass_energy_ratio


def _create_signal(tmp_path, filename="tone.wav", sr=44100):
    duration = 1.5
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Sum two sine waves to create mild dynamics.
    audio = 0.8 * np.sin(2 * np.pi * 220 * t) + 0.4 * np.sin(2 * np.pi * 440 * t)
    path = tmp_path / filename
    sf.write(path, audio, sr)
    return path


def test_master_track_limits_peak(tmp_path):
    audio_path = _create_signal(tmp_path)
    settings = MasteringSettings(
        target_peak_db=-1.5,
        limiter_ceiling_db=-1.0,
    )
    mastered, sr = master_track(audio_path, settings=settings)

    assert sr == settings.sample_rate
    peak = float(np.max(np.abs(mastered)))
    expected_max = float(librosa.db_to_amplitude(settings.limiter_ceiling_db))
    assert peak <= expected_max * 1.1


def test_master_cli_writes_file(tmp_path):
    audio_path = _create_signal(tmp_path)
    out_file = tmp_path / "mastered.wav"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "master",
            str(audio_path),
            "--out",
            str(out_file),
        ],
    )

    assert result.exit_code == 0, result.output
    assert out_file.exists()
    data, _ = sf.read(out_file)
    assert data.shape[0] > 0


def test_master_track_preserves_bass(tmp_path):
    audio_path = _create_signal(tmp_path)
    original, sr = librosa.load(audio_path, sr=44100)
    original_ratio = bass_energy_ratio(original, sr)

    settings = MasteringSettings(
        pre_emphasis=0.0,
        preserve_bass_ratio=True,
        compressor_threshold_db=-6.0,
        compressor_ratio=2.0,
    )
    mastered, _ = master_track(audio_path, settings=settings)
    mastered_mix = mastered.mean(axis=0)
    mastered_ratio = bass_energy_ratio(mastered_mix, sr)

    assert abs(mastered_ratio - original_ratio) < 0.01


def test_master_track_gentle_mode(tmp_path):
    audio_path = _create_signal(tmp_path)
    settings = MasteringSettings(gentle=True, preserve_bass_ratio=False)
    mastered, _ = master_track(audio_path, settings=settings)

    baseline_settings = MasteringSettings(gentle=False, preserve_bass_ratio=False)
    baseline, _ = master_track(audio_path, settings=baseline_settings)

    gentle_peak = float(np.max(np.abs(mastered)))
    baseline_peak = float(np.max(np.abs(baseline)))
    assert gentle_peak >= baseline_peak
