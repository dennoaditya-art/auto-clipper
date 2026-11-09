"""Cetak konteks kata kunci pembatasan di halaman Studio + daftar setelan akun."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.tiktok import state_path

KEYS = ("eligib", "restrict", "violat", "review", "warning", "limited", "penalt", "status")


def ctx(body: str) -> None:
    low = body.lower()
    for k in KEYS:
        start = 0
        while True:
            i = low.find(k, start)
            if i < 0:
                break
            print(f"   [{k}] ...{body[max(0, i - 90):i + 110]}...")
            start = i + len(k)


def main() -> None:
    settings = load_settings(Path(__file__).resolve().parents[1])
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            storage_state=str(state_path(settings)),
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        page.goto("https://www.tiktok.com/tiktokstudio", wait_until="domcontentloaded")
        page.wait_for_timeout(9000)
        print("== studio")
        ctx(" ".join(page.locator("body").inner_text().split()))

        page.goto("https://www.tiktok.com/setting", wait_until="domcontentloaded")
        page.wait_for_timeout(6000)
        print("\n== setelan lengkap")
        print(" ".join(page.locator("body").inner_text().split())[:1200])
        browser.close()


if __name__ == "__main__":
    main()
