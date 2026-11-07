from __future__ import annotations

from autoclip.select import (
    _candidate_from_llm,
    _overlap_ratio,
    _shape_bounds,
    heat_candidates,
    select_clips,
    snap_to_speech,
)

TEXTS = [
    "Kesalahan terbesar pebisnis pemula adalah takut menaikkan harga. Ini rahasia yang jarang dibahas.",
    "Jadi solusinya, hitung ulang nilai pelanggan dan margin. Hasilnya omzet naik.",
    "Kebanyakan orang fokus diskon. Padahal strategi branding lebih penting.",
    "Makanya saya bilang, jangan pernah bersaing di harga. Intinya diferensiasi.",
    "Contohnya bisnis kopi ini. Awalnya rugi, akhirnya profit setelah ubah positioning.",
]


def make_transcript(duration: float = 180.0) -> dict:
    segments = []
    index = 0
    start = 0.0
    while start < duration:
        segments.append(
            {
                "start": start,
                "end": min(duration, start + 3.5),
                "text": TEXTS[index % len(TEXTS)],
            }
        )
        index += 1
        start += 4.0
    return {"duration": duration, "segments": segments}


def test_heuristic_selection_valid(settings):
    account = settings.accounts[0]
    candidates = select_clips(
        make_transcript(), settings, account, provider="heuristic"
    )
    assert 1 <= len(candidates) <= 3
    for candidate in candidates:
        assert 20 <= candidate.duration <= 60
        assert candidate.title
        assert candidate.final_score() >= settings.selection.min_score
    for i, first in enumerate(candidates):
        for second in candidates[i + 1 :]:
            assert _overlap_ratio(first, second) <= 0.2


def test_llm_candidate_clamped(settings):
    account = settings.accounts[0]
    candidate = _candidate_from_llm(
        {
            "start": 5,
            "end": 900,
            "topic": "bisnis",
            "title": "Judul",
            "scores": {"hook": 120, "payoff": 80},
        },
        100.0,
        settings.selection,
        account.niche,
    )
    assert candidate is not None
    assert candidate.end == 65.0
    assert candidate.scores["hook"] == 100.0
    assert candidate.scores["clarity"] == 50.0


def test_llm_candidate_invalid_timestamp(settings):
    account = settings.accounts[0]
    assert (
        _candidate_from_llm(
            {"start": 200, "end": 240},
            100.0,
            settings.selection,
            account.niche,
        )
        is None
    )


def _speech(start: float, end: float, words_per_second: float = 2.0) -> list[dict]:
    """Segmen bersambung dengan timing kata, untuk uji batas klip."""
    segments = []
    t = start
    while t < end - 0.01:
        w_end = min(end, t + 0.5)
        segments.append(
            {
                "start": t,
                "end": w_end,
                "text": "kata ",
                "words": [{"s": t, "e": w_end, "w": "kata"}],
            }
        )
        t = w_end
    return segments


def test_payoff_within_last_8_seconds(settings):
    """Ekornya tidak boleh lebih dari 8 detik setelah punchline."""
    from dataclasses import replace

    cfg = replace(
        settings.selection, min_duration_seconds=22, max_duration_seconds=45
    )
    segments = _speech(0.0, 80.0)
    _, payoff_end = snap_to_speech(segments, 60.0, 63.0)
    start, end = _shape_bounds(segments, 60.0, 63.0, cfg)
    assert end - payoff_end <= 8.0
    assert 22 <= end - start <= 45


def test_clip_respects_max_duration(settings):
    segments = _speech(0.0, 60.0)
    start, end = _shape_bounds(segments, 30.0, 33.0, settings.selection)
    assert end - start <= settings.selection.max_duration_seconds


def test_shape_bounds_does_not_backfill_dead_air(settings):
    """Konteks sebelum hook tidak boleh menarik klip 12 detik ke belakang."""
    lone = {
        "start": 48.0,
        "end": 49.0,
        "text": "kata",
        "words": [{"s": 48.0, "e": 49.0, "w": "kata"}],
    }
    segments = _speech(0.0, 30.0) + [lone] + _speech(60.0, 100.0)
    start, _ = _shape_bounds(segments, 60.0, 63.0, settings.selection)
    assert start >= 58.0


def test_heat_candidate_finds_dense_window_inside_bucket(settings):
    """Bucket heatmap 50 detik: ambil kluster bicara padat, bukan awal bucket."""
    segments = _speech(105.0, 110.0) + _speech(135.0, 165.0)
    candidates = heat_candidates(
        segments, 170.0, settings.selection, "hiburan", [(100.0, 150.2, 1.0)]
    )
    assert len(candidates) == 1
    assert candidates[0].start >= 134.0
