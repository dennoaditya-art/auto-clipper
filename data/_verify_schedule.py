"""Verifikasi video panjang benar-benar terjadwal di YouTube."""

import json
import sqlite3

from pathlib import Path

from autoclip.config import load_settings
from autoclip.youtube import fetch_video

s = load_settings(Path("."))
c = sqlite3.connect("data/autoclip.db")
c.row_factory = sqlite3.Row

for cid in (61, 62, 63):
    pub = c.execute(
        "SELECT remote_id, account_id, status, scheduled_at FROM publications WHERE clip_id=? AND platform='youtube'",
        (cid,),
    ).fetchone()
    if not pub:
        print(f"#{cid} belum ada publication")
        continue
    v = fetch_video(s, pub["account_id"], pub["remote_id"])
    st = v.get("status") or {}
    print(f"#{cid} {pub['remote_id']} akun={pub['account_id']}")
    print(f"   privacy={st.get('privacyStatus')} publishAt={st.get('publishAt')}")
    print(f"   uploadStatus={st.get('uploadStatus')} judul={v.get('snippet', {}).get('title')}")
    print(f"   db scheduled_at={pub['scheduled_at']}")
