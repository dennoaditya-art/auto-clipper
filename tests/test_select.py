from __future__ import annotations

from autoclip.select import (
    _candidate_from_llm,
    _overlap_ratio,
    select_clips,
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
