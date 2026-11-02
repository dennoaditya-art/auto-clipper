from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from typing import Any

from .config import Settings
from .scan import iter_videos

log = logging.getLogger(__name__)

SYNC_TIMEOUT_SECONDS = 30 * 60
MAX_HEIGHT = 1080
POPULAR_CACHE_HOURS = 24


class SourceError(RuntimeError):
    pass


def _ytdlp() -> list[str]:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        found = shutil.which("yt-dlp")
        if not found:
            raise SourceError("yt-dlp tidak ditemukan (pip install yt-dlp)")
        return [found]
    return [sys.executable, "-m", "yt_dlp"]


def _command(settings: Settings, source_id: str, url: str, latest: int) -> list[str]:
    archive = settings.root / "data" / "ytdlp-archive.txt"
    template = settings.paths.incoming / f"{source_id}-%(id)s.%(ext)s"
    return [
        *_ytdlp(),
        "--playlist-end",
        str(latest),
        "--download-archive",
        str(archive),
        "--output",
        str(template),
        "--format",
        f"bv*[height<={MAX_HEIGHT}][vcodec^=avc1]+ba[acodec^=mp4a]"
        f"/bv*[height<={MAX_HEIGHT}]+ba"
        f"/b[height<={MAX_HEIGHT}]",
        "--merge-output-format",
        "mp4",
        "--no-overwrites",
        "--no-progress",
        "--no-warnings",
        "--force-ipv4",
        "--retries",
        "20",
        "--fragment-retries",
        "20",
        "--retry-sleep",
        "exp=2:30",
        "--concurrent-fragments",
        "4",
        "--continue",
        "--socket-timeout",
        "30",
        "--",
        url,
    ]


def _stream_durations(path: Any) -> dict[str, float]:
    from .media import ffprobe_bin, probe

    result = subprocess.run(
        [
            ffprobe_bin(),
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    durations: dict[str, float] = {}
    if result.returncode == 0:
        try:
            for stream in json.loads(result.stdout).get("streams", []):
                try:
                    value = float(stream.get("duration") or 0)
                except (TypeError, ValueError):
                    continue
                kind = str(stream.get("codec_type") or "")
                durations[kind] = max(durations.get(kind, 0.0), value)
        except json.JSONDecodeError:
            return {}
    overall = probe(path).duration
    durations["format"] = durations.get("format", 0.0) or overall
    return durations


def _verify_download(path: Any) -> None:
    """Pendek: deteksi download parsial (video stream lebih pendek dari audio)."""
    durations = _stream_durations(path)
    video = durations.get("video", 0.0)
    overall = durations.get("format", 0.0)
    if video <= 0:
        raise SourceError(f"{path}: stream video tidak ada")
    if overall > 0 and video < overall - 3:
        raise SourceError(
            f"{path}: video {video:.0f}s != durasi {overall:.0f}s (unduhan tidak lengkap)"
        )


def _drop_from_archive(settings: Settings, video_id: str) -> None:
    archive = _archive_path(settings)
    if not archive.exists():
        return
    kept = [
        line
        for line in archive.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip() and line.strip().split(" ")[-1] != video_id
    ]
    archive.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def _download(settings: Settings, source_id: str, url: str, latest: int) -> None:
    try:
        result = subprocess.run(
            _command(settings, source_id, url, latest),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SYNC_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceError(f"{source_id}: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "yt-dlp gagal").strip()
        raise SourceError(f"{source_id}: {detail[-800:]}")
    prefix = f"{source_id}-"
    for path in iter_videos(settings.paths.incoming):
        if not path.name.startswith(prefix):
            continue
        try:
            _verify_download(path)
        except SourceError as exc:
            log.error("unduhan rusak, dibuang: %s", exc)
            video_id = path.stem.split("-", 1)[-1].split(".")[0]
            path.unlink(missing_ok=True)
            _drop_from_archive(settings, video_id)
            raise


def _archive_path(settings: Settings) -> Any:
    return settings.root / "data" / "ytdlp-archive.txt"


def _archived_ids(settings: Settings) -> set[str]:
    archive = _archive_path(settings)
    if not archive.exists():
        return set()
    ids: set[str] = set()
    for line in archive.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split(" ")
        if len(parts) >= 2:
            ids.add(parts[1])
    return ids


def popular_videos(settings: Settings, source_id: str, url: str) -> list[dict[str, Any]]:
    """Daftar video kanal (id + view_count), cache harian; yt-dlp abaikan sort=p."""
    cache = settings.root / "data" / f"popular-{source_id}.json"
    if cache.exists():
        age = time.time() - cache.stat().st_mtime
        if age < POPULAR_CACHE_HOURS * 3600:
            try:
                cached = json.loads(cache.read_text(encoding="utf-8"))
                if isinstance(cached, list):
                    return cached
            except (json.JSONDecodeError, OSError):
                pass

    try:
        result = subprocess.run(
            [
                *_ytdlp(),
                "--flat-playlist",
                "--dump-json",
                "--no-warnings",
                "--socket-timeout",
                "30",
                "--",
                url,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SYNC_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SourceError(f"{source_id}: daftar video gagal: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "yt-dlp gagal").strip()
        raise SourceError(f"{source_id}: {detail[-500:]}")

    items: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        views = entry.get("view_count")
        if entry.get("id") and isinstance(views, int):
            items.append(
                {
                    "id": entry["id"],
                    "views": views,
                    "title": str(entry.get("title") or ""),
                }
            )
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    log.info("%s: %s video terindeks untuk fallback populer", source_id, len(items))
    return items


def download_most_popular(settings: Settings, source: Any) -> bool:
    """Unduh video paling banyak ditonton yang belum ada di arsip."""
    items = popular_videos(settings, source.id, source.url)
    archived = _archived_ids(settings)
    for item in sorted(items, key=lambda entry: entry["views"], reverse=True):
        if item["id"] in archived:
            continue
        url = f"https://www.youtube.com/watch?v={item['id']}"
        log.info(
            "fallback populer %s: %s (%s tayangan) %s",
            source.id,
            item["id"],
            item["views"],
            item["title"][:70],
        )
        _download(settings, source.id, url, 1)
        return True
    log.warning("%s: semua video populer sudah pernah diunduh", source.id)
    return False


def sync_sources(
    settings: Settings, only: str | None = None, account: str | None = None
) -> dict[str, Any]:
    sources = settings.active_sources()
    if account is not None:
        sources = tuple(s for s in sources if s.account_id == account)
    if only is not None:
        sources = tuple(s for s in sources if s.id == only)
        if not sources:
            raise SourceError(f"sumber aktif tidak ditemukan: {only}")
    summary: dict[str, Any] = {"downloaded": [], "errors": []}
    if not sources:
        return summary
    before = {path.name for path in iter_videos(settings.paths.incoming)}
    archive = _archive_path(settings)
    archive.parent.mkdir(parents=True, exist_ok=True)
    for source in sources:
        if source.rights_risk_accepted and not source.rights_approved:
            log.warning(
                "source %s: izin belum terverifikasi, risiko ditanggung pemilik akun",
                source.id,
            )
        snapshot = {path.name for path in iter_videos(settings.paths.incoming)}
        try:
            _download(settings, source.id, source.url, source.latest)
            fresh = {path.name for path in iter_videos(settings.paths.incoming)} - snapshot
            if not fresh and source.fallback_popular:
                log.info("%s: tidak ada upload baru, ambil yang paling populer", source.id)
                download_most_popular(settings, source)
        except SourceError as exc:
            log.error("sync gagal: %s", exc)
            summary["errors"].append(str(exc))
    after = {path.name for path in iter_videos(settings.paths.incoming)}
    prefixes = tuple(f"{source.id}-" for source in sources)
    new_files = sorted(
        name for name in after - before if name.startswith(prefixes)
    )
    ready = time.time() - settings.safety.min_source_age_seconds - 1
    for name in new_files:
        path = settings.paths.incoming / name
        try:
            os.utime(path, (ready, ready))
        except OSError as exc:
            log.warning("tidak bisa menandai %s siap: %s", name, exc)
    summary["downloaded"] = new_files
    if new_files:
        log.info("%s video baru diunduh", len(new_files))
    return summary
