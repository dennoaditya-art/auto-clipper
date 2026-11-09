"""Cari status pembatasan akun di halaman web TikTok yang masih ada.

Pakai: python data/_tt_probe.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.tiktok import state_path

URLS = [
    "https://www.tiktok.com/tiktokstudio/account-health",
    "https://www.tiktok.com/tiktokstudio/analytics/content",
    "https://www.tiktok.com/setting/account",
    "https://www.tiktok.com/setting",
    "https://www.tiktok.com/creator-center/account-status",
    "https://www.tiktok.com/tiktokstudio",
]

KEYS = ("eligib", "restrict", "violat", "review", "warning", "limited", "penalt")


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
        for url in URLS:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(6000)
                body = " ".join(page.locator("body").inner_text().split())
            except Exception as exc:  # noqa: BLE001
                print(f"\n== {url}\n   GAGAL: {exc}")
                continue
            hits = [k for k in KEYS if k in body.lower()]
            print(f"\n== {url}\n   akhir: {page.url}\n   kunci: {hits}\n   isi: {body[:260]}")
        browser.close()


if __name__ == "__main__":
    main()
