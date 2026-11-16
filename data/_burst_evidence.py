"""Bukti pola unggah: burst per hari & per 10 menit dari tabel publications."""

import sqlite3
from datetime import datetime
from pathlib import Path

conn = sqlite3.connect(Path(__file__).resolve().parents[1] / "data/autoclip.db")
rows = conn.execute(
    "SELECT platform, account_id, published_at FROM publications"
    " WHERE status='published' AND published_at IS NOT NULL ORDER BY published_at"
).fetchall()

per_day: dict[str, int] = {}
stamps = []
for platform, account, at in rows:
    day = at[:10]
    key = f"{platform}:{account}"
    per_day[day] = per_day.get(day, 0) + 1
    if platform == "youtube":
        stamps.append(datetime.fromisoformat(at))

print("-- unggahan per hari (semua akun/platform)")
for day in sorted(per_day):
    print(f"{day}  {per_day[day]}")

worst = 0
worst_at = None
for i, stamp in enumerate(stamps):
    j = i
    while j + 1 < len(stamps) and (stamps[j + 1] - stamp).total_seconds() <= 600:
        j += 1
    if j - i + 1 > worst:
        worst = j - i + 1
        worst_at = stamp
print(f"\n-- YouTube: {worst} unggahan dalam 10 menit, mulai {worst_at}")
