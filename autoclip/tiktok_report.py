"""Parser tabel konten TikTok Studio untuk laporan views mingguan.

Studio tidak punya ekspor CSV; satu-satunya jalan adalah membaca innerText tabel
lewat Playwright. Format tiap baris: durasi, caption, waktu, privacy, views,
likes, komentar — caption boleh kosong dan angka views memakai pemisah ribuan.
"""

from __future__ import annotations

import re
from statistics import median

_DURATION = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?$")
_MONTHS = (
    "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
)
_DATE = re.compile(rf"^(?:{_MONTHS})\w*\s+\d{{1,2}},\s+\d{{1,2}}:\d{{2}}\s*[AP]M$")
_NUMBER = re.compile(r"^[\d.,]+$")


def _number(line: str) -> int | None:
    if not _NUMBER.match(line):
        return None
    try:
        return int(line.replace(",", "").replace(".", ""))
    except ValueError:
        return None


def parse_content_rows(text: str) -> list[dict]:
    """Ambil (caption, waktu, views) dari innerText tabel konten Studio."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    rows: list[dict] = []
    for index, line in enumerate(lines):
        if not _DATE.match(line):
            continue
        previous = lines[index - 1] if index else ""
        caption = "" if _DURATION.match(previous) else previous
        views = None
        for after in lines[index + 1 : index + 5]:
            found = _number(after)
            if found is not None:
                views = found
                break
        if views is None:
            continue
        rows.append({"when": line, "caption": caption, "views": views})
    return rows


def summarize(rows: list[dict]) -> dict:
    views = [int(row["views"]) for row in rows]
    return {
        "n": len(views),
        "median": int(median(views)) if views else 0,
        "max": max(views) if views else 0,
    }
