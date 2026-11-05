import json
import sqlite3

c = sqlite3.connect("data/autoclip.db")
c.row_factory = sqlite3.Row
for cid in (52, 53, 55, 56, 58, 59, 60):
    r = c.execute("SELECT id, title, scores_json FROM clips WHERE id=?", (cid,)).fetchone()
    data = json.loads(r["scores_json"])
    print(f"#{r['id']}")
    print(f"  title  : {r['title']}")
    print(f"  reason : {data.get('reason', '')[:160]}")
    print(f"  caption: {data.get('caption', '')[:120]}")
    print()
