"""Render ulang varian TikTok klip 72-77 setelah perbaikan subtitle.

Pakai: python data/_rerender_tt.py 72 73 74
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip import pipeline
from autoclip.config import load_settings
from autoclip.db import connect, get_clip, get_source
from autoclip.media import probe
from autoclip.render import render_clip
from autoclip.transcribe import transcript_path

root = Path(__file__).resolve().parents[1]
settings = load_settings(root)
conn = connect(settings.paths.database)

for raw in sys.argv[1:]:
    clip_id = int(raw)
    clip = get_clip(conn, clip_id)
    source = get_source(conn, int(clip["source_id"]))
    media_path = Path(str(source["path"]))
    transcript = json.loads(
        transcript_path(settings, str(source["sha256"])).read_text(encoding="utf-8")
    )
    rendered = render_clip(
        media_path,
        probe(media_path),
        float(clip["start"]),
        float(clip["end"]),
        str(clip["title"]),
        settings,
        transcript,
        settings.paths.review / "clips",
        int(clip["source_id"]),
        watermark=pipeline._watermark_for(settings, media_path),
        watermark_image=pipeline._watermark_image_for(settings, media_path),
        profile="tiktok",
    )
    conn.execute(
        "UPDATE clips SET tiktok_path = ?, file_hash = ? WHERE id = ?",
        (str(rendered.path), rendered.sha256, clip_id),
    )
    conn.commit()
    print(clip_id, rendered.path)
