#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOOD_LIBRARY = ROOT / "profiles" / "mood_library.json"
DEFAULT_ROTATION_LIBRARY = ROOT / "profiles" / "rotation_library.json"


def normalize_language_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if not total:
        return {}
    return {lang: value / total for lang, value in weights.items()}


def resolve_entries(entries: list[Any]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for entry in entries:
        if isinstance(entry, str):
            resolved.append({"query": entry})
        elif isinstance(entry, dict) and "query" in entry:
            resolved.append(entry)
    return resolved


def _build_block_queries(
    blocks: list[dict[str, Any]],
    *,
    mood_library: dict[str, Any],
    language_weights: dict[str, float] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    curated: list[str] = []
    block_config: list[dict[str, Any]] = []

    for block in blocks:
        mood = block["mood"]
        count = block.get("track_count", 15)
        entries = mood_library.get(mood)
        if not entries:
            raise KeyError(f"Mood '{mood}' not found in mood library.")
        curated.extend(
            select_tracks(entries, count=count, language_weights=language_weights)
        )
        block_config.append(
            {
                "label": block.get("label", mood),
                "count": count,
            }
        )

    return curated, block_config


def select_tracks(
    entries: list[dict[str, Any]],
    *,
    count: int,
    language_weights: dict[str, float] | None = None,
) -> list[str]:
    if not entries or count <= 0:
        return []

    entries = resolve_entries(entries)
    if not language_weights:
        queue = deque(entries)
        picks: list[str] = []
        while queue and len(picks) < count:
            picks.append(queue.popleft()["query"])
        if len(picks) < count:
            pool = [entry["query"] for entry in entries]
            while pool and len(picks) < count:
                picks.append(pool[len(picks) % len(pool)])
        return picks[:count]

    weights = normalize_language_weights(language_weights)
    targets = {lang: int(round(weight * count)) for lang, weight in weights.items()}
    diff = count - sum(targets.values())
    if diff > 0:
        for lang in sorted(weights, key=weights.get, reverse=True):
            targets[lang] += 1
            diff -= 1
            if diff == 0:
                break

    lang_queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    fallback = deque()
    for entry in entries:
        lang = entry.get("language") or "any"
        if lang in weights or lang == "any":
            lang_queues[lang].append(entry)
        else:
            fallback.append(entry)

    picks: list[str] = []

    def pop_from(lang: str) -> dict[str, Any] | None:
        if lang in lang_queues and lang_queues[lang]:
            entry = lang_queues[lang].popleft()
            lang_queues[lang].append(entry)
            return entry
        if fallback:
            entry = fallback.popleft()
            fallback.append(entry)
            return entry
        for q in lang_queues.values():
            if q:
                entry = q.popleft()
                q.append(entry)
                return entry
        return None

    for lang, target in targets.items():
        for _ in range(max(0, target)):
            entry = pop_from(lang)
            if entry is None:
                break
            picks.append(entry["query"])
            if len(picks) == count:
                return picks

    while len(picks) < count:
        entry = pop_from("any")
        if entry is None:
            break
        picks.append(entry["query"])

    return picks[:count]


def build_profile(
    config: dict[str, Any],
    *,
    mood_library: dict[str, Any],
    rotation_library: dict[str, Any],
) -> dict[str, Any]:
    language_weights = config.get("language_weights")
    curated, block_config = _build_block_queries(
        config.get("blocks", []),
        mood_library=mood_library,
        language_weights=language_weights,
    )

    rotation_queries: list[str] = []
    rotation_key = config.get("rotation_bucket")
    if rotation_key:
        bucket = rotation_library.get(rotation_key)
        if not bucket:
            raise KeyError(f"Rotation bucket '{rotation_key}' not found.")
        rotation_count = config.get("rotation_count", len(bucket))
        rotation_queries.extend(bucket[:rotation_count])
    rotation_queries.extend(config.get("extra_rotation_queries", []))

    profile = {
        "playlist_name": config["playlist_name"],
        "description": config.get("description", ""),
        "public": config.get("public", True),
        "curated_queries": curated,
        "block_config": block_config,
        "rotation_queries": rotation_queries,
        "seed_genres": config.get("seed_genres", []),
    }
    if config.get("max_tracks") is not None:
        profile["max_tracks"] = config["max_tracks"]
    if config.get("target_duration_minutes") is not None:
        profile["target_duration_minutes"] = config["target_duration_minutes"]
    weekday_blocks = config.get("weekday_blocks") or {}
    if weekday_blocks:
        weekday_profiles: dict[str, dict[str, Any]] = {}
        weekday_descriptions = config.get("weekday_descriptions") or {}
        for weekday_name, weekday_config in weekday_blocks.items():
            weekday_curated, weekday_block_config = _build_block_queries(
                weekday_config,
                mood_library=mood_library,
                language_weights=language_weights,
            )
            weekday_override: dict[str, Any] = {
                "curated_queries": weekday_curated,
                "block_config": weekday_block_config,
            }
            if weekday_name in weekday_descriptions:
                weekday_override["description"] = weekday_descriptions[weekday_name]
            weekday_profiles[weekday_name] = weekday_override
        profile["weekday_profiles"] = weekday_profiles
    return profile


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a playlist profile from a business brief."
    )
    parser.add_argument(
        "config", type=Path, help="Path to the high-level client config (JSON)."
    )
    parser.add_argument(
        "--out",
        "-o",
        type=Path,
        required=True,
        help="Output path for the generated profile JSON.",
    )
    parser.add_argument(
        "--moods",
        type=Path,
        default=DEFAULT_MOOD_LIBRARY,
        help="Mood library JSON (default: profiles/mood_library.json).",
    )
    parser.add_argument(
        "--rotations",
        type=Path,
        default=DEFAULT_ROTATION_LIBRARY,
        help="Rotation buckets JSON (default: profiles/rotation_library.json).",
    )
    args = parser.parse_args()

    config = json.loads(args.config.read_text())
    mood_library = json.loads(args.moods.read_text())
    rotation_library = json.loads(args.rotations.read_text())

    profile = build_profile(
        config, mood_library=mood_library, rotation_library=rotation_library
    )
    args.out.write_text(json.dumps(profile, indent=2))
    print(f"Profile written to {args.out}")


if __name__ == "__main__":
    main()
