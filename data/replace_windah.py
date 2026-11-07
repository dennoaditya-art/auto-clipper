"""Ganti video Windah lama dengan render baru (watermark & batas diperbaiki).

Urutan aman: unggah dulu, baru hapus video lama. Kalau kuota habis, skrip
berhenti tanpa menghapus apa pun dan bisa dijalankan ulang nanti.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autoclip.config import load_settings
from autoclip.db import connect
from autoclip.publish import _upload_for
from autoclip.youtube import access_token, upload_video

LOG = ROOT / "data" / "replace_windah.log"
log = logging.getLogger("replace")

TARGETS = {
    28: ("k3sg7dSqkTA", "public", None),
    29: ("cE7_ZzT-jUY", "public", None),
    30: ("Zr_hqHv01nY", "public", None),
    37: ("Y2NAUjaQfSg", "private", "2026-11-06T12:00:00Z"),
    38: ("rxhC4UuNV6g", "private", "2026-11-06T13:00:00Z"),
    39: ("PyNsCIAUL2c", "private", "2026-11-07T04:00:00Z"),
    47: ("S_qJsJNRpXI", "private", "2026-11-10T15:00:00Z"),
}

QUOTA_MARK = "uploadLimitExceeded"


def delete_video(token: str, video_id: str) -> bool:
    for attempt in range(3):
        try:
            response = httpx.delete(
                "https://www.googleapis.com/youtube/v3/videos",
                params={"id": video_id},
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )
            if response.status_code in (204, 404):
                return True
            log.warning("hapus %s: %s", video_id, response.text[:120])
            return False
        except Exception as exc:
            log.warning("hapus %s gagal (try %s): %s", video_id, attempt + 1, exc)
            time.sleep(3 * (attempt + 1))
    return False


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG, encoding="utf-8"), logging.StreamHandler()],
    )
    settings = load_settings(ROOT)
    conn = connect(settings.paths.database)
    db = sqlite3.connect(settings.paths.database)
    db.row_factory = sqlite3.Row

    quota_hit = False
    for clip_id, (old_id, privacy, publish_at) in TARGETS.items():
        row = db.execute("select * from clips where id=?", (clip_id,)).fetchone()
        pub = db.execute(
            "select * from publications where clip_id=? and platform='youtube'",
            (clip_id,),
        ).fetchone()
        if pub is None:
            log.warning("#%s tidak punya publikasi YouTube; dilewati", clip_id)
            continue
        if str(pub["remote_id"]) != old_id:
            log.info("#%s sudah diganti (%s); dilewati", clip_id, pub["remote_id"])
            continue
        path = Path(str(row["file_path"]))
        if not path.exists():
            log.error("#%s file hilang: %s", clip_id, path)
            continue

        upload = _upload_for(settings, conn, row, "youtube")
        try:
            new_id = upload_video(
                settings,
                str(row["account_id"]),
                row,
                privacy=privacy,
                upload=upload,
                publish_at=publish_at,
            )
        except Exception as exc:
            if QUOTA_MARK in str(exc):
                log.warning("kuota habis; #%s dan sisanya menunggu", clip_id)
                quota_hit = True
                break
            log.error("#%s upload gagal: %s", clip_id, exc)
            continue

        token = access_token(settings, str(row["account_id"]))
        if not delete_video(token, old_id):
            log.warning("#%s video lama %s belum terhapus", clip_id, old_id)
        db.execute(
            "update publications set remote_id=?, status='published' where id=?",
            (new_id, pub["id"]),
        )
        db.commit()
        log.info("#%s %s -> %s (%s)", clip_id, old_id, new_id, privacy)

    remaining = [
        clip_id
        for clip_id in TARGETS
        if str(
            db.execute(
                "select remote_id from publications where clip_id=? and platform='youtube'",
                (clip_id,),
            ).fetchone()["remote_id"]
        )
        == TARGETS[clip_id][0]
    ]
    if not remaining:
        LOG.with_suffix(".done").write_text("selesai", encoding="utf-8")
        log.info("semua target selesai")
        return 0
    log.info("sisa target: %s", remaining)
    return 3 if quota_hit else 1


if __name__ == "__main__":
    sys.exit(main())
