"""Unggah klip ke TikTok lewat TikTok Studio (browser automation).

Kenapa browser, bukan API: Content Posting API mewajibkan audit aplikasi sebelum
bisa posting publik, dan tidak punya field jadwal sama sekali. Studio web punya
keduanya (publik + penjadwalan), memakai sesi login yang sudah ada.

ponytail: selector rapuh terhadap perubahan UI TikTok. Semua selector
dikumpulkan di konstanta di bawah supaya perbaikannya satu tempat.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from .config import Settings

log = logging.getLogger(__name__)

LOGIN_URL = "https://www.tiktok.com/login"
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
POSTS_URL = "https://www.tiktok.com/tiktokstudio/content"

CAPTION_EDITOR = ".public-DraftEditor-content"
TIME_LIST = ".tiktok-timepicker-option-list"
POST_BUTTON = "button.Button__root:has-text('Schedule'), button.Button__root:has-text('Post')"


class TikTokError(RuntimeError):
    pass


def state_path(settings: Settings) -> Path:
    return settings.root / "data" / "tiktok_state.json"


def authorize(settings: Settings, *, timeout_seconds: int = 900) -> Path:
    """Buka browser, tunggu login, simpan sesi ke state_path."""
    from playwright.sync_api import sync_playwright

    target = state_path(settings)
    target.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1200, "height": 800})
        page = context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded")
        print("Login TikTok di jendela yang terbuka...", flush=True)
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if any(c["name"] == "sessionid" for c in context.cookies()):
                context.storage_state(path=str(target))
                print(f"sesi tersimpan: {target}", flush=True)
                context.close()
                browser.close()
                return target
            time.sleep(2)
        context.close()
        browser.close()
        raise TikTokError("login tidak terdeteksi sebelum waktu habis")


def _dismiss_tour(page) -> None:
    """Tutup tur React Joyride + modal promo yang menutupi tombol."""
    page.evaluate(
        """() => {
            const portal = document.querySelector('#react-joyride-portal');
            if (portal) portal.remove();
            document.querySelectorAll('.react-joyride__overlay').forEach(n => n.remove());
        }"""
    )
    for name in ("Got it", "Got it!", "OK"):
        button = page.get_by_role("button", name=name, exact=True)
        if button.count():
            button.first.click(force=True)
            page.wait_for_timeout(500)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            break


def _set_caption(page, caption: str) -> None:
    page.evaluate(
        """(text) => {
            const ed = document.querySelector('.public-DraftEditor-content');
            ed.focus();
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            document.execCommand('insertText', false, text);
        }""",
        caption,
    )


def _pick_time(page, hour: int, minute: int) -> None:
    """Pilih jam & menit dari dropdown timepicker TikTok.

    Klik lewat DOM, bukan koordinat: list jam/menit bisa ter-scroll sehingga
    klik berbasis posisi mendarat di angka yang salah.
    """
    inputs = page.locator("input.TUXTextInputCore-input").nth(0)
    target = f"{hour:02d}:{minute:02d}"

    def choose(index: int, label: str) -> None:
        page.evaluate(
            """([idx, text]) => {
                const lists = document.querySelectorAll('.tiktok-timepicker-option-list');
                const list = lists[idx];
                if (!list) return;
                const item = [...list.children].find(n => n.innerText.trim() === text);
                if (item) item.click();
            }""",
            [index, label],
        )
        page.wait_for_timeout(500)

    for _attempt in range(3):
        inputs.click()
        page.wait_for_timeout(600)
        choose(1, f"{minute:02d}")
        choose(0, f"{hour:02d}")
        value = inputs.input_value()
        if value == target:
            return
    raise TikTokError(f"jam tidak terpasang: {inputs.input_value()} != {target}")


def _handle_dialogs(page, timeout: float = 15.0) -> None:
    """Tangani modal TikTok yang muncul saat panel jadwal dibuka.

    Dua modal berbeda bisa muncul berurutan dan keduanya punya tombol Cancel:
    - "Turn on automatic content checks?" -> jangan ubah setelan akun, Cancel.
    - "Allow your video to be saved for scheduled posting?" -> harus Allow.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        dialog = page.locator("[role=dialog]:visible, [role=alertdialog]:visible")
        if not dialog.count():
            page.wait_for_timeout(400)
            continue
        text = (dialog.first.inner_text() or "").lower()
        if "automatic content checks" in text:
            page.get_by_role("button", name="Cancel").first.click(force=True)
        elif "scheduled posting" in text:
            page.get_by_role("button", name="Allow").first.click(force=True)
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(800)


def _pick_date(page, day: datetime) -> None:
    """Pilih tanggal lewat kalender picker."""
    inputs = page.locator("input.TUXTextInputCore-input")
    # field tanggal baru muncul setelah panel jadwal selesai dirender
    inputs.nth(1).wait_for(timeout=20_000)
    stamp = day.strftime("%Y-%m-%d")
    if inputs.nth(1).input_value() == stamp:
        return
    inputs.nth(1).click()
    page.wait_for_timeout(600)
    cell = page.locator(
        f"[class*='calendar'] [class*='day']:text-is('{day.day}'), "
        f"[class*='DatePicker'] [class*='day']:text-is('{day.day}')"
    )
    cell.first.click(force=True)
    page.wait_for_timeout(400)
    if inputs.nth(1).input_value() != stamp:
        raise TikTokError(
            f"tanggal tidak terpasang: {inputs.nth(1).input_value()} != {stamp}"
        )


def publish_clip(
    settings: Settings,
    clip,
    caption: str,
    when: datetime,
    *,
    headless: bool = False,
) -> str:
    """Unggah satu klip dan jadwalkan. Mengembalikan keterangan status."""
    video = Path(str(clip["file_path"]))
    if not video.exists():
        raise TikTokError(f"file klip hilang: {video}")

    from playwright.sync_api import sync_playwright

    state = state_path(settings)
    if not state.exists():
        raise TikTokError(
            f"sesi TikTok belum ada: {state}. "
            "Jalankan: python -m autoclip auth tiktok"
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(storage_state=str(state), viewport={"width": 1440, "height": 900})
        page = context.new_page()
        try:
            page.goto(UPLOAD_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(4000)
            if "login" in page.url:
                raise TikTokError("sesi TikTok kedaluwarsa; jalankan auth tiktok")
            _dismiss_tour(page)

            page.get_by_role("button", name="Select video", exact=True).click()
            page.locator("input[type=file]").set_input_files(str(video))

            # tunggu proses unggah selesai: editor caption muncul
            page.wait_for_selector(CAPTION_EDITOR, timeout=180_000)
            page.wait_for_timeout(3000)
            _dismiss_tour(page)

            _set_caption(page, caption)
            # dropdown saran hashtag muncul dan menutupi tombol Schedule
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
            _dismiss_tour(page)

            page.locator("label:has-text('Schedule')").first.click(force=True)
            page.wait_for_timeout(1200)
            _handle_dialogs(page, 6.0)
            # klik ulang: modal tadi bisa membatalkan pilihan radio
            if page.locator("input[name=postSchedule][value=schedule]").is_checked() is False:
                page.locator("label:has-text('Schedule')").first.click(force=True)
                page.wait_for_timeout(800)
            _handle_dialogs(page, 10.0)

            _pick_date(page, when)
            _pick_time(page, when.hour, when.minute)

            page.locator(POST_BUTTON).first.click(force=True)
            page.wait_for_timeout(6000)
            if "/upload" in page.url:
                raise TikTokError("jadwal tidak terkirim (masih di halaman upload)")
            return page.url
        except Exception:
            shot = settings.root / "data" / "browser" / "tiktok_error.png"
            shot.parent.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(shot), full_page=True)
                log.warning("screenshot kegagalan: %s", shot)
            except Exception:
                pass
            raise
        finally:
            context.close()
            browser.close()
