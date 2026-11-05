"""Jadwalkan ulang video panjang: 1 per hari, dan pasang thumbnail."""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from autoclip.config import load_settings
from autoclip.db import get_clip, get_publication
from autoclip.render import make_thumbnail
from autoclip.youtube import VIDEO_URL, access_token, fetch_video, set_thumbnail

s = load_settings(Path("."))
conn = sqlite3.connect("data/autoclip.db")
conn.row_factory = sqlite3.Row

zone = timezone(timedelta(hours=7))
today = datetime.now(zone).date()

# satu video panjang per hari, jam 18:00 WIB
plan = {61: today, 62: today + timedelta(days=1), 63: today + timedelta(days=2)}

for cid, day in plan.items():
    pub = get_publication(conn, cid, "youtube", "kedua")
    if pub is None:
        print(f"#{cid} belum terunggah")
        continue
    when = datetime(day.year, day.month, day.day, 18, 0, tzinfo=zone)
    stamp = when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    token = access_token(s, "kedua")
    current = fetch_video(s, "kedua", str(pub["remote_id"]))
    snippet = current.get("snippet") or {}
    body = {
        "id": pub["remote_id"],
        "snippet": {
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "categoryId": snippet.get("categoryId", "24"),
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": stamp,
            "selfDeclaredMadeForKids": False,
        },
    }
    with httpx.Client(timeout=90) as client:
        resp = client.put(
            VIDEO_URL,
            params={"part": "snippet,status"},
            headers={"Authorization": f"Bearer {token}"},
            json=body,
        )
    if resp.status_code != 200:
        print(f"FAIL #{cid}: {resp.status_code} {resp.text[:200]}")
        continue
    conn.execute(
        "UPDATE publications SET scheduled_at=? WHERE clip_id=? AND platform='youtube'",
        (stamp, cid),
    )
    print(f"OK   #{cid} -> {when.strftime('%Y-%m-%d %H:%M WIB')} ({stamp})")

    clip = get_clip(conn, cid)
    video = Path(str(clip["file_path"]))
    image = video.with_suffix(".jpg")
    if not image.exists():
        image = make_thumbnail(video) or image
    try:
        set_thumbnail(s, "kedua", str(pub["remote_id"]), image)
        print(f"     thumbnail terpasang")
    except Exception as exc:
        print(f"     thumbnail gagal: {exc}")

conn.commit()
