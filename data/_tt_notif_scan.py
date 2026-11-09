"""Telusuri seluruh notifikasi TikTok dan cari peringatan pembatasan video.

Pakai: python data/_tt_notif_scan.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.tiktok import state_path

KEYS = (
    "not eligible",
    "ineligible",
    "eligib",
    "limited",
    "restrict",
    "violat",
    "community guideline",
    "for you feed",
    "under review",
    "removed",
    "unoriginal",
    "reused",
)


def main() -> None:
    settings = load_settings(Path(__file__).resolve().parents[1])
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state=str(state_path(settings)),
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        page.goto("https://www.tiktok.com/foryou", wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        page.get_by_text("Activity", exact=True).first.click()
        page.wait_for_timeout(5000)
        page.screenshot(path=str(Path(__file__).parent / "browser" / "notif.png"))

        seen: list[str] = []
        for _ in range(25):
            text = " ".join(page.locator("body").inner_text().split())
            if text not in seen:
                seen.append(text)
            page.mouse.wheel(0, 2200)
            page.wait_for_timeout(1200)
        blob = " ".join(seen)
        low = blob.lower()
        print("panjang teks:", len(blob))
        for k in KEYS:
            i = low.find(k)
            while i >= 0:
                print(f"[{k}] ...{blob[max(0, i - 120):i + 160]}...")
                i = low.find(k, i + len(k))
        browser.close()


if __name__ == "__main__":
    main()
