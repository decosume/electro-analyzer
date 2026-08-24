"""Helpers for generating simple social-video reels with FFmpeg."""

from __future__ import annotations

import json
import shlex
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .io_utils import ensure_directory


def _escape_drawtext(value: str) -> str:
    """Escape FFmpeg drawtext content."""
    escaped = value.replace("\\", "\\\\")
    escaped = escaped.replace(":", "\\:")
    escaped = escaped.replace("'", r"\'")
    escaped = escaped.replace("%", r"\%")
    return escaped


@dataclass(frozen=True)
class ReelScene:
    """Single text scene in a vertical reel."""

    headline: str
    body: str
    duration: float


@dataclass(frozen=True)
class ReelSpec:
    """Configuration for a lightweight reel render."""

    title: str
    subtitle: str
    cta: str
    scenes: Sequence[ReelScene]
    image_paths: Sequence[str] = ()
    width: int = 1080
    height: int = 1920
    fps: int = 30
    background_top: str = "#103b3f"
    background_bottom: str = "#071c1d"
    accent: str = "#19e06e"
    text_primary: str = "#f5f4ef"
    text_secondary: str = "#c5d2cc"
    audio_trim_start: float = 0.08
    audio_trim_end: float | None = None

    @property
    def duration(self) -> float:
        return float(sum(scene.duration for scene in self.scenes))


def load_reel_spec(path: Path) -> ReelSpec:
    """Read a reel brief from JSON."""
    data = json.loads(path.read_text())
    scenes = [
        ReelScene(
            headline=str(scene["headline"]),
            body=str(scene["body"]),
            duration=float(scene["duration"]),
        )
        for scene in data["scenes"]
    ]
    return ReelSpec(
        title=str(data["title"]),
        subtitle=str(data["subtitle"]),
        cta=str(data["cta"]),
        scenes=scenes,
        image_paths=tuple(str(path) for path in data.get("image_paths", [])),
        width=int(data.get("width", 1080)),
        height=int(data.get("height", 1920)),
        fps=int(data.get("fps", 30)),
        background_top=str(data.get("background_top", "#103b3f")),
        background_bottom=str(data.get("background_bottom", "#071c1d")),
        accent=str(data.get("accent", "#19e06e")),
        text_primary=str(data.get("text_primary", "#f5f4ef")),
        text_secondary=str(data.get("text_secondary", "#c5d2cc")),
        audio_trim_start=float(data.get("audio_trim_start", 0.08)),
        audio_trim_end=(
            float(data["audio_trim_end"])
            if data.get("audio_trim_end") is not None
            else None
        ),
    )


def _drawtext(
    text: str,
    *,
    x: str,
    y: str,
    fontsize: int,
    fontcolor: str,
    enable: str | None = None,
    box: bool = False,
    boxcolor: str = "black@0.0",
    boxborderw: int = 0,
    line_spacing: int | None = None,
    alpha: str | None = None,
) -> str:
    parts = [
        "drawtext=",
        f"text='{_escape_drawtext(text)}'",
        f"x={x}",
        f"y={y}",
        f"fontsize={fontsize}",
        f"fontcolor={fontcolor}",
    ]
    if enable:
        parts.append(f"enable='{enable}'")
    if box:
        parts.extend(
            [
                "box=1",
                f"boxcolor={boxcolor}",
                f"boxborderw={boxborderw}",
            ]
        )
    if line_spacing is not None:
        parts.append(f"line_spacing={line_spacing}")
    if alpha:
        parts.append(f"alpha={alpha}")
    return ":".join(parts)


def _wrap_text(text: str, width: int) -> str:
    """Wrap text for drawtext so it stays inside the frame."""
    lines = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    return "\n".join(lines) if lines else text


def _line_count(text: str) -> int:
    """Return the number of rendered lines for wrapped text."""
    return max(1, text.count("\n") + 1)


def _build_overlay_chain(spec: ReelSpec, image_input_count: int) -> str:
    """Assemble a filtergraph for the reel."""
    filters: list[str] = [
        f"[0:v]scale={spec.width}:{spec.height}",
        f"format=yuv420p",
        f"drawbox=x=0:y=0:w={spec.width}:h={spec.height}:color={spec.background_bottom}:t=fill",
        f"drawbox=x=0:y=0:w={spec.width}:h=340:color={spec.background_top}@0.94:t=fill",
        f"drawbox=x=56:y=104:w=244:h=48:color={spec.accent}@0.95:t=fill",
        f"drawbox=x=80:y=456:w=164:h=5:color={spec.accent}@0.92:t=fill",
        f"drawbox=x=64:y=520:w=10:h=1020:color={spec.accent}@0.95:t=fill",
        f"drawbox=x=92:y=560:w=548:h=760:color={spec.background_top}@0.34:t=fill",
        f"drawbox=x=92:y=560:w=548:h=760:color={spec.text_secondary}@0.08:t=3",
        f"drawbox=x=686:y=520:w=314:h=800:color={spec.background_top}@0.56:t=fill",
        f"drawbox=x=686:y=520:w=314:h=800:color={spec.text_secondary}@0.08:t=3",
        f"drawbox=x=0:y={spec.height - 190}:w={spec.width}:h=190:color={spec.background_top}@0.72:t=fill",
        _drawtext(
            "DIGITAL MONK",
            x="86",
            y="138",
            fontsize=24,
            fontcolor=spec.background_bottom,
        ),
        _drawtext(
            _wrap_text(spec.title, width=20),
            x="80",
            y="188",
            fontsize=62,
            fontcolor=spec.text_primary,
            line_spacing=8,
        ),
        _drawtext(
            _wrap_text(spec.subtitle, width=42),
            x="80",
            y="366",
            fontsize=26,
            fontcolor=spec.text_secondary,
            line_spacing=8,
        ),
    ]

    scene_count = max(1, len(spec.scenes))
    progress_width = 52
    progress_gap = 18
    progress_y = spec.height - 104
    progress_x = 80
    for idx in range(scene_count):
        x = progress_x + idx * (progress_width + progress_gap)
        filters.append(
            f"drawbox=x={x}:y={progress_y}:w={progress_width}:h=10:color={spec.text_secondary}@0.25:t=fill"
        )

    current = 0.0
    for idx, scene in enumerate(spec.scenes):
        start = current
        end = current + scene.duration
        enable = f"between(t,{start:.2f},{end:.2f})"
        wrapped_headline = _wrap_text(scene.headline, width=16)
        wrapped_body = _wrap_text(scene.body, width=30)
        headline_lines = _line_count(wrapped_headline)
        headline_y = 720
        body_y = headline_y + headline_lines * 66 + 34
        progress_x_scene = progress_x + idx * (progress_width + progress_gap)
        filters.append(
            f"drawbox=x={progress_x_scene}:y={progress_y}:w={progress_width}:h=10:color={spec.accent}@0.98:t=fill:enable='{enable}'"
        )
        filters.append(
            _drawtext(
                f"{idx + 1:02d} / {scene_count:02d}",
                x="104",
                y="640",
                fontsize=22,
                fontcolor=spec.accent,
                enable=enable,
            )
        )
        filters.append(
            _drawtext(
                wrapped_headline,
                x="104",
                y=str(headline_y),
                fontsize=58,
                fontcolor=spec.text_primary,
                enable=enable,
                line_spacing=10,
            )
        )
        filters.append(
            _drawtext(
                wrapped_body,
                x="104",
                y=str(body_y),
                fontsize=30,
                fontcolor=spec.text_secondary,
                enable=enable,
                line_spacing=10,
            )
        )
        current = end

    filters.append(
        _drawtext(
            _wrap_text(spec.cta, width=38),
            x="80",
            y=f"{spec.height - 168}",
            fontsize=32,
            fontcolor=spec.background_bottom,
            box=True,
            boxcolor=spec.accent,
            boxborderw=26,
            line_spacing=10,
        )
    )
    chain = ",".join(filters) + "[base0]"

    image_positions = [
        (708, 568, 270, 214),
        (708, 812, 270, 214),
        (708, 1056, 270, 214),
    ]
    current_label = "base0"
    for idx in range(min(image_input_count, len(image_positions))):
        x, y, width, height = image_positions[idx]
        image_label = f"img{idx}"
        next_label = f"base{idx + 1}"
        chain += (
            f";[{idx + 1}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}[{image_label}]"
            f";[{current_label}][{image_label}]overlay={x}:{y}[{next_label}]"
        )
        current_label = next_label
    return chain + f";[{current_label}]copy[outv]"


def build_reel_command(
    *,
    spec: ReelSpec,
    output_path: Path,
    audio_path: Path | None = None,
) -> list[str]:
    """Return the FFmpeg command used to render a reel."""
    ensure_directory(output_path.parent)

    image_paths = [Path(path) for path in spec.image_paths if Path(path).exists()]
    video_source = (
        f"color=c={spec.background_bottom}:s={spec.width}x{spec.height}:r={spec.fps}:d={spec.duration:.2f}"
    )
    filtergraph = _build_overlay_chain(spec, image_input_count=len(image_paths))

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "lavfi",
        "-i",
        video_source,
    ]

    for image_path in image_paths:
        cmd.extend(["-loop", "1", "-i", str(image_path)])

    if audio_path is not None:
        cmd.extend(["-stream_loop", "-1", "-i", str(audio_path)])

    cmd.extend(
        [
            "-filter_complex",
            filtergraph,
            "-map",
            "[outv]",
            "-t",
            f"{spec.duration:.2f}",
            "-r",
            str(spec.fps),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
        ]
    )

    if audio_path is not None:
        audio_input_index = 1 + len(image_paths)
        trim_start = max(0.0, spec.audio_trim_start)
        trim_end = spec.audio_trim_end
        fade_out_start = max(0.0, spec.duration - 1.5)
        if trim_end is None:
            trim_expr = f"atrim=start={trim_start:.2f}:duration={spec.duration:.2f}"
            audio_filter = (
                f"{trim_expr},asetpts=N/SR/TB,"
                f"afade=t=in:st=0:d=1.0,"
                f"afade=t=out:st={fade_out_start:.2f}:d=1.5"
            )
        else:
            trim_expr = f"atrim=start={trim_start:.2f}:end={trim_end:.2f}"
            loop_window = max(0.5, trim_end - trim_start)
            sample_count = int(44100 * loop_window)
            audio_filter = (
                f"{trim_expr},asetpts=N/SR/TB,"
                f"aloop=loop=-1:size={sample_count},"
                f"atrim=duration={spec.duration:.2f},"
                f"afade=t=in:st=0:d=1.0,"
                f"afade=t=out:st={fade_out_start:.2f}:d=1.5"
            )
        cmd.extend(
            [
                "-map",
                f"{audio_input_index}:a",
                "-af",
                audio_filter,
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-shortest",
            ]
        )
    else:
        cmd.append("-an")

    cmd.append(str(output_path))
    return cmd


def render_reel(
    *,
    spec: ReelSpec,
    output_path: Path,
    audio_path: Path | None = None,
) -> Path:
    """Render the reel to disk."""
    cmd = build_reel_command(spec=spec, output_path=output_path, audio_path=audio_path)
    subprocess.run(cmd, check=True)
    return output_path


def format_command(cmd: Sequence[str]) -> str:
    """Return a shell-safe preview of the FFmpeg command."""
    return " ".join(shlex.quote(part) for part in cmd)
