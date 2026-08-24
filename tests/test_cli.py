import json
from pathlib import Path

import numpy as np
import soundfile as sf
from typer.testing import CliRunner

from electro_analyzer.cli import _apply_block_config
from electro_analyzer.cli import _resolve_target_date
from electro_analyzer.cli import _resolve_weekday_profile
from electro_analyzer.cli import _rotation_seed_for_date
from electro_analyzer.cli import RotationCadence
from electro_analyzer.cli import app
from electro_analyzer.spotify_playlist import BarberShopVibeProfile


def _create_tone(tmp_path: Path, filename: str = "tone.wav", sr: int = 22050) -> Path:
    duration = 1.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    audio = 0.5 * np.sin(2 * np.pi * 440 * t)
    path = tmp_path / filename
    sf.write(path, audio, sr)
    return path


def test_analyze_command_outputs_json(tmp_path):
    audio_path = _create_tone(tmp_path)
    runner = CliRunner()

    result = runner.invoke(app, ["analyze", str(audio_path)])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["track"] == audio_path.name
    assert "bpm" in payload
    assert "key" in payload
    assert "sections" in payload


def test_plot_command_creates_files(tmp_path):
    audio_path = _create_tone(tmp_path)
    output_dir = tmp_path / "plots"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "plot",
            str(audio_path),
            "--out",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    files = list(output_dir.glob("*.png"))
    assert {path.name for path in files} == {
        f"{audio_path.stem}_waveform.png",
        f"{audio_path.stem}_spectrogram.png",
        f"{audio_path.stem}_chroma.png",
    }


def test_apply_block_config_uses_rotation_seed_override():
    profile = BarberShopVibeProfile(
        curated_queries=["a", "b", "c", "d", "e", "f"],
        block_config=[{"label": "one", "count": 3}, {"label": "two", "count": 3}],
    )

    _apply_block_config(profile, rotation_seed=202629)
    first_order = list(profile.curated_queries)

    profile = BarberShopVibeProfile(
        curated_queries=["a", "b", "c", "d", "e", "f"],
        block_config=[{"label": "one", "count": 3}, {"label": "two", "count": 3}],
    )
    _apply_block_config(profile, rotation_seed=202629)
    second_order = list(profile.curated_queries)

    profile = BarberShopVibeProfile(
        curated_queries=["a", "b", "c", "d", "e", "f"],
        block_config=[{"label": "one", "count": 3}, {"label": "two", "count": 3}],
    )
    _apply_block_config(profile, rotation_seed=202631)
    third_order = list(profile.curated_queries)

    assert first_order == second_order
    assert first_order != third_order


def test_rotation_seed_for_date_supports_daily_and_weekly_cadence():
    target = _resolve_target_date("2026-08-24")

    assert _rotation_seed_for_date(target, RotationCadence.DAILY) == 20260824
    assert _rotation_seed_for_date(target, RotationCadence.WEEKLY) == 202635


def test_resolve_weekday_profile_applies_matching_override():
    profile = BarberShopVibeProfile(
        description="Base flow",
        curated_queries=["base-a", "base-b"],
        block_config=[{"label": "base", "count": 2}],
        weekday_profiles={
            "monday": {
                "description": "Monday flow",
                "curated_queries": ["mon-a", "mon-b", "mon-c"],
                "block_config": [{"label": "open", "count": 3}],
            }
        },
    )

    resolved = _resolve_weekday_profile(
        profile,
        target_date=_resolve_target_date("2026-08-24"),
    )

    assert resolved.description == "Monday flow"
    assert list(resolved.curated_queries) == ["mon-a", "mon-b", "mon-c"]
    assert resolved.block_config == [{"label": "open", "count": 3}]


def test_resolve_weekday_profile_falls_back_to_default_override():
    profile = BarberShopVibeProfile(
        description="Base flow",
        curated_queries=["base-a", "base-b"],
        weekday_profiles={
            "default": {
                "description": "Default override",
                "curated_queries": ["default-a"],
            }
        },
    )

    resolved = _resolve_weekday_profile(
        profile,
        target_date=_resolve_target_date("2026-08-26"),
    )

    assert resolved.description == "Default override"
    assert list(resolved.curated_queries) == ["default-a"]
