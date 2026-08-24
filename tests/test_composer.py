from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from electro_analyzer.composer import compose_mix


def _synthesize_loop(path: Path, *, sr: int = 22050, bpm: float = 120.0, bars: int = 8) -> None:
    beats_per_bar = 4
    seconds_per_beat = 60.0 / bpm
    total_beats = beats_per_bar * bars
    duration = seconds_per_beat * total_beats
    samples = int(duration * sr)
    t = np.linspace(0, duration, samples, endpoint=False)
    kick = 0.3 * np.sin(2 * np.pi * 60 * t) * (np.sin(np.pi * np.mod(t, seconds_per_beat) / seconds_per_beat) ** 2)
    hat = 0.15 * np.random.default_rng(0).normal(size=samples)
    audio = kick + hat
    sf.write(path, audio, sr)


def test_compose_mix_builds_output(tmp_path):
    src = tmp_path / "loop.wav"
    _synthesize_loop(src)
    audio, sr = compose_mix([src], duration=30.0, target_bpm=120.0, bars=4, seed=7)
    assert sr == 44100
    assert audio.shape[0] == 44100 * 30
    assert not np.allclose(audio, 0.0)

