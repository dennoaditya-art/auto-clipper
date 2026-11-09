"""Ringkas sumber video + transkrip + jumlah klip, untuk memilih bahan klip baru."""

import sqlite3
from pathlib import Path

c = sqlite3.connect("data/autoclip.db")
c.row_factory = sqlite3.Row
print("id  status      durasi  klip  exists  path")
for r in c.execute("SELECT * FROM sources ORDER BY id"):
    n = c.execute("SELECT COUNT(*) FROM clips WHERE source_id=?", (r["id"],)).fetchone()[0]
    p = Path(str(r["path"]))
    print(
        f"{r['id']:<3} {r['status']:<11} {float(r['duration'] or 0):>7.0f} {n:>5}  "
        f"{str(p.exists()):<6}  {p.name}"
    )
    t = Path("data/transcripts") / f"{r['sha256']}.json"
    if not t.exists():
        t2 = Path("data/transcripts") / f"{r['sha256']}.json"
        print(f"    transkrip: {t2.exists()} {t2.name}")
