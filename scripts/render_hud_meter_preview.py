#!/usr/bin/env python3.11
"""Render a techno HUD meter overlay preview for a video segment."""

from __future__ import annotations

import os
os.environ.setdefault("NUMBA_CACHE_DIR", tempfile.gettempdir() if "tempfile" in globals() else "/tmp")
os.environ.setdefault("MPLCONFIGDIR", "/tmp")

import argparse
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np
from PIL import Image, ImageDraw, ImageFont


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--logo", type=Path, required=True)
    parser.add_argument("--start", type=float, required=True)
    parser.add_argument("--duration", type=float, default=20.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1632)
    parser.add_argument("--height", type=int, default=972)
    parser.add_argument("--fps", type=int, default=30)
    return parser.parse_args()


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def gradient_row(width: int) -> np.ndarray:
    stops = np.array(
        [
            [57, 255, 0],
            [125, 255, 0],
            [219, 255, 58],
            [255, 189, 35],
            [255, 79, 0],
        ],
        dtype=np.float32,
    )
    x = np.linspace(0.0, 1.0, width)
    anchors = np.linspace(0.0, 1.0, len(stops))
    out = np.zeros((width, 3), dtype=np.uint8)
    for channel in range(3):
        out[:, channel] = np.interp(x, anchors, stops[:, channel]).astype(np.uint8)
    return out


def vertical_fade(width: int, height: int, alpha_top: int, alpha_bottom: int) -> Image.Image:
    fade = np.zeros((height, width, 4), dtype=np.uint8)
    alpha = np.linspace(alpha_top, alpha_bottom, height).astype(np.uint8)
    fade[:, :, 3] = alpha[:, None]
    return Image.fromarray(fade, "RGBA")


def smooth(values: np.ndarray, window: int) -> np.ndarray:
    if window <= 1:
        return values
    kernel = np.ones(window, dtype=np.float32) / window
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")[: len(values)]


def normalize(values: np.ndarray, lo: float = 0.08, hi: float = 0.98) -> np.ndarray:
    vmin = float(np.min(values))
    vmax = float(np.max(values))
    if math.isclose(vmin, vmax):
        return np.full_like(values, lo)
    norm = (values - vmin) / (vmax - vmin)
    return lo + norm * (hi - lo)


def load_logo(path: Path, target_width: int) -> Image.Image:
    logo = Image.open(path).convert("RGBA")
    arr = np.array(logo)
    rgb = arr[:, :, :3].astype(np.float32)
    luminance = rgb.max(axis=2)
    alpha = np.clip((luminance - 8.0) * 1.35, 0, 255).astype(np.uint8)
    rgba = np.zeros_like(arr)
    rgba[:, :, :3] = 255
    rgba[:, :, 3] = alpha
    keyed = Image.fromarray(rgba, "RGBA")
    scale = target_width / keyed.width
    return keyed.resize((target_width, int(keyed.height * scale)), Image.Resampling.LANCZOS)


def draw_text_center(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, font: ImageFont.FreeTypeFont) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((x - tw / 2, y - th / 2), text, fill=(240, 240, 240, 230), font=font)


def build_overlay_frames(
    audio_path: Path,
    logo_path: Path,
    frames_dir: Path,
    width: int,
    height: int,
    fps: int,
    duration: float,
) -> None:
    audio, sr = librosa.load(audio_path, sr=22050, mono=True)
    hop_length = max(256, int(sr / fps))
    rms = librosa.feature.rms(y=audio, frame_length=2048, hop_length=hop_length)[0]
    spec = np.abs(librosa.stft(audio, n_fft=2048, hop_length=hop_length))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    bass_mask = (freqs >= 25) & (freqs <= 140)
    mid_mask = (freqs >= 140) & (freqs <= 2000)
    bass = spec[bass_mask].mean(axis=0)
    overall = spec[mid_mask].mean(axis=0) * 0.65 + rms[: spec.shape[1]] * 0.35

    total_frames = int(round(duration * fps))
    times = np.linspace(0.0, duration, total_frames, endpoint=False)
    feature_times = np.arange(len(rms)) * hop_length / sr
    bass_interp = np.interp(times, feature_times[: len(bass)], bass)
    overall_interp = np.interp(times, feature_times[: len(overall)], overall)
    bass_values = smooth(normalize(bass_interp, 0.12, 0.98), 7)
    overall_values = smooth(normalize(overall_interp, 0.10, 0.96), 9)

    frames_dir.mkdir(parents=True, exist_ok=True)
    font_path = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
    title_font = ImageFont.truetype(font_path, 34)
    value_font = ImageFont.truetype(font_path, 24)
    logo = load_logo(logo_path, target_width=470)
    gradient = gradient_row(1150)

    top_left_x = 34
    top_left_y = 42
    bar_left = 310
    hud_panel_top = 430
    bar_top_1 = 560
    bar_gap = 94
    bar_height = 40
    bar_width = gradient.shape[0]

    for index in range(total_frames):
        frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        # Branding block.
        draw.rectangle(
            (
                top_left_x - 12,
                top_left_y - 10,
                top_left_x + logo.width + 18,
                top_left_y + logo.height + 18,
            ),
            fill=(0, 0, 0, 96),
        )
        frame.alpha_composite(logo, (top_left_x, top_left_y))

        # Replace the baked-in lower visualizer with a soft fade instead of a hard block.
        fade = vertical_fade(width, height - hud_panel_top, alpha_top=18, alpha_bottom=248)
        frame.alpha_composite(fade, (0, hud_panel_top))

        # Labels.
        draw_text_center(draw, bar_left + int(bar_width * 0.10), bar_top_1 - 54, "10", value_font)
        draw_text_center(draw, bar_left + int(bar_width * 0.50), bar_top_1 - 54, "50", value_font)
        draw_text_center(draw, bar_left + int(bar_width * 0.985), bar_top_1 - 54, "100%", value_font)
        draw.text((bar_left - 170, bar_top_1 + 4), "BASS", fill=(235, 235, 235, 210), font=title_font)
        draw.text((bar_left - 170, bar_top_1 + bar_gap + 4), "ENERGY", fill=(235, 235, 235, 210), font=title_font)

        # Reactive bars.
        for row, value in enumerate((bass_values[index], overall_values[index])):
            y = bar_top_1 + row * bar_gap
            draw.rounded_rectangle(
                (bar_left, y, bar_left + bar_width, y + bar_height),
                radius=8,
                fill=(20, 20, 20, 205),
                outline=(155, 155, 155, 70),
                width=2,
            )

            active_w = max(6, int(bar_width * float(value)))
            strip = np.zeros((bar_height, active_w, 4), dtype=np.uint8)
            strip[:, :, :3] = gradient[:active_w][None, :, :]
            strip[:, :, 3] = 255
            fill = Image.fromarray(strip, "RGBA")
            frame.alpha_composite(fill, (bar_left, y))

            glow = Image.new("RGBA", (active_w, bar_height), (255, 255, 255, 0))
            glow_draw = ImageDraw.Draw(glow)
            glow_draw.rounded_rectangle(
                (0, 0, active_w - 1, bar_height - 1),
                radius=8,
                outline=(255, 255, 255, 42),
                width=2,
            )
            frame.alpha_composite(glow, (bar_left, y))

        frame.save(frames_dir / f"frame_{index:04d}.png")


def main() -> None:
    args = parse_args()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        audio_path = tmp / "segment.wav"
        frames_dir = tmp / "frames"
        overlay_path = tmp / "overlay.mov"

        run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{args.start:.3f}",
                "-t",
                f"{args.duration:.3f}",
                "-i",
                str(args.video),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "22050",
                str(audio_path),
            ]
        )

        build_overlay_frames(
            audio_path=audio_path,
            logo_path=args.logo,
            frames_dir=frames_dir,
            width=args.width,
            height=args.height,
            fps=args.fps,
            duration=args.duration,
        )

        run(
            [
                "ffmpeg",
                "-y",
                "-framerate",
                str(args.fps),
                "-i",
                str(frames_dir / "frame_%04d.png"),
                "-c:v",
                "qtrle",
                str(overlay_path),
            ]
        )

        args.output.parent.mkdir(parents=True, exist_ok=True)
        run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{args.start:.3f}",
                "-t",
                f"{args.duration:.3f}",
                "-i",
                str(args.video),
                "-i",
                str(overlay_path),
                "-filter_complex",
                "[0:v][1:v]overlay=0:0",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "20",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                str(args.output),
            ]
        )


if __name__ == "__main__":
    main()
