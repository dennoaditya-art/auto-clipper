import json
import sqlite3
from pathlib import Path

from autoclip.config import load_settings
from autoclip.db import connect, get_source
from autoclip.media import probe, sha256_file
from autoclip.pipeline import _watermark_for, _watermark_image_for
from autoclip.render import render_clip
from autoclip.select import _shape_bounds
from autoclip.transcribe import transcript_path

IDS = (28, 29, 30, 37, 38, 39, 47)

s = load_settings(Path("."))
conn = connect(s.paths.database)
db = sqlite3.connect("data/autoclip.db")
db.row_factory = sqlite3.Row

for clip_id in IDS:
    row = db.execute("select * from clips where id=?", (clip_id,)).fetchone()
    src = get_source(conn, int(row["source_id"]))
    media = Path(src["path"])
    tr = json.loads(transcript_path(s, src["sha256"]).read_text(encoding="utf-8"))

    start, end = float(row["start"]), float(row["end"])
    if 0 < end <= start + 1:
        end = start + end
    new_start, new_end = _shape_bounds(tr["segments"], start, end, s.selection)

    out = render_clip(
        media, probe(media), new_start, new_end, str(row["title"]), s, tr,
        s.paths.review / "clips", int(row["source_id"]),
        watermark=_watermark_for(s, media),
        watermark_image=_watermark_image_for(s, media),
    )
    old_file = Path(row["file_path"])
    db.execute(
        "update clips set start=?, end=?, file_path=?, file_hash=? where id=?",
        (new_start, new_end, str(out.path), sha256_file(out.path), clip_id),
    )
    db.commit()
    if old_file.exists() and old_file.resolve() != out.path.resolve():
        old_file.unlink()
    print(
        f"#{clip_id} {start:.1f}-{end:.1f} -> {new_start:.1f}-{new_end:.1f} "
        f"({new_end - new_start:.0f}s) {out.path.name}"
    )
