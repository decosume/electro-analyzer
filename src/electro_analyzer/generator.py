"""Procedural techno generator with lightweight synth voices."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

TAU = 2 * math.pi

PHASE_CONFIG = {
    "intro": {"kick": 0.9, "snare": 0.2, "hat_closed": 0.4, "hat_open": 0.0, "bass": 0.4, "pad": 0.3, "arp": 0.2, "lead": 0.3, "mix": 0.9},
    "groove": {"kick": 1.0, "snare": 0.6, "hat_closed": 0.5, "hat_open": 0.0, "bass": 0.8, "pad": 0.4, "arp": 0.2, "lead": 0.4, "mix": 1.0},
    "build": {"kick": 1.0, "snare": 1.0, "hat_closed": 0.9, "hat_open": 0.3, "bass": 1.0, "pad": 0.7, "arp": 0.6, "lead": 0.7, "mix": 1.0},
    "drop": {"kick": 0.5, "snare": 0.3, "hat_closed": 0.2, "hat_open": 0.0, "bass": 0.2, "pad": 1.0, "arp": 0.9, "lead": 0.8, "mix": 0.7},
    "peak": {"kick": 1.0, "snare": 1.0, "hat_closed": 1.0, "hat_open": 0.9, "bass": 1.0, "pad": 0.9, "arp": 1.0, "lead": 1.0, "mix": 1.0},
    "outro": {"kick": 0.8, "snare": 0.4, "hat_closed": 0.4, "hat_open": 0.0, "bass": 0.5, "pad": 0.6, "arp": 0.6, "lead": 0.3, "mix": 0.85},
}


def _ensure_length(value: int, minimum: int) -> int:
    return max(minimum, int(value))


def _adsr_envelope(
    length: int,
    *,
    sr: int,
    attack: float = 0.005,
    decay: float = 0.05,
    sustain: float = 0.7,
    release: float = 0.1,
) -> np.ndarray:
    attack_n = _ensure_length(attack * sr, 1)
    decay_n = _ensure_length(decay * sr, 1)
    release_n = _ensure_length(release * sr, 1)
    sustain_n = max(length - (attack_n + decay_n + release_n), 0)
    env = np.concatenate(
        [
            np.linspace(0.0, 1.0, attack_n, endpoint=False),
            np.linspace(1.0, sustain, decay_n, endpoint=False),
            np.full(sustain_n, sustain),
            np.linspace(sustain, 0.0, release_n, endpoint=False),
        ]
    )
    if env.size < length:
        env = np.pad(env, (0, length - env.size), mode="constant")
    return env[:length]


def _oscillator(freq: float, length: int, *, sr: int, kind: str = "saw") -> np.ndarray:
    t = np.arange(length) / sr
    if kind == "sine":
        return np.sin(TAU * freq * t)
    if kind == "square":
        return np.sign(np.sin(TAU * freq * t))
    if kind == "noise":
        return np.random.uniform(-1.0, 1.0, size=length)
    # default saw
    phase = np.mod(freq * t, 1.0)
    return 2.0 * phase - 1.0


def _lowpass(signal: np.ndarray, cutoff_hz: float, sr: int) -> np.ndarray:
    rc = 1.0 / (cutoff_hz * 2 * math.pi)
    dt = 1.0 / sr
    alpha = dt / (rc + dt)
    out = np.empty_like(signal)
    prev = 0.0
    for idx, sample in enumerate(signal):
        prev = prev + alpha * (sample - prev)
        out[idx] = prev
    return out


def _synthesize_kick(sr: int) -> np.ndarray:
    length = int(0.8 * sr)
    t = np.arange(length) / sr
    pitch = np.exp(np.linspace(math.log(150), math.log(40), length))
    phase = np.cumsum(pitch) / sr
    body = np.sin(TAU * phase)
    env = np.exp(-t * 10.0)
    click = np.exp(-t * 180.0) * np.sin(TAU * 400 * t)
    return (body * env + click) * 0.9


def _synthesize_snare(sr: int, *, clap_mix: float = 0.5) -> np.ndarray:
    length = int(0.5 * sr)
    noise = _oscillator(0, length, sr=sr, kind="noise")
    env = _adsr_envelope(length, sr=sr, attack=0.001, decay=0.08, sustain=0.1, release=0.1)
    tone = _oscillator(220, length, sr=sr, kind="sine") * env * 0.4
    noisy = _lowpass(noise, cutoff_hz=6000, sr=sr) * env
    clap_noise = _lowpass(_oscillator(0, length, sr=sr, kind="noise"), cutoff_hz=2000, sr=sr) * env
    return noisy * 0.6 + tone + clap_noise * clap_mix


def _synthesize_hihat(sr: int, *, open_hat: bool = False) -> np.ndarray:
    length = int((0.45 if open_hat else 0.15) * sr)
    noise = _oscillator(0, length, sr=sr, kind="noise")
    filtered = noise - _lowpass(noise, cutoff_hz=4000, sr=sr)
    env = _adsr_envelope(
        length,
        sr=sr,
        attack=0.0005,
        decay=0.02 if not open_hat else 0.1,
        sustain=0.0 if not open_hat else 0.2,
        release=0.02 if not open_hat else 0.2,
    )
    return filtered * env * (0.7 if open_hat else 0.5)


def _note_frequency(note: int, root_freq: float = 55.0) -> float:
    return root_freq * (2 ** (note / 12))


def _synthesize_bass_note(note: float, length_samples: int, *, sr: int, detune: float = 0.01) -> np.ndarray:
    freq = _note_frequency(note)
    osc1 = _oscillator(freq, length_samples, sr=sr, kind="saw")
    osc2 = _oscillator(freq * (1 + detune), length_samples, sr=sr, kind="saw")
    osc = (osc1 + osc2) * 0.5
    env = _adsr_envelope(length_samples, sr=sr, attack=0.005, decay=0.08, sustain=0.6, release=0.05)
    tone = _lowpass(osc, cutoff_hz=180, sr=sr) * env
    return tone * 0.75


def _synthesize_pad(note: float, length_samples: int, *, sr: int) -> np.ndarray:
    base = _note_frequency(note)
    osc1 = _oscillator(base, length_samples, sr=sr, kind="saw")
    osc2 = _oscillator(base * 1.01, length_samples, sr=sr, kind="saw")
    osc = (osc1 + osc2) * 0.5
    env = _adsr_envelope(length_samples, sr=sr, attack=0.5, decay=0.5, sustain=0.6, release=0.8)
    filtered = _lowpass(_lowpass(osc, cutoff_hz=1500, sr=sr), cutoff_hz=800, sr=sr)
    return filtered * env * 0.3


def _synthesize_arpeggio(note: float, length_samples: int, *, sr: int) -> np.ndarray:
    base = _note_frequency(note)
    osc = _oscillator(base, length_samples, sr=sr, kind="square")
    env = _adsr_envelope(length_samples, sr=sr, attack=0.01, decay=0.1, sustain=0.4, release=0.1)
    filtered = _lowpass(osc, cutoff_hz=2000, sr=sr)
    return filtered * env * 0.25


def _synthesize_lead(note: float, length_samples: int, *, sr: int) -> np.ndarray:
    base = _note_frequency(note)
    osc1 = _oscillator(base, length_samples, sr=sr, kind="saw")
    osc2 = _oscillator(base * 0.5, length_samples, sr=sr, kind="sine")
    osc = (osc1 * 0.7 + osc2 * 0.3)
    env = _adsr_envelope(length_samples, sr=sr, attack=0.02, decay=0.2, sustain=0.5, release=0.2)
    filtered = _lowpass(osc, cutoff_hz=2500, sr=sr)
    return filtered * env * 0.35


@dataclass
class PatternConfig:
    bpm: float
    duration_seconds: float
    sr: int = 44100
    beats_per_bar: int = 4
    steps_per_beat: int = 4

    @property
    def seconds_per_beat(self) -> float:
        return 60.0 / self.bpm

    @property
    def seconds_per_step(self) -> float:
        return self.seconds_per_beat / self.steps_per_beat

    @property
    def total_steps(self) -> int:
        return int(self.duration_seconds / self.seconds_per_step)

    @property
    def total_samples(self) -> int:
        return int(self.duration_seconds * self.sr)


def _place_sample(buffer: np.ndarray, sample: np.ndarray, start: int) -> None:
    end = min(buffer.size, start + sample.size)
    segment = sample[: end - start]
    buffer[start:end] += segment


def _sequence_indices(pattern: PatternConfig, positions: Iterable[int]) -> Sequence[int]:
    samples_per_step = int(pattern.seconds_per_step * pattern.sr)
    return [min(pattern.total_samples - samples_per_step, idx * samples_per_step) for idx in positions]


def _schedule_phases(steps: int) -> list[str]:
    phase_boundaries = [0.08, 0.35, 0.6, 0.67, 0.9, 1.0]
    phase_names = ["intro", "groove", "build", "drop", "peak", "outro"]
    schedule: list[str] = []
    prev = 0
    for frac, name in zip(phase_boundaries, phase_names):
        target = int(steps * frac)
        schedule.extend([name] * (target - prev))
        prev = target
    if len(schedule) < steps:
        schedule.extend([phase_names[-1]] * (steps - len(schedule)))
    return schedule


def generate_techno_track(
    *,
    duration: float = 420.0,
    bpm: float = 124.0,
    sr: int = 44100,
    root_note: int = 12,
    seed: int | None = None,
) -> tuple[np.ndarray, int]:
    pattern = PatternConfig(bpm=bpm, duration_seconds=duration, sr=sr)
    rng = random.Random(seed)

    drum_buffer = np.zeros(pattern.total_samples, dtype=np.float32)
    bass_buffer = np.zeros_like(drum_buffer)
    pad_buffer = np.zeros_like(drum_buffer)
    arp_buffer = np.zeros_like(drum_buffer)
    lead_buffer = np.zeros_like(drum_buffer)
    fx_buffer = np.zeros_like(drum_buffer)

    kick = _synthesize_kick(sr)
    snare = _synthesize_snare(sr)
    hat_closed = _synthesize_hihat(sr, open_hat=False)
    hat_open = _synthesize_hihat(sr, open_hat=True)

    steps = pattern.total_steps
    schedule = _schedule_phases(steps)

    for step_idx, phase in enumerate(schedule):
        is_downbeat = (step_idx % (pattern.steps_per_beat * pattern.beats_per_bar)) == 0
        is_backbeat = (step_idx % (pattern.steps_per_beat * pattern.beats_per_bar)) == pattern.steps_per_beat * 2
        start_sample = int(step_idx * pattern.seconds_per_step * sr)
        cfg = PHASE_CONFIG.get(phase, PHASE_CONFIG["groove"])
        if step_idx % pattern.steps_per_beat == 0:
            _place_sample(drum_buffer, kick * cfg["kick"], start_sample)
        if phase in {"groove", "build", "drop", "peak"} and is_backbeat and cfg["snare"] > 0:
            _place_sample(drum_buffer, snare * cfg["snare"], start_sample)
        if cfg["hat_closed"] > 0 and step_idx % max(1, pattern.steps_per_beat // 2) == 0:
            _place_sample(drum_buffer, hat_closed * cfg["hat_closed"], start_sample)
        if cfg["hat_open"] > 0 and phase in {"build", "peak"} and step_idx % (pattern.steps_per_beat * 2) == pattern.steps_per_beat:
            _place_sample(drum_buffer, hat_open * cfg["hat_open"], start_sample)

    # Bassline pattern (one note per beat)
    notes = [root_note, root_note + 5, root_note + 7, root_note + 3]
    beat_samples = int(pattern.seconds_per_beat * sr)
    for beat in range(int(pattern.duration_seconds / pattern.seconds_per_beat)):
        phase = schedule[min(beat * pattern.steps_per_beat, steps - 1)]
        cfg = PHASE_CONFIG.get(phase, PHASE_CONFIG["groove"])
        if phase == "intro" and beat < 4:
            continue
        if phase == "drop":
            continue
        note = rng.choice(notes) + rng.choice([-12, 0, 12]) * 0.0
        length = beat_samples
        waveform = _synthesize_bass_note(note, length, sr=sr) * cfg["bass"]
        start = beat * beat_samples
        _place_sample(bass_buffer, waveform, start)

    # Pads during build/peak/outro
    pad_bar_length = int(pattern.beats_per_bar * pattern.seconds_per_beat * sr)
    pad_notes = [root_note + 12, root_note + 3 + 12, root_note + 7 + 12]
    for bar in range(int(pattern.duration_seconds / (pattern.seconds_per_beat * pattern.beats_per_bar))):
        step_idx = bar * pattern.beats_per_bar * pattern.steps_per_beat
        phase = schedule[min(step_idx, steps - 1)]
        if phase == "intro":
            continue
        note = pad_notes[bar % len(pad_notes)]
        cfg = PHASE_CONFIG.get(phase, PHASE_CONFIG["groove"])
        if cfg["pad"] <= 0:
            continue
        waveform = _synthesize_pad(note, pad_bar_length, sr=sr) * cfg["pad"]
        start = bar * pad_bar_length
        _place_sample(pad_buffer, waveform, start)

    # Arpeggio / lead for emotional lift
    arp_steps = pattern.steps_per_beat
    arp_length = int(pattern.seconds_per_beat / 2 * sr)
    arp_notes = [root_note + 19, root_note + 24, root_note + 16]
    for step_idx, phase in enumerate(schedule):
        cfg = PHASE_CONFIG.get(phase, PHASE_CONFIG["groove"])
        if phase not in {"build", "peak", "outro"} or cfg["arp"] <= 0:
            continue
        if phase == "outro" and step_idx % (arp_steps * 4) != 0:
            continue
        start = int(step_idx * pattern.seconds_per_step * sr)
        note = arp_notes[(step_idx // 2) % len(arp_notes)]
        waveform = _synthesize_arpeggio(note, arp_length, sr=sr) * cfg["arp"]
        _place_sample(arp_buffer, waveform, start)

    lead_notes = [root_note + 7, root_note + 14, root_note + 12, root_note + 9]
    lead_length = int(pattern.seconds_per_beat * sr)
    for step_idx, phase in enumerate(schedule):
        cfg = PHASE_CONFIG.get(phase, PHASE_CONFIG["groove"])
        if cfg["lead"] <= 0:
            continue
        if phase not in {"intro", "groove", "build", "peak"}:
            continue
        if step_idx % (pattern.steps_per_beat * 2) != 0:
            continue
        start = int(step_idx * pattern.seconds_per_step * sr)
        note = lead_notes[(step_idx // (pattern.steps_per_beat * 2)) % len(lead_notes)]
        waveform = _synthesize_lead(note, lead_length, sr=sr) * cfg["lead"]
        _place_sample(lead_buffer, waveform, start)

    # Risers / FX at transitions
    transition_steps = [idx for idx in range(1, len(schedule)) if schedule[idx] != schedule[idx - 1]]
    riser_duration = int(pattern.seconds_per_beat * sr * 4)
    for step_idx in transition_steps:
        phase = schedule[step_idx]
        if phase in {"build", "peak", "drop"}:
            start = int(max(0, (step_idx * pattern.seconds_per_step * sr) - riser_duration))
            noise = _synthesize_hihat(sr, open_hat=True)
            riser = np.interp(
                np.linspace(0, noise.size, riser_duration, endpoint=False),
                np.arange(noise.size),
                noise,
            )
            curve = np.linspace(0.2, 1.0, riser_duration)
            if phase == "drop":
                curve = 1.0 - curve * 0.4
            _place_sample(fx_buffer, riser * curve, start)

    # Phase-driven mix automation for darker breakdowns
    phase_mix = np.array([PHASE_CONFIG.get(phase, PHASE_CONFIG["groove"])["mix"] for phase in schedule])
    phase_mix = phase_mix.repeat(int(pattern.seconds_per_step * sr))
    if phase_mix.size < pattern.total_samples:
        phase_mix = np.pad(phase_mix, (0, pattern.total_samples - phase_mix.size), mode="edge")
    else:
        phase_mix = phase_mix[: pattern.total_samples]
    phase_mix = _lowpass(phase_mix, cutoff_hz=2.0, sr=sr)

    mix = drum_buffer + bass_buffer + pad_buffer + arp_buffer + lead_buffer + fx_buffer
    mix = mix * phase_mix
    mix = _lowpass(mix, cutoff_hz=12000, sr=sr)  # soften highs
    peak = np.max(np.abs(mix)) or 1.0
    mix = (mix / peak) * 0.95
    return mix.astype(np.float32), sr
