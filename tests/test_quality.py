import numpy as np
import soundfile as sf

from electro_analyzer.quality import QualityMetrics, assess_quality


def _create_tone(tmp_path, filename="tone.wav", sr=44100):
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = 0.2 * np.sin(2 * np.pi * 220 * t)
    path = tmp_path / filename
    sf.write(path, audio, sr)
    return path


def test_assess_quality_reports_metrics(tmp_path):
    path = _create_tone(tmp_path)
    audio, sr = sf.read(path)
    metrics = assess_quality(audio, sr)

    assert isinstance(metrics, QualityMetrics)
    assert metrics.loudness_lufs < 0
    assert metrics.true_peak_db <= 0
    assert 0 <= metrics.bass_ratio <= 1
