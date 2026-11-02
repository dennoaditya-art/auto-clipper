from __future__ import annotations

import re

from autoclip.subtitles import clip_karaoke_ass, clip_srt, ts_srt


def test_timestamp_format():
    assert ts_srt(0) == "00:00:00,000"
    assert ts_srt(61.5) == "00:01:01,500"


def test_clip_srt_wraps_and_trims(tmp_path):
    transcript = {
        "segments": [
            {
                "start": 0.0,
                "end": 4.0,
                "text": "Ini kalimat panjang yang harus dibungkus menjadi beberapa baris "
                "supaya subtitle tetap terbaca di layar vertikal.",
            }
        ]
    }
    path = tmp_path / "sub.srt"
    count = clip_srt(transcript, 1.0, 3.0, path, max_chars=24)
    assert count >= 2
    text = path.read_text(encoding="utf-8")
    assert "-->" in text
    cue_lines = [
        line
        for line in text.splitlines()
        if line and "-->" not in line and not line.isdigit()
    ]
    assert all(len(line) <= 24 for line in cue_lines)
    timestamps = [
        line
        for line in text.splitlines()
        if "-->" in line
    ]
    assert timestamps[0].startswith("00:00:00,000")
    assert timestamps[-1].endswith("00:00:02,000")


def test_karaoke_keeps_spaces_between_words(tmp_path):
    """Regresi: tag \\k tanpa spasi membuat kata menempel ('menemukanjalan')."""
    transcript = {
        "segments": [
            {
                "start": 0.0,
                "end": 2.0,
                "text": "akhirnya menemukan jalan",
                "words": [
                    {"s": 0.0, "e": 0.4, "w": "akhirnya"},
                    {"s": 0.4, "e": 0.9, "w": "menemukan"},
                    {"s": 0.9, "e": 1.4, "w": "jalan"},
                ],
            }
        ]
    }
    path = tmp_path / "k.ass"
    assert clip_karaoke_ass(transcript, 0.0, 2.0, path) > 0
    body = path.read_text(encoding="utf-8")
    dialogue = [ln for ln in body.splitlines() if ln.startswith("Dialogue:")]
    assert dialogue
    # buang tag override ASS ({\k40}) lalu lihat teks yang tampil
    visible = [re.sub(r"\{[^}]*\}", "", ln).split(",", 9)[-1] for ln in dialogue]
    # regresi: tiap baris tidak boleh punya kata menempel ("menemukanjalan")
    for line in visible:
        assert "menemukanjalan" not in line
        assert "akhirnyamenemukan" not in line
    # kata dalam satu baris dipisah spasi
    assert "akhirnya menemukan" in visible[0]
