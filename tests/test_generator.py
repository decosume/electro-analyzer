from __future__ import annotations

import numpy as np

from electro_analyzer.generator import generate_techno_track


def test_generate_techno_track_length_and_content():
    audio, sr = generate_techno_track(duration=30.0, bpm=120.0, seed=1)
    assert sr == 44100
    assert audio.shape[0] == 30 * sr
    assert not np.allclose(audio, 0.0)
