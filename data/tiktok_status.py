"""Cek status satu posting TikTok: terjadwal vs sudah tayang.

Pakai: python data/tiktok_status.py "kata kunci 1" "kata kunci 2"
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.tiktok import POSTS_URL, state_path

ROW = '[data-tt="components_RowLayout_FlexRow"]'


def main(argv):
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
        for needle in argv:
            page.get_by_placeholder("Search for post description").fill(needle)
            page.wait_for_timeout(4000)
            rows = page.locator(ROW).filter(has_text=needle).all_inner_texts()
            print("==", needle, "->", len(rows), "baris")
            for text in rows:
                print("   ", " | ".join(text.split("\n")))
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
