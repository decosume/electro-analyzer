from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "build_client_profile.py"
)
SPEC = importlib.util.spec_from_file_location("build_client_profile", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
build_profile = MODULE.build_profile


def test_build_profile_emits_weekday_profiles_and_block_config():
    config = {
        "playlist_name": "Duques Daily",
        "description": "Base description",
        "blocks": [
            {"label": "Warmup", "mood": "barbershop_morning", "track_count": 2},
            {"label": "Rush", "mood": "barbershop_afternoon", "track_count": 2},
        ],
        "weekday_blocks": {
            "monday": [
                {
                    "label": "Monday Open",
                    "mood": "barbershop_morning",
                    "track_count": 1,
                },
                {
                    "label": "Monday Peak",
                    "mood": "barbershop_evening",
                    "track_count": 2,
                },
            ]
        },
        "weekday_descriptions": {"monday": "Monday-specific flow"},
        "rotation_bucket": "test_rotation",
        "rotation_count": 2,
    }
    mood_library = {
        "barbershop_morning": [
            {"query": "Morning A", "language": "en"},
            {"query": "Morning B", "language": "en"},
        ],
        "barbershop_afternoon": [
            {"query": "Afternoon A", "language": "en"},
            {"query": "Afternoon B", "language": "en"},
        ],
        "barbershop_evening": [
            {"query": "Evening A", "language": "en"},
            {"query": "Evening B", "language": "en"},
        ],
    }
    rotation_library = {"test_rotation": ["Rotation A", "Rotation B", "Rotation C"]}

    profile = build_profile(
        config,
        mood_library=mood_library,
        rotation_library=rotation_library,
    )

    assert profile["block_config"] == [
        {"label": "Warmup", "count": 2},
        {"label": "Rush", "count": 2},
    ]
    assert profile["rotation_queries"] == ["Rotation A", "Rotation B"]
    assert (
        profile["weekday_profiles"]["monday"]["description"] == "Monday-specific flow"
    )
    assert profile["weekday_profiles"]["monday"]["block_config"] == [
        {"label": "Monday Open", "count": 1},
        {"label": "Monday Peak", "count": 2},
    ]
    assert profile["weekday_profiles"]["monday"]["curated_queries"] == [
        "Morning A",
        "Evening A",
        "Evening B",
    ]
