"""Daftarkan jendela waktu pilihan manual sebagai klip di DB.

Pakai: python data/add_clip_window.py "17 3525.5 3570.4 Judul hook"
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autoclip.config import load_settings  # noqa: E402
from autoclip.db import add_clip, connect, get_source  # noqa: E402

settings = load_settings(ROOT)
conn = connect(settings.paths.database)

for raw in sys.argv[1:]:
    source_id, start, end, title = raw.split(" ", 3)
    source = get_source(conn, int(source_id))
    clip_id = add_clip(
        conn,
        source_id=int(source_id),
        account_id="utama",
        start=float(start),
        end=float(end),
        file_path="",
        file_hash="",
        title=title,
        topic="roblox",
        scores_json=json.dumps({"manual": True}),
        viral_score=0.0,
        niche_fit=0.0,
        final_score=0.0,
    )
    print(f"clip {clip_id}: {title}")
