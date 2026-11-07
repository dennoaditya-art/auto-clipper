"""Daftar posting TikTok Studio (tanggal + caption) untuk cek jadwal.

Pakai: python data/tiktok_list.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.tiktok import POSTS_URL, state_path

ROW = '[data-tt="components_RowLayout_FlexRow"]'


def main():
    settings = load_settings(Path(__file__).resolve().parents[1])
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state=str(state_path(settings)),
            viewport={"width": 1440, "height": 900},
        )
        page = context.new_page()
        page.goto(POSTS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(9000)
        for _ in range(8):
            page.mouse.wheel(0, 1600)
            page.wait_for_timeout(1000)
        rows = page.locator(ROW).all_inner_texts()
        print("rows:", len(rows))
        for text in rows:
            print(" ".join(text.split())[:120])
        browser.close()


if __name__ == "__main__":
    main()
