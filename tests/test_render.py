from __future__ import annotations

from autoclip.media import probe
from autoclip.render import RenderError, render_clip

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
