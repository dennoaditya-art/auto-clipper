"""Cek baris jadwal terbaru di TikTok Studio > Posts."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.sync_api import sync_playwright

from autoclip import tiktok
from autoclip.config import load_settings

ROOT = Path(__file__).resolve().parents[1]
settings = load_settings(ROOT)
shot = ROOT / "data" / "browser" / "tt_scheduled.png"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(
        storage_state=str(tiktok.state_path(settings)),
        viewport={"width": 1440, "height": 1000},
    )
    page = context.new_page()
    page.goto(tiktok.POSTS_URL + "?tab=scheduled", wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    page.screenshot(path=str(shot), full_page=False)
    print(page.locator("body").inner_text()[:1500])
    context.close()
    browser.close()
print("screenshot:", shot)
