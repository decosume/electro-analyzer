from __future__ import annotations

from electro_analyzer.spotify_playlist import BarberShopPlaylistManager
from electro_analyzer.spotify_playlist import _build_insertion_plan
from electro_analyzer.spotify_playlist import _select_rotation_tracks


def test_build_insertion_plan_preserves_gaps_between_local_items():
    plan = _build_insertion_plan(local_positions=[5, 8], total_track_count=10)

    assert plan == [(0, 5), (6, 2), (9, 3)]


def test_build_insertion_plan_without_locals_inserts_all_from_start():
    plan = _build_insertion_plan(local_positions=[], total_track_count=4)

    assert plan == [(0, 4)]


def test_build_insertion_plan_handles_shorter_track_list_than_first_local_gap():
    plan = _build_insertion_plan(local_positions=[5, 8], total_track_count=3)

    assert plan == [(0, 3)]


def test_select_rotation_tracks_returns_full_pool_when_limit_exceeds_unique_tracks():
    selected = _select_rotation_tracks(
        ["a", "b", "a", "c"],
        limit=5,
        week_seed=202629,
    )

    assert selected == ["a", "b", "c"]


def test_select_rotation_tracks_picks_deterministic_weekly_subset():
    rotation_ids = ["a", "b", "c", "d", "e", "f"]

    selected_week_1 = _select_rotation_tracks(rotation_ids, limit=3, week_seed=202629)
    selected_week_1_repeat = _select_rotation_tracks(rotation_ids, limit=3, week_seed=202629)
    selected_week_2 = _select_rotation_tracks(rotation_ids, limit=3, week_seed=202631)

    assert selected_week_1 == selected_week_1_repeat
    assert selected_week_1 == ["b", "c", "d"]
    assert selected_week_2 == ["a", "d", "e"]
    assert len(selected_week_1) == 3
    assert all(track_id in rotation_ids for track_id in selected_week_1)
    assert selected_week_1 != selected_week_2


def test_exclude_artists_filters_matching_tracks():
    manager = object.__new__(BarberShopPlaylistManager)

    def fake_fetch(track_ids):
        return {
            "keep": {"artists": [{"name": "GOTA"}]},
            "drop": {"artists": [{"name": "Jamiroquai"}]},
            "drop2": {"artists": [{"name": "Jamiroquai feat. Someone"}]},
        }

    manager._fetch_track_metadata = fake_fetch  # type: ignore[attr-defined]

    filtered = manager._exclude_artists(  # type: ignore[attr-defined]
        ["keep", "drop", "drop2"],
        ["Jamiroquai"],
    )

    assert filtered == ["keep"]
