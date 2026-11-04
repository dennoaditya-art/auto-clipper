"""Set categoryId video yang sudah tayang ke nilai settings.upload.category_id."""

import sqlite3
import sys
from pathlib import Path

from autoclip.config import load_settings
from autoclip.youtube import update_video

APPLY = "--apply" in sys.argv

s = load_settings(Path("."))
target = s.upload.category_id
c = sqlite3.connect("data/autoclip.db")
c.row_factory = sqlite3.Row
rows = c.execute(
    "SELECT remote_id, account_id acc FROM publications WHERE status='published'"
).fetchall()

print(f"target categoryId = {target}, video = {len(rows)}")
if not APPLY:
    print("(dry-run) tambahkan --apply")
    raise SystemExit(0)

ok = fail = 0
for r in rows:
    try:
        client = __import__("httpx").Client(timeout=60)
        from autoclip.youtube import VIDEO_URL, access_token, fetch_video

        current = fetch_video(s, r["acc"], r["remote_id"])
        snippet = dict(current.get("snippet") or {})
        if snippet.get("categoryId") == target:
            print(f"SKIP {r['remote_id']} sudah {target}")
            continue
        snippet["categoryId"] = target
        token = access_token(s, r["acc"])
        resp = client.put(
            VIDEO_URL,
            params={"part": "snippet"},
            headers={"Authorization": f"Bearer {token}"},
            json={"id": r["remote_id"], "snippet": snippet},
        )
        client.close()
        if resp.status_code == 200:
            print(f"OK   {r['remote_id']} -> {target}")
            ok += 1
        else:
            print(f"FAIL {r['remote_id']}: {resp.status_code} {resp.text[:150]}")
            fail += 1
    except Exception as exc:
        print(f"FAIL {r['remote_id']}: {exc}")
        fail += 1
print(f"\nselesai: ok={ok} fail={fail}")
