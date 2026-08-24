"""Typer-based command-line interface for Electro Analyzer."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, List, Optional
import random

import librosa
import soundfile as sf
import typer

from .analyzer import AnalysisReport, analyze_track
from .composer import compose_mix
from .generator import generate_techno_track
from .io_utils import derive_output_stem, ensure_directory, resolve_plot_paths
from .mastering import MasteringSettings, master_track
from .plotting import generate_plots
from .spotify_playlist import BarberShopPlaylistManager, BarberShopVibeProfile
from .validators import validate_audio_path

app = typer.Typer(help="Analyze electronic music tracks for key structural features.")


class ModelBackend(str, Enum):
    """Supported analysis backends."""

    LIBROSA = "librosa"
    ESSENTIA = "essentia"


class RotationCadence(str, Enum):
    """Supported cadence options for deterministic playlist rotation."""

    WEEKLY = "weekly"
    DAILY = "daily"


def _normalize_backend(model: ModelBackend) -> str:
    """Convert the enum to the lowercase string expected by the analyzer."""
    backend = model.value.lower()
    if backend != ModelBackend.LIBROSA.value:
        raise typer.BadParameter(f"Backend '{backend}' is not implemented yet.")
    return backend


@app.command()
def analyze(
    audio: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to the audio file to analyze."
    ),
    sr: int = typer.Option(44100, "--sr", help="Target sampling rate for analysis."),
    model: ModelBackend = typer.Option(
        ModelBackend.LIBROSA, "--model", "-m", help="Analysis backend to use."
    ),
) -> None:
    """Analyze an audio file and print a JSON report to stdout."""
    backend = _normalize_backend(model)
    validated_path = validate_audio_path(audio)
    report: AnalysisReport = analyze_track(
        validated_path, sample_rate=sr, backend=backend
    )
    typer.echo(json.dumps(report.to_dict(), indent=2))


@app.command()
def plot(
    audio: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to the audio file to visualize."
    ),
    sr: int = typer.Option(44100, "--sr", help="Target sampling rate for analysis."),
    model: ModelBackend = typer.Option(
        ModelBackend.LIBROSA, "--model", "-m", help="Analysis backend to use."
    ),
    out: Path = typer.Option(
        Path("outputs"), "--out", "-o", help="Directory for generated plots."
    ),
) -> None:
    """Generate waveform, spectrogram, and chroma plots for a track."""
    _normalize_backend(model)
    validated_path = validate_audio_path(audio)

    ensure_directory(out)
    audio_data, sr_loaded = librosa.load(validated_path, sr=sr, mono=True)
    plot_paths = resolve_plot_paths(validated_path, out)
    generate_plots(audio_data, sr_loaded, plot_paths.items())

    typer.echo("Generated plots:")
    for name, path in plot_paths.items():
        typer.echo(f"- {name}: {path}")


def _resolve_master_output(audio: Path, out: Optional[Path]) -> Path:
    """Determine the output path for mastered audio, creating directories if needed."""
    if out is None:
        default_dir = ensure_directory(Path("outputs"))
        return default_dir / f"{derive_output_stem(audio)}_mastered.wav"
    if out.is_dir():
        ensure_directory(out)
        return out / f"{derive_output_stem(audio)}_mastered.wav"
    ensure_directory(out.parent)
    return out


@app.command()
def master(
    audio: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to the audio file to master."
    ),
    sr: int = typer.Option(44100, "--sr", help="Target sampling rate for mastering."),
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        "-o",
        help="Output file or directory for the mastered track (defaults to outputs/).",
    ),
    threshold_db: float = typer.Option(
        -18.0, "--threshold-db", help="Compressor threshold in dBFS."
    ),
    ratio: float = typer.Option(4.0, "--ratio", help="Compressor ratio."),
    target_peak_db: float = typer.Option(
        -1.0,
        "--target-peak-db",
        help="Normalize peaks to this dBFS level before limiting.",
    ),
    limiter_db: float = typer.Option(
        -0.3, "--limiter-db", help="Limiter ceiling in dBFS."
    ),
    pre_emphasis: float = typer.Option(
        0.97,
        "--pre-emphasis",
        help="Pre-emphasis coefficient applied before compression (0 to disable).",
    ),
    bass_target: Optional[float] = typer.Option(
        None,
        "--bass-target",
        help="Optional target bass energy ratio between 0.05 and 0.5.",
    ),
    match_bass: bool = typer.Option(
        True,
        "--match-bass/--no-match-bass",
        help="Preserve the source track's bass balance when mastering.",
    ),
    bass_cutoff: float = typer.Option(
        120.0,
        "--bass-cutoff",
        help="Frequency boundary (Hz) used for bass energy calculations.",
    ),
    gentle: bool = typer.Option(
        False,
        "--gentle",
        help="Use a softer chain (less compression, no pre-emphasis) to preserve transients.",
    ),
) -> None:
    """Apply a lightweight mastering chain and write the processed audio to disk."""
    validated_path = validate_audio_path(audio)
    settings = MasteringSettings(
        sample_rate=sr,
        pre_emphasis=pre_emphasis,
        compressor_threshold_db=threshold_db,
        compressor_ratio=ratio,
        target_peak_db=target_peak_db,
        limiter_ceiling_db=limiter_db,
        bass_balance_target=bass_target,
        bass_cutoff_hz=bass_cutoff,
        preserve_bass_ratio=match_bass,
        gentle=gentle,
    )
    mastered_audio, sample_rate = master_track(validated_path, settings=settings)
    output_path = _resolve_master_output(audio, out)

    data = mastered_audio.T  # convert to shape (samples, channels)
    sf.write(output_path, data, sample_rate)
    typer.echo(f"Mastered file written to: {output_path}")


@app.command()
def compose(
    sources: List[Path] = typer.Argument(
        [],
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        help="Audio files to sample from. Provide zero or more paths.",
    ),
    source_dir: Optional[Path] = typer.Option(
        None,
        "--source-dir",
        exists=True,
        file_okay=False,
        help="Directory containing source audio files.",
    ),
    duration: float = typer.Option(
        300.0,
        "--duration",
        min=60.0,
        help="Target duration for the generated collage in seconds.",
    ),
    bars: int = typer.Option(
        8, "--bars", min=2, max=16, help="Beats-per-segment granularity."
    ),
    bpm: Optional[float] = typer.Option(
        128.0,
        "--target-bpm",
        help="Optional BPM normalization target.",
    ),
    out: Path = typer.Option(
        Path("outputs/techno_collage.wav"),
        "--out",
        help="Destination path for the rendered track.",
    ),
    seed: Optional[int] = typer.Option(
        None,
        "--seed",
        help="Optional random seed for deterministic results.",
    ),
) -> None:
    """Generate a techno-inspired collage by slicing beats from source material."""

    collected: List[Path] = list(sources)
    if source_dir:
        extensions = (".wav", ".mp3", ".flac", ".ogg", ".aiff", ".aif")
        for ext in extensions:
            collected.extend(source_dir.glob(f"*{ext}"))
    unique_sources = [path for path in dict.fromkeys(collected) if path.exists()]
    if not unique_sources:
        raise typer.BadParameter(
            "Provide at least one existing audio file or --source-dir with audio."
        )
    ensure_directory(out.parent)
    audio, sr = compose_mix(
        unique_sources,
        duration=duration,
        target_sr=44100,
        target_bpm=bpm,
        bars=bars,
        seed=seed,
    )
    sf.write(out, audio, sr)
    typer.echo(f"Generated techno collage using {len(unique_sources)} sources → {out}")


@app.command()
def generate(
    duration: float = typer.Option(
        420.0, "--duration", min=60.0, help="Length in seconds."
    ),
    bpm: float = typer.Option(
        124.0, "--bpm", min=80.0, max=140.0, help="Tempo target."
    ),
    out: Path = typer.Option(
        Path("outputs/original_techno.wav"), "--out", help="Output WAV."
    ),
    seed: Optional[int] = typer.Option(None, "--seed", help="Random seed."),
) -> None:
    """Synthesize a fully original techno track via procedural drums and synths."""

    ensure_directory(out.parent)
    audio, sr = generate_techno_track(duration=duration, bpm=bpm, seed=seed)
    sf.write(out, audio, sr)
    typer.echo(f"Generated original techno track at {bpm} BPM → {out}")


def _load_vibe_profile(path: Optional[Path]) -> BarberShopVibeProfile:
    """Load a playlist profile override from JSON if provided."""
    if path is None:
        return BarberShopVibeProfile()
    data = json.loads(path.read_text())
    return BarberShopVibeProfile(**data)


def _normalize_weekday_key(value: str) -> str:
    """Normalize weekday-profile keys for predictable lookup."""
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _resolve_target_date(raw_date: Optional[str]) -> date:
    """Resolve a user-provided date override or default to UTC today."""
    if raw_date is None:
        return datetime.utcnow().date()
    try:
        return date.fromisoformat(raw_date)
    except ValueError as exc:
        raise typer.BadParameter("Date must use YYYY-MM-DD format.") from exc


def _rotation_seed_for_date(
    target_date: date,
    cadence: RotationCadence,
) -> int:
    """Build a deterministic seed for the given date and cadence."""
    if cadence == RotationCadence.DAILY:
        return int(target_date.strftime("%Y%m%d"))
    iso = target_date.isocalendar()
    return iso.year * 100 + iso.week


def _resolve_weekday_profile(
    profile: BarberShopVibeProfile,
    *,
    target_date: date,
) -> BarberShopVibeProfile:
    """Apply optional weekday-specific overrides onto a base profile."""
    weekday_profiles = profile.weekday_profiles or {}
    if not weekday_profiles:
        return profile

    weekday_name = _normalize_weekday_key(target_date.strftime("%A"))
    overrides = weekday_profiles.get(weekday_name) or weekday_profiles.get("default")
    if not overrides:
        return profile

    merged: dict[str, Any] = asdict(profile)
    merged.update(overrides)
    merged["weekday_profiles"] = weekday_profiles
    return BarberShopVibeProfile(**merged)


def _apply_block_config(
    profile: BarberShopVibeProfile,
    *,
    rotation_seed: int | None = None,
) -> None:
    """Reorder curated tracks according to block definitions with weekly variation."""
    config = getattr(profile, "block_config", None)
    if not config:
        return
    curated = list(profile.curated_queries)
    if not curated:
        return
    total = len(curated)
    cursor = 0
    week_seed = rotation_seed if rotation_seed is not None else _weekly_rotation_seed()
    ordered: list[str] = []
    for idx, block in enumerate(config):
        count = int(block.get("count", 0))
        if count <= 0:
            continue
        block_slice = curated[cursor : cursor + count]
        cursor += count
        if not block_slice:
            continue
        rng = random.Random(week_seed + idx * 17)
        rng.shuffle(block_slice)
        ordered.extend(block_slice)
    if cursor < total:
        remainder = curated[cursor:]
        random.Random(week_seed * 19).shuffle(remainder)
        ordered.extend(remainder)
    if ordered:
        profile.curated_queries = ordered


@app.command()
def playlist(
    client_id: str = typer.Option(
        ...,
        "--client-id",
        envvar="SPOTIFY_CLIENT_ID",
        prompt=True,
        help="Spotify client ID.",
    ),
    client_secret: str = typer.Option(
        ...,
        "--client-secret",
        envvar="SPOTIFY_CLIENT_SECRET",
        prompt=True,
        hide_input=True,
        help="Spotify client secret.",
    ),
    redirect_uri: str = typer.Option(
        ...,
        "--redirect-uri",
        envvar="SPOTIFY_REDIRECT_URI",
        prompt=True,
        help="Redirect URI registered with the Spotify app dashboard.",
    ),
    playlist_name: Optional[str] = typer.Option(
        None,
        "--playlist-name",
        help="Override the default Barber Shop playlist name.",
    ),
    public: bool = typer.Option(
        True,
        "--public/--private",
        help="Make the Spotify playlist public.",
    ),
    rotation_tracks: int = typer.Option(
        12,
        "--rotation-tracks",
        min=5,
        max=200,
        help="Number of tracks to draw from the configured rotation pool each refresh.",
    ),
    rotation_seed: Optional[int] = typer.Option(
        None,
        "--rotation-seed",
        help="Override the computed rotation seed to force a different curated/rotation mix.",
    ),
    rotation_cadence: RotationCadence = typer.Option(
        RotationCadence.WEEKLY,
        "--rotation-cadence",
        case_sensitive=False,
        help="Compute deterministic rotation seeds by ISO week or by calendar day.",
    ),
    for_date: Optional[str] = typer.Option(
        None,
        "--for-date",
        help="Resolve weekday overrides and deterministic seeds for a specific YYYY-MM-DD date.",
    ),
    cooldown_days: int = typer.Option(
        3,
        "--cooldown-days",
        min=0,
        help="Skip refreshing if the playlist was updated within this many days.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Ignore the cooldown window and refresh anyway.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Resolve tracks without updating Spotify.",
    ),
    profile_config: Optional[Path] = typer.Option(
        None,
        "--profile-config",
        help="Path to a JSON file overriding the vibe profile.",
    ),
    max_tracks: Optional[int] = typer.Option(
        None,
        "--max-tracks",
        min=1,
        help="Cap the playlist at this many tracks (applied before duration trimming).",
    ),
    target_duration_hours: Optional[float] = typer.Option(
        None,
        "--target-duration-hours",
        min=0.25,
        help="Stop adding tracks once the runtime meets this many hours.",
    ),
) -> None:
    """Create or refresh the confident Barber Shop playlist on Spotify."""
    target_date = _resolve_target_date(for_date)
    resolved_rotation_seed = (
        rotation_seed
        if rotation_seed is not None
        else _rotation_seed_for_date(target_date, rotation_cadence)
    )

    profile = _load_vibe_profile(profile_config)
    profile = _resolve_weekday_profile(profile, target_date=target_date)
    _apply_block_config(profile, rotation_seed=resolved_rotation_seed)
    if playlist_name:
        profile.playlist_name = playlist_name
    profile.public = public
    if max_tracks is not None:
        profile.max_tracks = max_tracks
    if target_duration_hours is not None:
        profile.target_duration_minutes = int(round(target_duration_hours * 60))
    target_duration = (
        timedelta(minutes=profile.target_duration_minutes)
        if profile.target_duration_minutes
        else None
    )

    manager = BarberShopPlaylistManager(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )
    result = manager.refresh_playlist(
        profile,
        rotation_tracks=rotation_tracks,
        rotation_seed=resolved_rotation_seed,
        cooldown=timedelta(days=cooldown_days),
        dry_run=dry_run,
        force=force,
        max_tracks=profile.max_tracks,
        target_duration=target_duration,
    )

    if result.skipped:
        typer.echo(
            f"Skipped refresh for '{result.playlist_name}': {result.reason or 'cooldown active.'}"
        )
        if result.preview:
            typer.echo("Preview of candidate tracks:")
            for name in result.preview:
                typer.echo(f"- {name}")
        if result.runtime_ms:
            typer.echo(f"Resolved runtime: ~{result.runtime_ms / 3600000:.2f}h")
        return

    summary = (
        f"Playlist '{result.playlist_name}' refreshed with {result.track_count} tracks."
    )
    if result.runtime_ms:
        hours = result.runtime_ms / 3600000
        summary += f" (~{hours:.2f}h)"
    typer.echo(summary)
    typer.echo(f"Link: {result.playlist_url}")
    if result.preview:
        typer.echo("First ten tracks:")
        for name in result.preview:
            typer.echo(f"- {name}")


def main() -> None:
    """CLI entrypoint for external callers."""
    app()


if __name__ == "__main__":
    main()
