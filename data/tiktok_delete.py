"""Hapus posting TikTok Studio berdasarkan potongan caption.

Pakai: python data/_tiktok_delete.py "potongan caption" ["potongan lain" ...]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.tiktok import POSTS_URL, state_path

ROW = '[data-tt="components_RowLayout_FlexRow"]'
ACTION = 'button[data-tt="components_ActionCell_Clickable"]'


def delete_one(page, needle: str) -> bool:
    page.get_by_placeholder("Search for post description").fill(needle)
    page.wait_for_timeout(4000)
    row = page.locator(ROW).filter(has_text=needle)
    if not row.count():
        print("tidak ketemu:", needle)
        return False
    row.first.locator(ACTION).last.click()
    page.wait_for_timeout(1500)
    page.get_by_text("Delete", exact=True).click()
    page.wait_for_timeout(1500)
    confirm = page.get_by_role("button", name="Delete", exact=True)
    if confirm.count():
        confirm.last.click()
        page.wait_for_timeout(2500)
    print("dihapus:", needle)
    return True


def main(argv):
    settings = load_settings(Path(__file__).resolve().parents[1])
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            storage_state=str(state_path(settings)), viewport={"width": 1440, "height": 900}
        )
        page = context.new_page()
        page.goto(POSTS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(9000)
        for needle in argv:
            try:
                delete_one(page, needle)
            except Exception as exc:
                print("gagal hapus", needle, exc)
                page.screenshot(path=f"data/_studio_del_fail_{len(needle)}.png")
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
