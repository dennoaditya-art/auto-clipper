"""Unggah klip ke TikTok lewat TikTok Studio (browser automation).

Kenapa browser, bukan API: Content Posting API mewajibkan audit aplikasi sebelum
bisa posting publik, dan tidak punya field jadwal sama sekali. Studio web punya
keduanya (publik + penjadwalan), memakai sesi login yang sudah ada.

ponytail: selector rapuh terhadap perubahan UI TikTok. Semua selector
dikumpulkan di konstanta di bawah supaya perbaikannya satu tempat.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

from .config import Settings

log = logging.getLogger(__name__)

LOGIN_URL = "https://www.tiktok.com/login"
UPLOAD_URL = "https://www.tiktok.com/tiktokstudio/upload"
POSTS_URL = "https://www.tiktok.com/tiktokstudio/content"

CAPTION_EDITOR = ".public-DraftEditor-content"
# Sejak Nov 2026 panel jadwal memakai Select + wheel picker, bukan input teks.
PICKER_VALUE = "span.Picker__value"
DATE_PANEL = ".DatePicker__panel"
TIME_PANEL = ".TimePicker__panel"
POST_BUTTON = "button.Button__root:has-text('Schedule'), button.Button__root:has-text('Post')"
MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


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
    """Tulis caption lewat keyboard asli, bukan execCommand.

    `execCommand('selectAll')` di dalam evaluate tidak selalu mengosongkan
    editor Draft yang memulihkan draf TikTok; hasilnya caption lama + baru
    menempel jadi satu ("#ezklip#windahbasudara"). Ctrl+A di keyboard asli
    memakai selection milik Draft sendiri sehingga isinya benar-benar diganti.
    """
    editor = page.locator(CAPTION_EDITOR).first
    head = caption.split("#")[0].strip()[:30]
    # Editor Draft dirender ulang setiap kali TikTok selesai memproses video;
    # teks yang diketik terlalu awal hilang tanpa error. Tulis ulang sampai isi
    # benar-benar bertahan.
    for _attempt in range(3):
        editor.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        page.keyboard.insert_text(caption)
        page.wait_for_timeout(1500)
        if not head or editor.inner_text().count(head) == 1:
            return
        page.wait_for_timeout(2000)
    raise TikTokError(f"caption tidak tertulis: {editor.inner_text()[:80]!r}")


def _picker_values(page) -> tuple[str, str]:
    """Teks tombol tanggal & jam saat ini (kosong kalau panel belum tampil)."""
    values = page.locator(PICKER_VALUE)
    if values.count() < 2:
        return "", ""
    return values.nth(0).inner_text().strip(), values.nth(1).inner_text().strip()


def _date_text(day: datetime) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def _pick_time(page, hour: int, minute: int) -> None:
    """Pilih jam & menit dari wheel picker TikTok.

    Angka yang sama muncul di kolom jam dan menit, jadi opsi diklik lewat
    `role=option` + aria-label ("Hours 19" / "Minutes 30"), bukan teks.
    """
    trigger = page.locator(PICKER_VALUE).nth(1)
    target = f"{hour:02d}:{minute:02d}"

    for _attempt in range(3):
        trigger.click()
        page.locator(TIME_PANEL).wait_for(timeout=10_000)
        page.get_by_role("option", name=f"Hours {hour:02d}", exact=True).click()
        page.wait_for_timeout(300)
        page.get_by_role("option", name=f"Minutes {minute:02d}", exact=True).click()
        page.wait_for_timeout(500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        if trigger.inner_text().strip() == target:
            return
    raise TikTokError(f"jam tidak terpasang: {trigger.inner_text().strip()} != {target}")


def _pick_date(page, day: datetime) -> None:
    """Pilih tanggal dari kalender picker TikTok (navigasi per bulan)."""
    trigger = page.locator(PICKER_VALUE).nth(0)
    # kolom tanggal baru muncul setelah panel jadwal selesai dirender
    trigger.wait_for(timeout=20_000)
    want = _date_text(day)

    for _attempt in range(2):
        if trigger.inner_text().strip() == want:
            return
        trigger.click()
        page.locator(DATE_PANEL).wait_for(timeout=10_000)
        for _ in range(24):
            month = page.locator(".DatePicker__titleMonth").inner_text().strip()
            year = int(page.locator(".DatePicker__titleYear").inner_text().strip())
            if (year, MONTHS.index(month)) == (day.year, day.month - 1):
                break
            forward = (year, MONTHS.index(month)) < (day.year, day.month - 1)
            arrow = "Next month" if forward else "Previous month"
            page.get_by_role("button", name=arrow).click()
            page.wait_for_timeout(300)
        else:
            raise TikTokError("bulan kalender tidak tercapai")

        # hari bisa dobel saat bulan berikutnya meluber ke grid; aria-label unik
        page.get_by_role(
            "button",
            name=re.compile(
                rf"^[A-Za-z]+, {day:%B} {day.day}(st|nd|rd|th), {day.year}$"
            ),
        ).click()
        page.wait_for_timeout(500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    raise TikTokError(
        f"tanggal tidak terpasang: {trigger.inner_text().strip()} != {want}"
    )


def _wait_schedule_ready(page, when: datetime) -> None:
    """Pastikan jam & tanggal bertahan sebelum menunggu tombol aktif.

    Panel jadwal bisa ter-render ulang saat TikTok selesai memproses video,
    mengembalikan jam ke nilai default. Pasang ulang sampai nilainya stabil.
    """
    want = (_date_text(when), when.strftime("%H:%M"))
    for _ in range(4):
        _pick_date(page, when)
        _pick_time(page, when.hour, when.minute)
        page.wait_for_timeout(1200)
        open_panels = page.locator(f"{DATE_PANEL}:visible, {TIME_PANEL}:visible")
        if open_panels.count():
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
        if _picker_values(page) == want and open_panels.count() == 0:
            return
    raise TikTokError(f"jadwal tidak stabil: {_picker_values(page)} != {want}")


def _handle_dialogs(page, timeout: float = 15.0) -> None:
    """Tangani modal TikTok yang muncul saat panel jadwal dibuka.

    Dua modal berbeda bisa muncul berurutan dan keduanya punya tombol Cancel:
    - "Turn on automatic content checks?" -> jangan ubah setelan akun, Cancel.
    - "Allow your video to be saved for scheduled posting?" -> harus Allow.
    """
    deadline = time.time() + timeout
    selector = (
        "[role=dialog]:visible, [role=alertdialog]:visible, .common-modal-body:visible"
    )
    while time.time() < deadline:
        dialog = page.locator(selector)
        if not dialog.count():
            page.wait_for_timeout(400)
            continue
        # modal TikTok memakai portal tanpa role, jadi teks semua kandidat digabung
        text = " ".join(dialog.all_inner_texts()).lower()
        if "automatic content checks" in text:
            if os.environ.get("AUTOCLIP_TIKTOK_CONTENT_CHECK") == "on":
                # dipakai sekali untuk membaca vonis kelayakan For You dari TikTok
                page.get_by_role("button", name="Turn on").first.click(force=True)
            else:
                page.get_by_role("button", name="Cancel").first.click(force=True)
        elif "scheduled posting" in text:
            page.get_by_role("button", name="Allow").first.click(force=True)
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(800)


def _clip_video(clip) -> str:
    """Varian TikTok (letterbox) kalau ada; kalau tidak, file utama."""
    try:
        chosen = clip["tiktok_path"]
    except (IndexError, KeyError):
        chosen = None
    return str(chosen or clip["file_path"])


def publish_clip(
    settings: Settings,
    clip,
    caption: str,
    when: datetime | None,
    *,
    headless: bool = False,
) -> str:
    """Unggah satu klip; jadwalkan kalau `when` diisi, kalau None terbit sekarang."""
    video = Path(str(_clip_video(clip)))
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
            # TikTok mengisi deskripsi dengan nama file begitu unggahan selesai;
            # caption yang ditulis sebelum itu tertimpa nama file.
            try:
                page.wait_for_function(
                    "name => document.querySelector('.public-DraftEditor-content')"
                    "?.innerText.includes(name)",
                    arg=Path(video).stem,
                    timeout=180_000,
                )
            except Exception:
                log.warning("nama file tidak muncul di deskripsi; lanjut saja")
            page.wait_for_timeout(1500)
            _dismiss_tour(page)
            # modal "Turn on automatic content checks?" muncul tepat setelah
            # unggahan selesai dan menutupi editor caption
            _handle_dialogs(page, 4.0)

            # Tunggu tombol aksi aktif: itu tanda TikTok selesai memproses video.
            # Sebelum titik ini editor caption masih bisa di-render ulang dan
            # menghapus teks yang baru diketik.
            from playwright.sync_api import expect as _expect

            _expect(page.locator(POST_BUTTON).first).to_be_enabled(timeout=480_000)
            _set_caption(page, caption)
            # dropdown saran hashtag muncul dan menutupi tombol Schedule
            page.keyboard.press("Escape")
            page.wait_for_timeout(400)
            _dismiss_tour(page)

            if when is not None:
                page.locator("label:has-text('Schedule')").first.click(force=True)
                page.wait_for_timeout(1200)
                _handle_dialogs(page, 6.0)
                # klik ulang: modal tadi bisa membatalkan pilihan radio
                if page.locator("input.Radio__input[value=schedule]").is_checked() is False:
                    page.locator("label:has-text('Schedule')").first.click(force=True)
                    page.wait_for_timeout(800)
                _handle_dialogs(page, 10.0)

                _pick_date(page, when)
                _pick_time(page, when.hour, when.minute)
                _wait_schedule_ready(page, when)

            # tombol Schedule baru aktif setelah video selesai diproses TikTok;
            # mengklik saat masih disabled tidak melakukan apa pun.
            _dismiss_tour(page)
            if os.environ.get("AUTOCLIP_TIKTOK_CONTENT_CHECK") == "on":
                page.wait_for_timeout(10_000)
                dump = settings.root / "data/browser/tiktok_checks.txt"
                dump.write_text(page.locator("body").inner_text(), encoding="utf-8")
                page.screenshot(path=str(dump.with_suffix(".png")), full_page=True)
            button = page.locator(POST_BUTTON).first
            from playwright.sync_api import expect

            expect(button).to_be_enabled(timeout=480_000)
            if caption.split("#")[0].strip()[:30] not in page.locator(
                CAPTION_EDITOR
            ).first.inner_text():
                raise TikTokError("caption tertimpa nama file sebelum posting")
            button.click()
            try:
                page.wait_for_url(
                    lambda url: "/upload" not in url, timeout=120_000
                )
            except Exception:
                # sekali lagi: klik pertama kadang hanya menutup tooltip
                expect(button).to_be_enabled(timeout=60_000)
                button.click()
                page.wait_for_url(
                    lambda url: "/upload" not in url, timeout=120_000
                )
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
