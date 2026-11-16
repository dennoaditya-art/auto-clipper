"""Audit views tab Shorts kanal (video vertikal tidak muncul di /videos).

Pakai: python data/_yt_shorts_audit.py <channel_url> [<channel_url> ...]
"""

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import yt_dlp  # noqa: E402

conn = sqlite3.connect(ROOT / "data/autoclip.db")
conn.row_factory = sqlite3.Row
published = {
    r["remote_id"]: dict(r)
    for r in conn.execute(
        "SELECT clip_id, account_id, remote_id, published_at FROM publications WHERE platform='youtube'"
    )
}

opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist", "playlistend": 200}
for url in sys.argv[1:]:
    with yt_dlp.YoutubeDL(opts) as ydl:
        try:
            listing = ydl.extract_info(url.rstrip("/") + "/shorts", download=False)
        except Exception as exc:  # noqa: BLE001
            print(f"== {url} GAGAL {type(exc).__name__}: {str(exc)[:120]}")
            continue
    entries = listing.get("entries") or []
    print(f"== {listing.get('channel') or url} shorts={len(entries)} channel={listing.get('channel_url')}")
    rows = sorted(entries, key=lambda e: e.get("view_count") or 0)
    zero = 0
    for e in rows:
        pub = published.get(e.get("id"))
        views = e.get("view_count")
        if not views:
            zero += 1
        tag = f"clip {pub['clip_id']}/{pub['account_id']}" if pub else "bukan DB"
        print(f"{views if views is not None else '?':>7}  {e.get('id')}  {tag:<16} {(e.get('title') or '')[:52]}")
    print(f"-- 0 views: {zero}/{len(rows)}\n")
