"""Render varian YouTube Shorts: crop vertikal penuh, subtitle aman dari UI.

Pakai: python data/render_manual_yt.py 84 85 86
Hasil: storage/review/manual/youtube/<id>-<slug>.mp4
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.db import connect, get_clip, get_source
from autoclip.media import probe
from autoclip.render import render_clip
from autoclip.transcribe import transcript_path

root = Path(__file__).resolve().parents[1]
settings = load_settings(root)
conn = connect(settings.paths.database)
out_dir = root / "storage" / "review" / "manual" / "youtube"

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
        out_dir,
        int(clip["source_id"]),
        profile="youtube",
    )
    dur = float(clip["end"]) - float(clip["start"])
    print(f"#{clip_id} {dur:.0f} dtk -> {rendered.path}")
