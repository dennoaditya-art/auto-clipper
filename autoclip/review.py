from __future__ import annotations

import html
import json
import os
from datetime import datetime
from pathlib import Path

from .config import Settings
from .db import get_clip, list_clips, record_review, set_clip_status
from .media import sha256_file

STATUS_ORDER = {"pending": 0, "approved": 1, "rejected": 2, "stale": 3}


class ReviewError(RuntimeError):
    pass


def approve(conn, clip_id: int, reviewer: str | None = None) -> None:
    clip = get_clip(conn, clip_id)
    if clip["status"] != "pending":
        raise ReviewError(f"clip {clip_id} berstatus {clip['status']}, bukan pending")
    path = Path(clip["file_path"])
    if not path.exists():
        set_clip_status(conn, clip_id, "stale")
        raise ReviewError(f"file clip hilang: {path}")
    digest = sha256_file(path)
    if digest != clip["file_hash"]:
        set_clip_status(conn, clip_id, "stale")
        raise ReviewError("hash file berubah; approval dibatalkan, render ulang")
    record_review(conn, clip_id, "approved", reviewer or _reviewer(), digest)


def reject(conn, clip_id: int, reviewer: str | None = None) -> None:
    clip = get_clip(conn, clip_id)
    if clip["status"] not in {"pending", "approved"}:
        raise ReviewError(f"clip {clip_id} berstatus {clip['status']}")
    record_review(conn, clip_id, "rejected", reviewer or _reviewer(), None)


def _reviewer() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "local"


def _safe(value: object) -> str:
    return html.escape(str(value))


def write_review_html(
    settings: Settings, conn, account_id: str | None = None
) -> Path:
    settings.paths.review.mkdir(parents=True, exist_ok=True)
    clips = list_clips(conn)
    if account_id is not None:
        clips = [c for c in clips if str(c["account_id"]) == account_id]
    clips.sort(
        key=lambda c: (
            STATUS_ORDER.get(c["status"], 9),
            -float(c["final_score"]),
            int(c["id"]),
        )
    )
    rows = []
    for clip in clips:
        video_path = Path(clip["file_path"])
        try:
            src = video_path.relative_to(settings.paths.review).as_posix()
        except ValueError:
            src = video_path.as_uri()
        try:
            scores = json.loads(clip["scores_json"])
        except json.JSONDecodeError:
            scores = {}
        score_items = "".join(
            f"<span><b>{_safe(k)}</b> {_safe(round(float(v), 1))}</span>"
            for k, v in scores.items()
            if isinstance(v, (int, float))
        )
        status = clip["status"]
        rows.append(
            f"""
            <article class="clip { _safe(status) }">
              <video src="{_safe(src)}" controls preload="metadata"></video>
              <div class="meta">
                <div class="top">
                  <span class="badge { _safe(status) }">{_safe(status)}</span>
                  <span class="score">{float(clip['final_score']):.1f}</span>
                </div>
                <h2>{_safe(clip['title'])}</h2>
                <p class="muted">{_safe(clip['topic'])} &middot;
                  {float(clip['start']):.1f}s &ndash; {float(clip['end']):.1f}s &middot;
                  viral {float(clip['viral_score']):.1f} &middot;
                  niche {float(clip['niche_fit']):.1f}</p>
                <p class="scores">{score_items}</p>
                <p class="muted small">{_safe(clip['source_path'])}</p>
                <code>python -m autoclip approve {int(clip['id'])}<br>python -m autoclip reject {int(clip['id'])}</code>
              </div>
            </article>
            """
        )

    pending = sum(1 for c in clips if c["status"] == "pending")
    document = f"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Auto-Clipper Review</title>
<style>
  :root {{ color-scheme: dark; --bg:#0b0c0f; --card:#14161b; --line:#262a33;
    --text:#f2f3f5; --muted:#9aa0aa; --accent:#f5c518; --ok:#22c55e; --bad:#ef4444; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
    font:15px/1.5 system-ui, Segoe UI, sans-serif; }}
  header {{ padding:28px 24px 8px; max-width:1200px; margin:auto; }}
  h1 {{ margin:0 0 4px; font-size:24px; }}
  .muted {{ color:var(--muted); }}
  .small {{ font-size:12px; }}
  main {{ max-width:1200px; margin:auto; padding:16px 24px 48px;
    display:grid; gap:18px; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); }}
  .clip {{ background:var(--card); border:1px solid var(--line); border-radius:14px;
    overflow:hidden; }}
  video {{ width:100%; max-height:520px; background:#000; display:block; }}
  .meta {{ padding:14px 16px 18px; }}
  .top {{ display:flex; justify-content:space-between; align-items:center; }}
  .badge {{ font-size:11px; text-transform:uppercase; letter-spacing:.08em;
    padding:3px 8px; border-radius:999px; background:#2a2e37; }}
  .badge.pending {{ background:#3a3210; color:#fde68a; }}
  .badge.approved {{ background:#0f2e1a; color:#86efac; }}
  .badge.rejected {{ background:#3a1414; color:#fca5a5; }}
  .badge.stale {{ background:#312441; color:#d8b4fe; }}
  .score {{ font-size:20px; font-weight:800; color:var(--accent); }}
  h2 {{ font-size:16px; margin:10px 0 6px; }}
  .scores {{ display:flex; flex-wrap:wrap; gap:6px; margin:10px 0; }}
  .scores span {{ background:#1c1f26; border:1px solid var(--line);
    border-radius:7px; padding:2px 7px; font-size:11px; color:var(--muted); }}
  code {{ display:block; margin-top:10px; padding:8px 10px; background:#0e1014;
    border-radius:8px; font-size:12px; color:#c9d1d9; }}
  .empty {{ padding:60px 24px; text-align:center; color:var(--muted); }}
</style>
</head>
<body>
<header>
  <h1>Auto-Clipper Review</h1>
  <p class="muted">{pending} pending &middot; {len(clips)} total &middot;
    dibuat {_safe(datetime.now().strftime('%Y-%m-%d %H:%M'))}</p>
</header>
<main>
{''.join(rows) if rows else '<p class="empty">Belum ada klip. Jalankan: python -m autoclip run</p>'}
</main>
</body>
</html>
"""
    path = settings.paths.review / (
        f"review-{account_id}.html" if account_id else "review.html"
    )
    document = document.replace(
        "<title>Auto-Clipper Review</title>",
        f"<title>Auto-Clipper Review ({account_id or 'semua'})</title>",
    )
    path.write_text(document, encoding="utf-8")
    return path
