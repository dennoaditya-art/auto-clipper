"""Statistik publik video YouTube tanpa API (token OAuth mati).

Pakai: python data/_yt_public_stats.py
Sumber ID: tabel publications (platform=youtube, status=published).
"""

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

conn = sqlite3.connect(ROOT / "data/autoclip.db")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT id, clip_id, account_id, remote_id, published_at, status"
    " FROM publications WHERE platform='youtube' ORDER BY id"
).fetchall()

try:
    import yt_dlp
except ImportError:
    raise SystemExit("yt_dlp tidak terpasang")

opts = {"quiet": True, "no_warnings": True, "skip_download": True}
for r in rows:
    vid = r["remote_id"]
    if not vid:
        print(f"#{r['id']} clip {r['clip_id']} status={r['status']} remote_id kosong")
        continue
    url = f"https://www.youtube.com/watch?v={vid}"
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        print(
            f"#{r['id']:>2} clip {r['clip_id']:>3} {vid} "
            f"views={info.get('view_count')} likes={info.get('like_count')} "
            f"comments={info.get('comment_count')} "
            f"up={info.get('upload_date')} len={info.get('duration')}s "
            f"| {str(info.get('title'))[:60]}"
        )
    except Exception as exc:  # noqa: BLE001 - diagnostik
        print(f"#{r['id']} clip {r['clip_id']} {vid} GAGAL: {type(exc).__name__}: {str(exc)[:120]}")
