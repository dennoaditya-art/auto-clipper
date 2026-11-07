from __future__ import annotations

from autoclip.config import RenderConfig
from autoclip.media import VideoInfo, probe
from autoclip.render import RenderError, _blur_fill_graph, _letterbox_filter, render_clip

import pytest


def test_render_vertical_with_subtitles(settings, video):
    transcript = {
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "Halo ini uji coba subtitle."},
            {"start": 2.0, "end": 4.0, "text": "Klip kedua tetap terbaca."},
            {"start": 4.0, "end": 6.0, "text": "Selesai."},
        ]
    }
    result = render_clip(
        video,
        probe(video),
        1.0,
        5.0,
        "Uji Render",
        settings,
        transcript,
        settings.paths.review / "clips",
        source_id=1,
    )
    assert result.path.exists()
    assert result.path.stat().st_size > 0
    assert len(result.sha256) == 64
    info = probe(result.path)
    assert info.width == 1080
    assert info.height == 1920
    assert 3.5 <= info.duration <= 4.5
    assert info.has_audio


def test_letterbox_filter_geometry():
    info = VideoInfo(duration=10, width=854, height=480, has_audio=True, fps=30)
    render = RenderConfig(
        width=1080, height=1920, crf=28, preset="ultrafast", encoder="libx264",
        face_crop=False, face_sample_fps=1.0, subtitles=True, subtitle_max_chars=32,
        subtitle_style="", subtitle_language="id", hook_overlay=True,
        hook_seconds=2.0, emoji_hook=True, zoom_punch=False, loudnorm=True,
    )
    f = _letterbox_filter(info, render)
    assert "scale=1080:608" in f
    assert "pad=1080:1920:0:656" in f


def test_letterbox_filter_handles_4_3():
    info = VideoInfo(duration=10, width=640, height=480, has_audio=True, fps=30)
    render = RenderConfig(
        width=1080, height=1920, crf=28, preset="ultrafast", encoder="libx264",
        face_crop=False, face_sample_fps=1.0, subtitles=True, subtitle_max_chars=32,
        subtitle_style="", subtitle_language="id", hook_overlay=True,
        hook_seconds=2.0, emoji_hook=True, zoom_punch=False, loudnorm=True,
    )
    f = _letterbox_filter(info, render)
    assert "scale=1080:810" in f
    assert "pad=1080:1920:0:555" in f


def test_blur_fill_graph_shape():
    render = RenderConfig(
        width=1080, height=1920, crf=28, preset="ultrafast", encoder="libx264",
        face_crop=False, face_sample_fps=1.0, subtitles=True, subtitle_max_chars=32,
        subtitle_style="", subtitle_language="id", hook_overlay=True,
        hook_seconds=2.0, emoji_hook=True, zoom_punch=False, loudnorm=True,
    )
    graph = _blur_fill_graph(render)
    assert "split=2" in graph
    assert "boxblur" in graph
    assert "overlay=(W-w)/2:(H-h)/2" in graph


def test_render_tiktok_profile_blur_fill(settings, video, monkeypatch):
    """Profil tiktok tidak boleh lagi memakai letterbox hitam."""
    def boom(*args, **kwargs):
        raise AssertionError("profil tiktok tidak boleh memakai letterbox")

    monkeypatch.setattr("autoclip.render._letterbox_filter", boom)
    transcript = {"segments": [{"start": 0.0, "end": 6.0, "text": "Opah nya seram."}]}
    result = render_clip(
        video, probe(video), 1.0, 5.0, "Opah Seram", settings, transcript,
        settings.paths.review / "clips", source_id=1, profile="tiktok",
    )
    info = probe(result.path)
    assert (info.width, info.height) == (1080, 1920)


def test_shorts_profile_does_not_use_letterbox(settings, video, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("profil shorts tidak boleh memakai letterbox")

    monkeypatch.setattr("autoclip.render._letterbox_filter", boom)
    transcript = {"segments": [{"start": 0.0, "end": 6.0, "text": "Halo semua."}]}
    result = render_clip(
        video, probe(video), 1.0, 5.0, "Shorts", settings, transcript,
        settings.paths.review / "clips", source_id=1, profile="shorts",
    )
    assert probe(result.path).height == 1920


def test_profiles_write_separate_files(settings, video):
    transcript = {"segments": [{"start": 0.0, "end": 6.0, "text": "Halo semua."}]}
    shorts = render_clip(
        video, probe(video), 1.0, 5.0, "Bentrok Nama", settings, transcript,
        settings.paths.review / "clips", source_id=1, profile="shorts",
    )
    tiktok = render_clip(
        video, probe(video), 1.0, 5.0, "Bentrok Nama", settings, transcript,
        settings.paths.review / "clips", source_id=1, profile="tiktok",
    )
    assert shorts.path != tiktok.path
    assert tiktok.path.stem.endswith("_tt")


def test_karaoke_filter_is_applied(settings, video, monkeypatch):
    """Subtitle karaoke harus benar-benar masuk filter, bukan cuma ditulis ke file."""
    from autoclip import render as render_module

    captured: dict[str, list[str]] = {}
    real = render_module._encode_command

    def spy(video, output, start, end, filters, *args, **kwargs):
        captured["filters"] = list(filters)
        return real(video, output, start, end, filters, *args, **kwargs)

    monkeypatch.setattr(render_module, "_encode_command", spy)
    transcript = {"segments": [{"start": 0.0, "end": 6.0, "text": "Halo semua."}]}
    render_clip(
        video, probe(video), 1.0, 5.0, "Subtitle Wajib", settings, transcript,
        settings.paths.review / "clips", source_id=1, profile="tiktok",
    )
    assert "ass=sub.ass" in captured["filters"]


def test_unknown_profile_rejected(settings, video):
    with pytest.raises(ValueError, match="profil"):
        render_clip(
            video, probe(video), 1.0, 5.0, "Profil Salah", settings,
            {"segments": [{"start": 1.0, "end": 4.0, "text": "halo"}]},
            settings.paths.review / "clips", source_id=1, profile="layar_lebar",
        )


def test_render_fails_when_subtitles_empty(settings, video):
    """Klip tanpa satu pun cue subtitle tidak boleh tayang."""
    transcript = {"segments": [{"start": 100.0, "end": 102.0, "text": "jauh"}]}
    with pytest.raises(RenderError, match="subtitle kosong"):
        render_clip(
            video,
            probe(video),
            1.0,
            5.0,
            "Tanpa Subtitle",
            settings,
            transcript,
            settings.paths.review / "clips",
            source_id=1,
        )
