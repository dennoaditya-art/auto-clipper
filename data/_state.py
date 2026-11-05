import sqlite3
from pathlib import Path

c = sqlite3.connect("data/autoclip.db")
c.row_factory = sqlite3.Row

print("=== SOURCES ===")
for r in c.execute("SELECT id, path, duration, status FROM sources ORDER BY id"):
    name = Path(r["path"]).name
    print(f"{r['id']:3} {r['status']:12} {(r['duration'] or 0)/60:6.1f}min  {name}")

print("\n=== CLIPS per status/account ===")
for r in c.execute(
    "SELECT account_id, status, COUNT(*) n FROM clips GROUP BY account_id, status"
):
    print(f"{r['account_id']:6} {r['status']:10} {r['n']}")

print("\n=== CLIPS belum publish (approved) ===")
rows = c.execute(
    """SELECT c.id, c.account_id, c.title, c.topic, (c.end-c.start) dur
       FROM clips c
       WHERE c.status='approved'
         AND NOT EXISTS (SELECT 1 FROM publications p
                         WHERE p.clip_id=c.id AND p.status='published')
       ORDER BY c.id"""
).fetchall()
print(f"total: {len(rows)}")
for r in rows:
    print(f"{r['id']:3} {r['account_id']:6} {r['dur']:7.1f}s {(r['topic'] or '-')[:14]:14} {r['title'][:44]}")

print("\n=== publications ===")
for r in c.execute(
    "SELECT status, COUNT(*) n FROM publications GROUP BY status"
):
    print(f"{r['status']:10} {r['n']}")
