"""Cetak statistik views TikTok terbaru dari TikTok Studio.

Pakai: python data/tiktok_report.py [--headless] [--days 7]
Butuh sesi login: python -m autoclip auth tiktok
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.tiktok import POSTS_URL, TikTokError, state_path
from autoclip.tiktok_report import parse_content_rows, summarize


def fetch_rows(settings, *, headless: bool = False) -> list[dict]:
    from playwright.sync_api import sync_playwright

    state = state_path(settings)
    if not state.exists():
        raise TikTokError(f"sesi TikTok belum ada: {state}. Jalankan: python -m autoclip auth tiktok")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            storage_state=str(state), viewport={"width": 1440, "height": 900}
        )
        page = context.new_page()
        try:
            page.goto(POSTS_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(6000)
            if "login" in page.url:
                raise TikTokError("sesi TikTok kedaluwarsa; jalankan auth tiktok")
            text = page.inner_text("body")
        finally:
            browser.close()
    return parse_content_rows(text)


def main(argv: list[str]) -> int:
    settings = load_settings(Path(__file__).resolve().parents[1])
    headless = "--headless" in argv
    rows = fetch_rows(settings, headless=headless)
    stats = summarize(rows)
    print(f"n={stats['n']} median={stats['median']} max={stats['max']}")
    for row in rows:
        print(f"{row['views']:>8}  {row['when']:<20}  {row['caption'][:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
