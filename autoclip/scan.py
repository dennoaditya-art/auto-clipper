from __future__ import annotations

import logging
import time
from pathlib import Path

from .config import Settings
from .db import create_source
from .media import VIDEO_EXTENSIONS, MediaError, probe, sha256_file

log = logging.getLogger(__name__)


def iter_videos(incoming: Path) -> list[Path]:
    if not incoming.exists():
        return []
    return sorted(
        p
        for p in incoming.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )


def scan(settings: Settings, conn) -> list[int]:
    created: list[int] = []
    minimum_age = settings.safety.min_source_age_seconds
    current = time.time()
    for path in iter_videos(settings.paths.incoming):
        try:
            age = current - path.stat().st_mtime
        except OSError as exc:
            log.warning("tidak bisa membaca %s: %s", path, exc)
            continue
        if age < minimum_age:
            log.info("lewati file baru (mungkin masih disalin): %s", path.name)
            continue
        try:
            digest = sha256_file(path)
        except OSError as exc:
            log.warning("gagal hash %s: %s", path, exc)
            continue
        try:
            info = probe(path)
        except MediaError as exc:
            log.warning("gagal probe %s: %s", path, exc)
            continue
        source_id = create_source(conn, str(path.resolve()), digest, info.duration)
        if source_id is None:
            log.info("duplikat, dilewati: %s", path.name)
            continue
        log.info("sumber baru #%s: %s (%.1fs)", source_id, path.name, info.duration)
        created.append(source_id)
    return created
