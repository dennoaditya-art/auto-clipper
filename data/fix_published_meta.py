"""Perbaiki metadata video yang sudah tayang dengan hashtag/credit sumber lain."""

import sqlite3
import sys
from pathlib import Path

from autoclip.config import load_settings
from autoclip.publish import _source_meta
from autoclip.youtube import _description, _hashtag_list, update_video

APPLY = "--apply" in sys.argv

s = load_settings(Path("."))
c = sqlite3.connect("data/autoclip.db")
c.row_factory = sqlite3.Row
rows = c.execute(
    """SELECT p.remote_id, p.account_id acc, c.source_id, s.path, c.title
       FROM publications p
       JOIN clips c ON c.id = p.clip_id
       JOIN sources s ON s.id = c.source_id
       WHERE p.status='published'"""
).fetchall()

plan = []
for r in rows:
    hashtags, credit = _source_meta(s, c, {"source_id": r["source_id"]}, "youtube")
    tags = [t.lstrip("#") for t in _hashtag_list(hashtags)][:15]
    desc = _description({"title": r["title"], "topic": ""}, None, hashtags)
    desc = f"{credit}\n\n{desc}".strip() if credit else desc
    plan.append((r["acc"], r["remote_id"], r["path"], tags, desc))

print(f"{'ACC':5} {'VIDEO':13} {'SUMBER':12} TAGS")
for acc, rid, path, tags, _ in plan:
    src = Path(path).name.split("-", 1)[0]
    print(f"{acc:5} {rid:13} {src:12} {' '.join(tags)}")

if not APPLY:
    print("\n(dry-run) tambahkan --apply untuk menulis ke YouTube")
    raise SystemExit(0)

for acc, rid, path, tags, desc in plan:
    try:
        update_video(s, acc, rid, description=desc, tags=tags)
        print(f"OK   {rid}")
    except Exception as exc:
        print(f"FAIL {rid}: {exc}")
