from __future__ import annotations

from pathlib import Path

from electro_analyzer.social_video import ReelScene, ReelSpec, build_reel_command


def test_build_reel_command_includes_local_audio_when_present(tmp_path: Path) -> None:
    out = tmp_path / "reel.mp4"
    audio = tmp_path / "bed.mp3"
    audio.write_bytes(b"fake")
    spec = ReelSpec(
        title="Title",
        subtitle="Subtitle",
        cta="CTA",
        scenes=[ReelScene(headline="Hook", body="Body", duration=3.0)],
    )

    cmd = build_reel_command(spec=spec, output_path=out, audio_path=audio)

    assert cmd[0] == "ffmpeg"
    assert str(audio) in cmd
    assert "-stream_loop" in cmd
    assert "-af" in cmd
    assert str(out) == cmd[-1]


def test_build_reel_command_disables_audio_when_missing(tmp_path: Path) -> None:
    out = tmp_path / "reel.mp4"
    spec = ReelSpec(
        title="Title",
        subtitle="Subtitle",
        cta="CTA",
        scenes=[ReelScene(headline="Hook", body="Body", duration=3.0)],
    )

    cmd = build_reel_command(spec=spec, output_path=out, audio_path=None)

    assert "-an" in cmd
