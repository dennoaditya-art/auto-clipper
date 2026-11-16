"""Dump mentah baris TikTok Studio + status tab (diagnosa 0 views).

Pakai: python data/_tt_dump_rows.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.tiktok import POSTS_URL, state_path

ROW = '[data-tt="components_RowLayout_FlexRow"]'

settings = load_settings(Path(__file__).resolve().parents[1])
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(
        storage_state=str(state_path(settings)), viewport={"width": 1440, "height": 900}
    )
    page = ctx.new_page()
    page.goto(POSTS_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    print("URL:", page.url)
    print("TITLE:", page.title())
    # tab yang tersedia (Published / Scheduled / Draft)
    for tab in page.locator('[role="tab"], button[role="tab"]').all_inner_texts():
        print("TAB:", " ".join(tab.split()))
    page.wait_for_timeout(1000)
    rows = page.locator(ROW)
    print("rows:", rows.count())
    for i in range(rows.count()):
        text = " ".join(rows.nth(i).inner_text().split())
        print(f"ROW{i}: {text}")
    body = page.locator("body").inner_text()
    for key in ("Scheduled", "Draft", "Gagal", "Failed", "Under review", "Diproses"):
        if key in body:
            print("ADA TEKS:", key)
    page.screenshot(path="data/browser/tt_studio_posts.png", full_page=False)
    browser.close()
