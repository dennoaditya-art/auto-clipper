"""Audit views seluruh video kanal YouTube tanpa API (1 request daftar).

Pakai: python data/_yt_channel_audit.py [video_id_penanda]
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
probe_id = sys.argv[1] if len(sys.argv) > 1 else "Opl1zxitIAY"

import yt_dlp  # noqa: E402

opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist"}
with yt_dlp.YoutubeDL(opts) as ydl:
    info = ydl.extract_info(f"https://www.youtube.com/watch?v={probe_id}", download=False)
    channel = info.get("channel_url") or info.get("uploader_url")
    print("KANAL:", info.get("channel"), channel)
    listing = ydl.extract_info(channel.rstrip("/") + "/videos", download=False)

entries = listing.get("entries") or []
print(f"video publik terdaftar: {len(entries)}")

conn = sqlite3.connect(ROOT / "data/autoclip.db")
conn.row_factory = sqlite3.Row
published = {
    r["remote_id"]: dict(r)
    for r in conn.execute("SELECT clip_id, remote_id, published_at FROM publications WHERE platform='youtube'")
}

rows = sorted(entries, key=lambda e: e.get("view_count") or 0)
zero = 0
for e in rows:
    pub = published.get(e.get("id"))
    tag = f"clip {pub['clip_id']}" if pub else "tidak di DB"
    views = e.get("view_count")
    if not views:
        zero += 1
    print(f"{views if views is not None else '?':>8}  {e.get('id')}  {tag:<12} {(e.get('title') or '')[:55]}")

print(f"\n0 views: {zero}/{len(rows)}")
missed = [v for v in published if v and v not in {e.get('id') for e in rows}]
print("ID di DB tapi tidak muncul di daftar kanal:", len(missed), missed[:10])
