"""Ringkas publikasi TikTok 5-9 Nov + status klip terbaru."""

import sqlite3

c = sqlite3.connect("data/autoclip.db")
c.row_factory = sqlite3.Row
print("--- publications tiktok 5-9 Nov")
for r in c.execute(
    "SELECT clip_id,status,created_at,published_at,substr(coalesce(error,''),1,70) e "
    "FROM publications WHERE platform='tiktok' AND created_at >= '2026-11-05' "
    "ORDER BY created_at"
):
    print(dict(r))
print("--- clips 70+")
for r in c.execute("SELECT id,status,title FROM clips WHERE id>=70 ORDER BY id"):
    print(r["id"], r["status"], (r["title"] or "")[:50])
