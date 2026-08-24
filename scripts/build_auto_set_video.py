#!/usr/bin/env python3.11
"""Build an automated music-synced video cut from a DJ set and source clips."""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import soundfile as sf
from scipy import signal


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv"}


@dataclass(frozen=True)
class VideoClip:
    path: Path
    duration: float
    width: int
    height: int


@dataclass(frozen=True)
class Segment:
    index: int
    timeline_start: float
    timeline_end: float
    output_duration: float
    clip_name: str
    clip_path: str
    clip_start: float
    clip_end: float
    speed: float
    reverse: bool
    stage: str
    accent: bool
    zoom: float
    pan_x: float
    pan_y: float
    contrast: float
    brightness: float


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, check=True, capture_output=True, text=True)


def probe_video(path: Path) -> VideoClip:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    payload = json.loads(_run(cmd).stdout)
    stream = payload["streams"][0]
    duration = float(payload["format"]["duration"])
    return VideoClip(
        path=path,
        duration=duration,
        width=int(stream["width"]),
        height=int(stream["height"]),
    )


def discover_videos(directory: Path) -> list[VideoClip]:
    candidates = sorted(
        path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
    )
    if not candidates:
        raise SystemExit(f"No video files found in {directory}")
    return [probe_video(path) for path in candidates]


def load_audio(path: Path) -> tuple[np.ndarray, int]:
    audio, sr = sf.read(path)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float64)
    audio = audio - np.mean(audio)
    peak = np.max(np.abs(audio)) or 1.0
    audio = audio / peak
    return audio, sr


def resample_audio(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return audio
    gcd = math.gcd(src_sr, dst_sr)
    return signal.resample_poly(audio, dst_sr // gcd, src_sr // gcd)


def analyze_audio(audio: np.ndarray, sr: int) -> dict[str, object]:
    analysis_sr = 4000
    audio_ds = resample_audio(audio, sr, analysis_sr)

    frame = max(1, int(0.05 * analysis_sr))
    hop = max(1, int(0.01 * analysis_sr))
    window = np.hanning(frame)

    frame_count = 1 + max(0, (len(audio_ds) - frame) // hop)
    energy = np.empty(frame_count)
    times = np.empty(frame_count)

    for index in range(frame_count):
        start = index * hop
        chunk = audio_ds[start : start + frame]
        if len(chunk) < frame:
            chunk = np.pad(chunk, (0, frame - len(chunk)))
        chunk = chunk * window
        energy[index] = np.sqrt(np.mean(chunk**2))
        times[index] = (start + frame / 2) / analysis_sr

    smooth_window = max(5, min(101, (len(energy) // 20) * 2 + 1))
    if smooth_window % 2 == 0:
        smooth_window += 1
    if smooth_window >= len(energy):
        smooth_window = len(energy) - 1 if len(energy) % 2 == 0 else len(energy)
    if smooth_window < 5:
        smooth = energy.copy()
    else:
        smooth = signal.savgol_filter(energy, smooth_window, 3 if smooth_window >= 7 else 1)

    onset = np.maximum(np.diff(smooth, prepend=smooth[0]), 0.0)
    bpm_min = 115.0
    bpm_max = 140.0
    lag_min = int(round((60.0 / bpm_max) / (hop / analysis_sr)))
    lag_max = int(round((60.0 / bpm_min) / (hop / analysis_sr)))
    onset_zero_mean = onset - np.mean(onset)
    autocorr = signal.correlate(onset_zero_mean, onset_zero_mean, mode="full")[len(onset_zero_mean) - 1 :]
    valid = autocorr[lag_min : lag_max + 1]
    best_lag = int(np.argmax(valid)) + lag_min
    bpm = 60.0 / (best_lag * hop / analysis_sr)
    seconds_per_beat = 60.0 / bpm

    prominence = float(np.percentile(onset, 98)) if len(onset) else 0.0
    peaks, properties = signal.find_peaks(
        onset,
        prominence=prominence * 0.25 if prominence > 0 else None,
        distance=max(1, int((seconds_per_beat / 2.0) / (hop / analysis_sr))),
    )
    prominences = properties.get("prominences", np.array([]))
    peak_order = np.argsort(prominences)[::-1][:80] if len(prominences) else []
    accent_times = sorted(float(times[peaks[i]]) for i in peak_order)

    rolling_window = max(1, int(8.0 / (hop / analysis_sr)))
    rolling_energy = np.convolve(energy, np.ones(rolling_window) / rolling_window, mode="same")
    slope = np.gradient(rolling_energy)
    riser_order = np.argsort(slope)[::-1]
    riser_times: list[float] = []
    for idx in riser_order:
        time_value = float(times[idx])
        if all(abs(time_value - existing) > 20.0 for existing in riser_times):
            riser_times.append(time_value)
        if len(riser_times) == 12:
            break

    normalized_energy = energy.copy()
    energy_min = float(np.min(normalized_energy))
    energy_max = float(np.max(normalized_energy))
    if energy_max > energy_min:
        normalized_energy = (normalized_energy - energy_min) / (energy_max - energy_min)
    else:
        normalized_energy = np.zeros_like(normalized_energy)

    return {
        "duration": float(len(audio) / sr),
        "bpm": float(bpm),
        "seconds_per_beat": float(seconds_per_beat),
        "energy_times": times,
        "energy_values": normalized_energy,
        "accent_times": accent_times,
        "riser_times": riser_times,
    }


def stage_for_time(time_value: float, duration: float) -> str:
    ratio = time_value / duration if duration > 0 else 0.0
    if ratio < 0.125:
        return "intro"
    if ratio < 0.25:
        return "groove_a"
    if ratio < 0.375:
        return "lift_a"
    if ratio < 0.5:
        return "peak_a"
    if ratio < 0.625:
        return "breakdown"
    if ratio < 0.75:
        return "industrial"
    if ratio < 0.875:
        return "peak_b"
    return "outro"


def choose_clip(
    stage: str,
    accent: bool,
    videos: dict[str, VideoClip],
    rng: random.Random,
    time_ratio: float,
    outro_bias: float,
) -> VideoClip:
    primary_map = {
        "intro": ["cdmx003", "cdmx001"],
        "groove_a": ["cdmx001", "cdmx004"],
        "lift_a": ["cdmx001", "cdmx005"],
        "peak_a": ["cdmx005", "cdmx004"],
        "breakdown": ["cdmx002", "cdmx003"],
        "industrial": ["cdmx002", "cdmx004"],
        "peak_b": ["cdmx005", "cdmx004"],
        "outro": ["cdmx005", "cdmx003"],
    }
    ordered_names = primary_map.get(stage, list(videos))
    if time_ratio >= 0.82 and "cdmx005" in videos and rng.random() < outro_bias:
        return videos["cdmx005"]
    if accent and len(ordered_names) > 1:
        return videos[ordered_names[1]]
    return videos[ordered_names[0] if rng.random() < 0.7 else ordered_names[min(1, len(ordered_names) - 1)]]


def local_energy(time_value: float, times: np.ndarray, values: np.ndarray) -> float:
    idx = int(np.searchsorted(times, time_value, side="left"))
    idx = max(0, min(idx, len(values) - 1))
    return float(values[idx])


def build_segments(
    videos: list[VideoClip],
    analysis: dict[str, object],
    target_duration: float,
    seed: int,
    timeline_offset: float = 0.0,
    speed_multiplier: float = 1.0,
    outro_bias: float = 0.7,
) -> list[Segment]:
    rng = random.Random(seed)
    duration = float(analysis["duration"])
    beat = float(analysis["seconds_per_beat"])
    energy_times = np.asarray(analysis["energy_times"])
    energy_values = np.asarray(analysis["energy_values"])
    accent_times = list(analysis["accent_times"])
    riser_times = list(analysis["riser_times"])

    video_map = {clip.path.stem: clip for clip in videos}
    cursor_by_clip = {clip.path.stem: 5.0 for clip in videos}
    output_segments: list[Segment] = []

    timeline = 0.0
    index = 0
    while timeline < target_duration - 0.05:
        absolute_time = timeline_offset + timeline
        time_ratio = absolute_time / duration if duration > 0 else 0.0
        stage = stage_for_time(absolute_time, duration)
        energy = local_energy(absolute_time, energy_times, energy_values)
        next_accent = min((value for value in accent_times if value >= absolute_time), default=None)
        is_accent = next_accent is not None and (next_accent - absolute_time) <= beat * 2.0
        is_riser = any(abs(absolute_time - value) <= beat * 4.0 for value in riser_times)

        if is_accent:
            beats = 2 if energy < 0.55 else 1
        elif energy < 0.28:
            beats = 8
        elif energy < 0.55:
            beats = 4
        else:
            beats = 2
        if stage in {"peak_a", "peak_b"} and energy > 0.72:
            beats = 1
        elif stage == "industrial" and energy > 0.60:
            beats = min(beats, 2)

        segment_duration = beats * beat
        if timeline + segment_duration > target_duration:
            segment_duration = target_duration - timeline

        speed = 1.0
        if energy < 0.22:
            speed = 0.82
        elif energy < 0.45:
            speed = 0.96
        elif energy < 0.72:
            speed = 1.08
        else:
            speed = 1.18
        if is_accent:
            speed += 0.12
        if stage in {"peak_a", "peak_b"}:
            speed += 0.06
        elif stage == "breakdown":
            speed -= 0.08
        speed = min(max(speed * speed_multiplier, 0.60), 1.35)

        reverse = False
        if is_riser and rng.random() < 0.34:
            reverse = True
            speed = min(speed + 0.10, 1.50)

        zoom = 1.03
        if energy < 0.28:
            zoom = 1.02
        elif energy < 0.55:
            zoom = 1.05
        elif energy < 0.72:
            zoom = 1.10
        else:
            zoom = 1.16
        if is_accent:
            zoom += 0.03
        if reverse:
            zoom += 0.02
        zoom = min(zoom, 1.22)

        pan_span = min(0.16, max(0.04, (zoom - 1.0) * 1.4))
        stage_pan = {
            "intro": (-0.30, -0.20),
            "groove_a": (-0.18, 0.05),
            "lift_a": (0.12, -0.04),
            "peak_a": (0.28, 0.10),
            "breakdown": (-0.08, 0.18),
            "industrial": (0.20, -0.16),
            "peak_b": (0.30, -0.10),
            "outro": (0.08, 0.22),
        }
        stage_x, stage_y = stage_pan.get(stage, (0.0, 0.0))
        pan_x = max(-1.0, min(1.0, stage_x + rng.uniform(-pan_span, pan_span)))
        pan_y = max(-1.0, min(1.0, stage_y + rng.uniform(-pan_span, pan_span)))

        contrast = 1.10
        brightness = -0.02
        if stage == "breakdown":
            contrast = 1.06
            brightness = -0.06
        elif stage == "industrial":
            contrast = 1.22
            brightness = -0.05
        elif stage in {"peak_a", "peak_b"}:
            contrast = 1.28
            brightness = -0.01
        if is_accent:
            contrast += 0.05
            brightness += 0.01

        clip = choose_clip(stage, is_accent, video_map, rng, time_ratio, outro_bias)
        clip_key = clip.path.stem
        source_duration = max(0.30, min(segment_duration * speed, clip.duration - 0.25))
        clip_start = cursor_by_clip[clip_key]
        if clip_start + source_duration >= clip.duration - 0.25:
            clip_start = 5.0 + rng.random() * max(1.0, clip.duration * 0.15)
        if clip_start + source_duration >= clip.duration - 0.25:
            clip_start = max(0.0, clip.duration - source_duration - 0.25)
        clip_end = min(clip.duration, clip_start + source_duration)
        cursor_by_clip[clip_key] = clip_end + rng.uniform(1.5, 5.0)

        output_segments.append(
            Segment(
                index=index,
                timeline_start=round(timeline, 3),
                timeline_end=round(timeline + segment_duration, 3),
                output_duration=round(segment_duration, 3),
                clip_name=clip.path.name,
                clip_path=str(clip.path),
                clip_start=round(clip_start, 3),
                clip_end=round(clip_end, 3),
                speed=round(speed, 3),
                reverse=reverse,
                stage=stage,
                accent=is_accent,
                zoom=round(zoom, 3),
                pan_x=round(pan_x, 3),
                pan_y=round(pan_y, 3),
                contrast=round(contrast, 3),
                brightness=round(brightness, 3),
            )
        )
        timeline += segment_duration
        index += 1

    return output_segments


def build_filter_script(
    segments: list[Segment],
    videos: list[VideoClip],
    audio_duration: float,
    width: int,
    height: int,
    fps: int,
    spectrogram_height: int,
    visualizer_style: str,
) -> str:
    lines: list[str] = []
    concat_inputs: list[str] = []
    video_index_by_stem = {clip.path.stem: idx + 1 for idx, clip in enumerate(videos)}
    hud_height = max(108, min(180, spectrogram_height))

    for segment in segments:
        input_index = video_index_by_stem[Path(segment.clip_name).stem]
        speed_pts = 1.0 / segment.speed
        scaled_w = max(width, int(math.ceil(width * segment.zoom)))
        scaled_h = max(height, int(math.ceil(height * segment.zoom)))
        crop_x = max(0, scaled_w - width)
        crop_y = max(0, scaled_h - height)
        crop_x_expr = "0"
        crop_y_expr = "0"
        if crop_x > 0:
            crop_x_expr = f"{crop_x / 2:.3f}+({crop_x / 2:.3f})*{segment.pan_x:.3f}"
        if crop_y > 0:
            crop_y_expr = f"{crop_y / 2:.3f}+({crop_y / 2:.3f})*{segment.pan_y:.3f}"
        chain = [
            f"[{input_index}:v]",
            (
                f"trim=start={segment.clip_start:.3f}:end={segment.clip_end:.3f},"
                f"setpts=PTS-STARTPTS,"
            ),
        ]
        if segment.reverse:
            chain.append("reverse,")
        chain.append(
            f"setpts={speed_pts:.6f}*(PTS-STARTPTS),"
            f"scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:{crop_x_expr}:{crop_y_expr},"
            "setsar=1,"
            f"eq=saturation=0:contrast={segment.contrast:.3f}:brightness={segment.brightness:.3f},"
            "unsharp=5:5:0.8:5:5:0.0,"
            f"fps={fps},format=yuv420p[v{segment.index}]"
        )
        lines.append("".join(chain))
        concat_inputs.append(f"[v{segment.index}]")

    lines.append(f"{''.join(concat_inputs)}concat=n={len(segments)}:v=1:a=0[cutv]")
    lines.append(f"[0:a]atrim=0:{audio_duration:.3f},asetpts=PTS-STARTPTS[audio]")

    if visualizer_style == "bars":
        lines.append(
            f"[audio]asplit=2[aout][aviz];"
            f"[aviz]showfreqs=s={width}x{spectrogram_height}:mode=bar:"
            "ascale=log:fscale=log:win_func=hann:cmode=combined:"
            "minamp=0.000001:colors=white,"
            "format=rgba,colorchannelmixer=aa=0.60[viz]"
        )
    elif visualizer_style == "pulse":
        lines.append(
            f"[audio]asplit=2[aout][aviz];"
            f"[aviz]showwaves=s={width}x{spectrogram_height}:mode=cline:"
            f"rate={fps}:scale=sqrt:colors=white,"
            "format=rgba,colorchannelmixer=aa=0.70[viz]"
        )
    elif visualizer_style == "hybrid":
        wave_height = max(48, spectrogram_height // 3)
        bar_height = max(60, spectrogram_height - wave_height)
        lines.append(
            f"[audio]asplit=3[aout][afreq][awave];"
            f"[afreq]showfreqs=s={width}x{bar_height}:mode=bar:"
            "ascale=log:fscale=log:win_func=hann:cmode=combined:"
            "minamp=0.000001:colors=white,"
            "format=rgba,colorchannelmixer=aa=0.48[barviz];"
            f"[awave]showwaves=s={width}x{wave_height}:mode=cline:"
            f"rate={fps}:scale=sqrt:colors=white,"
            "format=rgba,colorchannelmixer=aa=0.78[waveviz];"
            f"color=c=black@0.0:s={width}x{spectrogram_height}:r={fps}[vizbase];"
            "[vizbase][barviz]overlay=0:0[tmpviz];"
            f"[tmpviz][waveviz]overlay=0:{bar_height}[viz]"
        )
    else:
        lines.append(
            f"[audio]asplit=2[aout][aspec];"
            f"[aspec]showspectrum=s={width}x{spectrogram_height}:mode=combined:"
            f"color=intensity:scale=log:legend=0:slide=scroll:fps={fps},"
            "format=rgba,colorchannelmixer=aa=0.35[viz]"
        )

    lines.append(
        "[cutv]drawgrid=width=iw/12:height=ih/8:thickness=1:color=white@0.045,"
        "drawbox=x=0:y=0:w=iw:h=ih:t=2:color=white@0.12,"
        "drawbox=x=0:y=ih-2:w=iw:h=2:t=fill:color=white@0.10,"
        "drawbox=x=0:y=ih-"
        f"{hud_height + 8}:w=iw:h={hud_height + 8}:t=fill:color=black@0.18,"
        "drawbox=x=iw/2-18:y=ih/2-1:w=36:h=2:t=fill:color=white@0.10,"
        "drawbox=x=iw/2-1:y=ih/2-18:w=2:h=36:t=fill:color=white@0.10[gridv]"
    )
    lines.append("[gridv][viz]overlay=0:H-h[vout]")
    return ";\n".join(lines)


def render_video(
    audio_path: Path,
    videos: list[VideoClip],
    segments: list[Segment],
    output_path: Path,
    audio_start: float,
    audio_duration: float,
    fps: int,
    spectrogram_height: int,
    visualizer_style: str,
    video_encoder: str,
    x264_preset: str,
    crf: int,
    video_bitrate: str,
) -> None:
    width = videos[0].width
    height = videos[0].height
    filter_script = build_filter_script(
        segments=segments,
        videos=videos,
        audio_duration=audio_duration,
        width=width,
        height=height,
        fps=fps,
        spectrogram_height=spectrogram_height,
        visualizer_style=visualizer_style,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".ffscript", delete=False) as handle:
        handle.write(filter_script)
        script_path = Path(handle.name)

    try:
        cmd = ["ffmpeg", "-y"]
        if audio_start > 0:
            cmd.extend(["-ss", f"{audio_start:.3f}"])
        cmd.extend(["-t", f"{audio_duration:.3f}", "-i", str(audio_path)])
        for clip in videos:
            cmd.extend(["-i", str(clip.path)])
        cmd.extend(
            [
                "-filter_complex_script",
                str(script_path),
                "-map",
                "[vout]",
                "-map",
                "[aout]",
                "-c:v",
                video_encoder,
            ]
        )
        if video_encoder == "libx264":
            cmd.extend(
                [
                    "-preset",
                    x264_preset,
                    "-crf",
                    str(crf),
                ]
            )
        else:
            cmd.extend(
                [
                    "-b:v",
                    video_bitrate,
                ]
            )
            if video_encoder == "h264_videotoolbox":
                cmd.extend(
                    [
                        "-allow_sw",
                        "1",
                    ]
                )
        cmd.extend(
            [
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-movflags",
                "+faststart",
                "-shortest",
                str(output_path),
            ]
        )
        subprocess.run(cmd, check=True)
    finally:
        script_path.unlink(missing_ok=True)


def write_edl(path: Path, segments: Iterable[Segment], metadata: dict[str, object]) -> None:
    payload = {
        "metadata": metadata,
        "segments": [asdict(segment) for segment in segments],
    }
    path.write_text(json.dumps(payload, indent=2))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True, help="Path to the DJ set WAV/MP3.")
    parser.add_argument(
        "--video-dir",
        type=Path,
        required=True,
        help="Directory containing source video clips.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/auto_set_video.mp4"),
        help="Output MP4 path.",
    )
    parser.add_argument(
        "--edl-out",
        type=Path,
        default=Path("outputs/auto_set_video_edl.json"),
        help="Output JSON edit-decision list path.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=180.0,
        help="Target output duration in seconds. Use 0 to match the whole audio file.",
    )
    parser.add_argument(
        "--audio-start",
        type=float,
        default=0.0,
        help="Start offset in seconds inside the input audio for chunked rendering.",
    )
    parser.add_argument("--seed", type=int, default=7, help="Random seed for deterministic edits.")
    parser.add_argument(
        "--speed-multiplier",
        type=float,
        default=1.0,
        help="Multiply calculated motion speed by this factor. Values below 1 slow the edit.",
    )
    parser.add_argument(
        "--outro-bias",
        type=float,
        default=0.7,
        help="Probability of forcing cdmx005 in the final section when available.",
    )
    parser.add_argument("--fps", type=int, default=30, help="Output frame rate.")
    parser.add_argument(
        "--spectrogram-height",
        type=int,
        default=180,
        help="Height in pixels for the bottom spectrogram overlay.",
    )
    parser.add_argument(
        "--visualizer-style",
        choices=("spectrum", "bars", "pulse", "hybrid"),
        default="hybrid",
        help="Overlay visualizer style.",
    )
    parser.add_argument(
        "--video-encoder",
        choices=("libx264", "h264_videotoolbox"),
        default="libx264",
        help="Video encoder to use.",
    )
    parser.add_argument(
        "--x264-preset",
        default="medium",
        help="libx264 preset when using software encoding.",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=18,
        help="libx264 CRF when using software encoding.",
    )
    parser.add_argument(
        "--video-bitrate",
        default="12M",
        help="Target bitrate for hardware encoding modes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    audio, sr = load_audio(args.audio)
    analysis = analyze_audio(audio, sr)
    videos = discover_videos(args.video_dir)
    total_duration = float(analysis["duration"])
    audio_start = min(max(0.0, args.audio_start), total_duration)
    remaining_duration = max(0.0, total_duration - audio_start)
    target_duration = remaining_duration if args.duration <= 0 else min(args.duration, remaining_duration)
    segments = build_segments(
        videos=videos,
        analysis=analysis,
        target_duration=target_duration,
        seed=args.seed,
        timeline_offset=audio_start,
        speed_multiplier=args.speed_multiplier,
        outro_bias=args.outro_bias,
    )

    metadata = {
        "audio": str(args.audio),
        "video_dir": str(args.video_dir),
        "duration": round(target_duration, 3),
        "audio_start": round(audio_start, 3),
        "estimated_bpm": round(float(analysis["bpm"]), 3),
        "seconds_per_beat": round(float(analysis["seconds_per_beat"]), 3),
        "seed": args.seed,
        "fps": args.fps,
        "segment_count": len(segments),
        "speed_multiplier": args.speed_multiplier,
        "outro_bias": args.outro_bias,
        "visualizer_style": args.visualizer_style,
        "video_encoder": args.video_encoder,
    }
    write_edl(args.edl_out, segments, metadata)
    render_video(
        audio_path=args.audio,
        videos=videos,
        segments=segments,
        output_path=args.out,
        audio_start=audio_start,
        audio_duration=target_duration,
        fps=args.fps,
        spectrogram_height=args.spectrogram_height,
        visualizer_style=args.visualizer_style,
        video_encoder=args.video_encoder,
        x264_preset=args.x264_preset,
        crf=args.crf,
        video_bitrate=args.video_bitrate,
    )
    print(json.dumps(metadata, indent=2))
    print(f"EDL written to {args.edl_out}")
    print(f"Video written to {args.out}")


if __name__ == "__main__":
    main()
