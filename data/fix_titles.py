"""Perbaiki judul video yang sudah terunggah tapi judulnya terpotong."""

import json
import sqlite3
import sys
from pathlib import Path

from autoclip.config import load_settings
from autoclip.db import get_publication
from autoclip.select import _caption_title, _usable_title
from autoclip.youtube import update_video

APPLY = "--apply" in sys.argv

s = load_settings(Path("."))
c = sqlite3.connect("data/autoclip.db")
c.row_factory = sqlite3.Row

rows = c.execute(
    """SELECT c.id, c.title, c.scores_json, c.account_id
       FROM clips c
       WHERE c.id BETWEEN 52 AND 60 ORDER BY c.id"""
).fetchall()

plan = []
for r in rows:
    data = json.loads(r["scores_json"] or "{}")
    new = _caption_title(str(data.get("caption") or ""))
    if not _usable_title(r["title"]) and _usable_title(new):
        plan.append((r["id"], r["account_id"], r["title"], new))
    else:
        print(f"SKIP #{r['id']}: judul masih layak -> {r['title']}")

print(f"\nakan diubah: {len(plan)}")
for cid, acc, old, new in plan:
    print(f"#{cid} {acc}")
    print(f"  lama: {old}")
    print(f"  baru: {new}")

if not APPLY:
    print("\n(dry-run) tambahkan --apply")
    raise SystemExit(0)

for cid, acc, old, new in plan:
    pub = get_publication(c, cid, "youtube", acc)
    if pub is None:
        print(f"FAIL #{cid}: belum ada publication")
        continue
    try:
        update_video(s, acc, str(pub["remote_id"]), description=None, tags=None)
        # update_video tidak punya param title; pakai helper langsung
        import httpx

        from autoclip.youtube import VIDEO_URL, access_token, fetch_video

        current = fetch_video(s, acc, str(pub["remote_id"]))
        snippet = dict(current.get("snippet") or {})
        snippet["title"] = new[:100]
        token = access_token(s, acc)
        with httpx.Client(timeout=60) as client:
            resp = client.put(
                VIDEO_URL,
                params={"part": "snippet"},
                headers={"Authorization": f"Bearer {token}"},
                json={"id": pub["remote_id"], "snippet": snippet},
            )
        if resp.status_code == 200:
            c.execute("UPDATE clips SET title=? WHERE id=?", (new, cid))
            print(f"OK   #{cid} {pub['remote_id']}")
        else:
            print(f"FAIL #{cid}: {resp.status_code} {resp.text[:150]}")
    except Exception as exc:
        print(f"FAIL #{cid}: {exc}")

c.commit()
