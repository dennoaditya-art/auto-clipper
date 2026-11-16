"""Teks transkrip + jeda untuk jendela waktu mentah (belum jadi klip).

Pakai: python data/_window_text.py 17 3525.5 3570.4
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autoclip.config import load_settings  # noqa: E402
from autoclip.transcribe import transcript_path  # noqa: E402

source_id = int(sys.argv[1])
settings = load_settings(ROOT)
import sqlite3  # noqa: E402

conn = sqlite3.connect(ROOT / "data/autoclip.db")
conn.row_factory = sqlite3.Row
source = conn.execute("SELECT * FROM sources WHERE id=?", (source_id,)).fetchone()
segs = json.loads(
    transcript_path(settings, source["sha256"]).read_text(encoding="utf-8")
)["segments"]

for pair in sys.argv[2:]:
    a, b = (float(x) for x in pair.replace("-", " ").split())
    print(f"== {a:.1f}-{b:.1f}")
    prev = a
    for s in segs:
        if s["end"] <= a or s["start"] >= b:
            continue
        gap = s["start"] - prev
        if gap > 2:
            print(f"   (jeda {gap:.1f}s)")
        print(f"  {s['start']:7.1f} {s['end']:7.1f}  {s['text']}")
        prev = max(prev, s["end"])
    print(f"   jeda akhir {b - prev:.1f}s\n")
