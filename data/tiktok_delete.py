"""Hapus posting TikTok Studio (terjadwal/terbit) berdasarkan caption atau tanggal.

Pakai:
    python data/tiktok_delete.py "potongan caption"
    python data/tiktok_delete.py --date "Nov 11" --date "Nov 12"

Kenapa perlu: tidak ada API untuk menghapus posting terjadwal, dan salah jadwal
hanya bisa dibetulkan lewat UI Studio. Selector dikumpulkan di konstanta.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.tiktok import POSTS_URL, state_path

ROW = '[data-tt="components_RowLayout_FlexRow"]'
ACTION = 'button[data-tt="components_ActionCell_Clickable"]'


def _delete_first(page, needle: str) -> bool:
    page.get_by_placeholder("Search for post description").fill(needle)
    page.wait_for_timeout(4000)
    row = page.locator(ROW).filter(has_text=needle)
    if not row.count():
        return False
    row.first.locator(ACTION).last.click()
    page.wait_for_timeout(1200)
    page.get_by_text("Delete", exact=True).click()
    page.wait_for_timeout(1200)
    confirm = page.get_by_role("button", name="Delete", exact=True)
    if confirm.count():
        confirm.last.click()
    page.wait_for_timeout(2500)
    return True


def _delete_by_date(page, label: str, limit: int = 20) -> int:
    removed = 0
    page.mouse.wheel(0, -20000)
    page.wait_for_timeout(800)
    for _ in range(limit):
        row = page.locator(ROW).filter(has_text=label)
        if not row.count():
            break
        row.first.locator(ACTION).last.click()
        page.wait_for_timeout(1200)
        page.get_by_text("Delete", exact=True).click()
        page.wait_for_timeout(1200)
        confirm = page.get_by_role("button", name="Delete", exact=True)
        if confirm.count():
            confirm.last.click()
        page.wait_for_timeout(2500)
        removed += 1
    return removed


def main(argv):
    dates = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--date"]
    captions = [arg for arg in argv if not arg.startswith("--") and arg not in dates]
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
        for caption in captions:
            print(caption, "dihapus" if _delete_first(page, caption) else "tidak ketemu")
        for round_index in range(5):
            total = sum(_delete_by_date(page, label) for label in dates)
            if total == 0:
                break
            print("ronde", round_index + 1, "total", total)
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1:])
