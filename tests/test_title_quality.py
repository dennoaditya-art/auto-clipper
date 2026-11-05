from __future__ import annotations

from autoclip.select import _caption_title, _usable_title


def test_usable_title_rejects_truncated_quote():
    assert not _usable_title("Baru aja sarapan, buat")
    assert not _usable_title("Dulu tuh kita sebutnya handshake event. Jadi")
    assert not _usable_title("Boleh. Ada satu film favoritku yang kalau misalnya aku tonton")


def test_usable_title_accepts_complete_sentence():
    assert _usable_title("Cerita pas tak sengaja ketemu oshi idaman cuma berjarak 5 sentimeter")
    assert _usable_title("Karyawan Paling Nyebelin di Kantor")


def test_usable_title_rejects_too_short():
    assert not _usable_title("Center Lagi!")
    assert not _usable_title("")


def test_caption_title_strips_hashtags_and_takes_first_sentence():
    caption = "Panik beneran, ngakak. Kalian pernah gak kehilangan barang? #Insiden #Panik"
    title = _caption_title(caption)
    assert "#" not in title
    assert title.startswith("Panik beneran")
    assert _usable_title(title)
