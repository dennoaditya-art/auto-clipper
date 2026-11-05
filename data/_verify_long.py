import json
import sqlite3
import subprocess
from pathlib import Path

from autoclip.config import load_settings
from autoclip.media import ffprobe_bin, probe

s = load_settings(Path("."))
c = sqlite3.connect("data/autoclip.db")
c.row_factory = sqlite3.Row

print("=== VIDEO PANJANG (kompilasi) ===")
for r in c.execute(
    """SELECT c.id, c.account_id, c.title, c.file_path, c.status
       FROM clips c WHERE c.topic='longform' ORDER BY c.id"""
):
    p = Path(r["file_path"])
    if p.exists():
        info = probe(p)
        pub = c.execute(
            "SELECT status, remote_id FROM publications WHERE clip_id=?", (r["id"],)
        ).fetchone()
        state = f"{pub['status']}" if pub else "belum upload"
        print(
            f"#{r['id']:3} {r['account_id']:6} {info.duration/60:5.1f}min "
            f"{info.width}x{info.height} audio={info.has_audio} "
            f"{p.stat().st_size/1024/1024:5.0f}MB [{state}] {r['title'][:42]}"
        )
    else:
        print(f"#{r['id']:3} HILANG {p}")

print("\n=== KLIP TIKTOK siap unggah (campaign TikTok-only) ===")
rows = c.execute(
    """SELECT c.id, c.title, c.file_path FROM clips c
       WHERE c.id BETWEEN 46 AND 51 ORDER BY c.id"""
).fetchall()
for r in rows:
    p = Path(r["file_path"])
    print(f"#{r['id']} {'OK' if p.exists() else 'HILANG'} {p.name[:56]}")
    print(f"     {r['title'][:70]}")
