"""Verifikasi semua posting TikTok terjadwal muncul di Studio (lewat pencarian).

Pakai: python data/tiktok_verify.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.db import connect, get_clip
from autoclip.publish import _clip_transcript, _tiktok_caption
from autoclip.tiktok import POSTS_URL, state_path

ROW = '[data-tt="components_RowLayout_FlexRow"]'
CLOCK = '[data-tt="components_PublishStageLabel_FlexCenter"] svg'


def _search_needle(caption: str) -> str:
    """Potongan caption tanpa hashtag dan emoji.

    Pencarian Studio tidak cocok kalau kata kunci memuat emoji, jadi emoji
    dibuang dulu; 40 karakter pertama tetap unik per klip.
    """
    meme = caption.split("#", 1)[0]
    clean = "".join(c for c in meme if ord(c) < 0x2100)
    return clean.strip()[:40]


def main():
    root = Path(__file__).resolve().parents[1]
    settings = load_settings(root)
    conn = connect(settings.paths.database)
    rows = conn.execute(
        "SELECT scheduled_at, clip_id FROM publications"
        " WHERE platform='tiktok' AND status='published'"
        " AND scheduled_at >= '2026-11-07T00:00:00Z' ORDER BY scheduled_at"
    ).fetchall()
    if not rows:
        print("tidak ada publikasi TikTok terjadwal")
        return

    captions = {}
    for _, clip_id in rows:
        clip = get_clip(conn, int(clip_id))
        caption = _tiktok_caption(settings, conn, clip, _clip_transcript(settings, conn, clip))
        captions[int(clip_id)] = _search_needle(caption)

    from playwright.sync_api import sync_playwright

    problems = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state=str(state_path(settings)),
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        page.goto(POSTS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(9000)
        for scheduled, clip_id in rows:
            needle = captions[int(clip_id)]
            page.get_by_placeholder("Search for post description").fill(needle)
            page.wait_for_timeout(3500)
            matches = page.locator(ROW).filter(has_text=needle).count()
            status = "?"
            if matches == 1:
                row = page.locator(ROW).filter(has_text=needle).first
                # ikon jam di label tanggal = masih terjadwal; tanpa ikon = sudah tayang
                status = "terjadwal" if row.locator(CLOCK).count() else "tayang"
            print(scheduled, "clip", clip_id, "->", matches, "baris |", status, "|", needle)
            if matches != 1:
                problems.append((int(clip_id), matches, needle))
        browser.close()

    print("SELESAI; masalah:", problems or "tidak ada")


if __name__ == "__main__":
    main()
