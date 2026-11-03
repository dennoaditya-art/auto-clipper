from __future__ import annotations

from autoclip.select import _opening_quote, snap_to_speech


def _segments(words):
    """Bangun segmen dengan timing kata dari daftar (start, end, kata)."""
    return [
        {
            "start": words[0][0],
            "end": words[-1][1],
            "text": " ".join(w[2] for w in words),
            "words": [{"s": s, "e": e, "w": t} for s, e, t in words],
        }
    ]


def test_snap_strips_dead_lead_in():
    """Regresi: klip #20 dimulai 16,8s sebelum kata pertama."""
    segs = _segments([(16.83, 17.30, "Sisi"), (17.30, 17.80, "lain")])
    start, end = snap_to_speech(segs, 0.0, 24.0)
    assert start >= 16.5, f"masih ada {start:.2f}s tanpa suara di awal"
    assert start < 16.9


def test_snap_extends_to_finish_sentence():
    """Kalau kata terakhir bukan akhir kalimat, tarik sampai titik."""
    segs = _segments(
        [
            (10.0, 10.4, "Ini"),
            (10.4, 10.9, "kalimat"),
            (10.9, 11.5, "panjang."),
        ]
    )
    _, end = snap_to_speech(segs, 10.0, 10.6)
    assert end >= 11.5, "kalimat terpotong di tengah"


def test_snap_does_not_leave_hanging_cut():
    """Klip #17 kehilangan 0,96s kata terakhir."""
    segs = _segments([(5.0, 5.4, "kata"), (5.4, 6.2, "terakhir.")])
    start, end = snap_to_speech(segs, 5.0, 5.24)
    assert end >= 6.2 - 0.01


def test_opening_quote_uses_spoken_words():
    """Judul harus dari ucapan nyata, bukan hasil karangan."""
    segs = _segments(
        [(0.0, 0.3, "gue"), (0.3, 0.6, "takutnya"), (0.6, 1.0, "digoreng")]
    )
    quote = _opening_quote(segs, 0.0, 20.0)
    assert "gue" in quote.lower()
    assert "digoreng" in quote.lower()


def test_opening_quote_drops_filler_openers():
    segs = _segments([(0.0, 0.3, "guys"), (0.3, 0.7, "mau"), (0.7, 1.0, "nanya")])
    quote = _opening_quote(segs, 0.0, 20.0)
    assert not quote.lower().startswith("guys")


def test_opening_quote_empty_when_no_speech():
    segs = _segments([(30.0, 30.5, "jauh")])
    assert _opening_quote(segs, 0.0, 10.0) == ""
