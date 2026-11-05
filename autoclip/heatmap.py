"""Heatmap "paling sering di-replay" dari halaman watch YouTube.

Kenapa scraping: YouTube Data API tidak menyediakan data heatmap. Halaman watch
publik memuatnya sebagai entri `heatmap.markers`, jadi satu request HTTP cukup.

Dipakai untuk menaikkan skor klip yang jatuh di momen yang benar-benar diputar
ulang penonton, bukan hanya momen yang ramai secara heuristik transkrip.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

_MARKER = re.compile(
    r'"startMillis":"(\d+)","durationMillis":"(\d+)"'
    r',"intensityScoreNormalized":([0-9.]+)'
)
_ID = re.compile(r"[A-Za-z0-9_-]{11}")


def video_id(path_or_url: str) -> str | None:
    """Ambil ID video dari nama file `windah3-sQS6zVkqYGA.mp4` atau URL."""
    text = str(path_or_url)
    tail = re.split(r"[-/]|v=", text)
    for part in reversed(tail):
        token = part.split(".")[0].split("?")[0].split("&")[0]
        if _ID.fullmatch(token or ""):
            return token
    return None


def parse(html: str) -> list[tuple[float, float, float]]:
    """(start_detik, end_detik, intensitas 0..1) dari HTML halaman watch."""
    markers = []
    for start_ms, dur_ms, score in _MARKER.findall(html):
        start = int(start_ms) / 1000
        end = (int(start_ms) + int(dur_ms)) / 1000
        markers.append((round(start, 2), round(end, 2), float(score)))
    return markers


def fetch(video: str, cache_dir: Path | None = None, ttl: float = 86_400) -> list:
    """Ambil heatmap, dengan cache lokal agar tidak menembak YouTube terus."""
    vid = video_id(video) or video
    cached: Path | None = None
    if cache_dir is not None:
        cached = cache_dir / f"{vid}.json"
        if cached.exists() and time.time() - cached.stat().st_mtime < ttl:
            try:
                return [tuple(item) for item in json.loads(cached.read_text("utf-8"))]
            except (ValueError, OSError):
                pass

    url = f"https://www.youtube.com/watch?v={vid}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
            ),
            "Accept-Language": "id-ID,id;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            html = response.read().decode("utf-8", "replace")
    except Exception as exc:  # jaringan/geo: heatmap opsional, jangan gagalkan run
        log.warning("heatmap %s gagal diambil: %s", vid, exc)
        return []
    markers = parse(html)
    if cache_dir is not None:
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(markers), encoding="utf-8")
        except OSError:
            pass
    log.info("heatmap %s: %s titik replay", vid, len(markers))
    return markers


def bonus(markers: list, start: float, end: float, ceiling: float = 18.0) -> float:
    """Tambahan skor 0..ceiling untuk klip yang menutup puncak replay."""
    if not markers:
        return 0.0
    peak = max(
        (score for s, e, score in markers if e > start and s < end),
        default=0.0,
    )
    # intensitas relatif: heatmap YouTube sudah dinormalisasi 0..1
    return round(ceiling * min(1.0, peak ** 0.5), 2)
