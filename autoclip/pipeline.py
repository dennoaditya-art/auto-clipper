from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from .config import Account, Campaign, Settings
from .db import (
    add_clip,
    clips_for_source,
    future_scheduled_slots,
    get_source,
    set_clip_status,
    connect,
    create_job,
    finish_job,
    init_db,
    list_sources,
    set_source_status,
)
from .media import MediaError, probe
from .publish import publish_approved, publish_clip, schedule_slot
from .render import render_clip
from .review import write_review_html
from .scan import scan
from .select import select_clips
from .sources import sync_sources
from .transcribe import ensure_transcript
from .translate import translate_segments, translate_texts

log = logging.getLogger(__name__)

LOCK_STALE_SECONDS = 6 * 3600


class AlreadyRunning(RuntimeError):
    pass


class RunLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle: int | None = None

    def __enter__(self) -> "RunLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            try:
                self.handle = os.open(
                    self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                )
                os.write(self.handle, f"{os.getpid()} {time.time()}".encode())
                return self
            except FileExistsError:
                try:
                    age = time.time() - self.path.stat().st_mtime
                except OSError:
                    age = LOCK_STALE_SECONDS + 1
                if age > LOCK_STALE_SECONDS and attempt == 0:
                    log.warning("lock lama dihapus: %s", self.path)
                    self.path.unlink(missing_ok=True)
                    continue
                raise AlreadyRunning(f"proses lain sedang berjalan ({self.path})")
        raise AlreadyRunning("gagal membuat lock")

    def __exit__(self, *_: object) -> None:
        if self.handle is not None:
            os.close(self.handle)
            self.handle = None
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass


def _subtitles_in_target_language(
    settings: Settings, transcript: dict[str, Any], candidates: list[Any]
) -> dict[str, Any]:
    """Translate only the segments inside the selected clips, keeping timings."""
    target = settings.render.subtitle_language.strip()
    if not settings.render.subtitles or not target:
        return transcript
    source_language = str(transcript.get("language") or "").split("-")[0]
    if source_language == target:
        return transcript
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        log.warning("subtitle_language=%s tanpa GEMINI_API_KEY, subtitle dilewati", target)
        return transcript

    cache_dir = settings.paths.work / "translate"
    windows = [
        segment
        for segment in transcript.get("segments", [])
        if any(segment["end"] > c.start and segment["start"] < c.end for c in candidates)
    ]
    translated = translate_segments(
        windows,
        target=target,
        model=settings.selection.gemini_model,
        api_key=api_key,
        cache_dir=cache_dir,
    )
    return {**transcript, "segments": translated}


def _titles_in_target_language(
    settings: Settings, candidates: list[Any]
) -> list[Any]:
    """Translate candidate titles and captions so they match the subtitle language."""
    target = settings.render.subtitle_language.strip()
    if not target or not candidates:
        return candidates
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return candidates

    texts: list[str] = []
    for candidate in candidates:
        texts.extend([candidate.title, candidate.caption, candidate.topic])
    translated = translate_texts(
        texts,
        target=target,
        model=settings.selection.gemini_model,
        api_key=api_key,
        cache_dir=settings.paths.work / "translate",
    )
    updated = []
    for index, candidate in enumerate(candidates):
        updated.append(
            replace(
                candidate,
                title=translated[index * 3],
                caption=translated[index * 3 + 1],
                topic=translated[index * 3 + 2],
            )
        )
    return updated


def _pick_account(settings: Settings) -> Account:
    for account in settings.enabled_accounts():
        if account.rights_approved:
            return account
    raise RuntimeError("tidak ada akun enabled dengan rights_approved")


def source_account_id(settings: Settings, path: str) -> str | None:
    """Akun yang dipetakan ke sebuah file sumber (prefix nama file)."""
    key = Path(path).name.split("-", 1)[0]
    for src in settings.sources:
        if src.id == key:
            return src.account_id
    return None


def account_for_source(settings: Settings, source) -> Account:
    """Pilih akun sesuai prefix nama file sumber (mis. jkt48-xxxx.mp4)."""
    key = Path(source["path"]).name.split("-", 1)[0]
    for src in settings.sources:
        if src.id != key:
            continue
        for account in settings.enabled_accounts():
            if account.id == src.account_id and account.rights_approved:
                return account
        raise RuntimeError(
            f"source {key}: akun {src.account_id} belum enabled/rights_approved"
        )
    return _pick_account(settings)


def _watermark_for(settings: Settings, media_path: Path) -> str:
    """Watermark kampanye dari prefix nama file (mis. jkt48-xxxx.mp4)."""
    key = media_path.name.split("-", 1)[0]
    for source in settings.sources:
        if source.id == key:
            return source.watermark
    return ""


def campaign_for_media(settings: Settings, media_path: Path) -> Campaign | None:
    """Campaign terpakai (aktif + ada budget) untuk sumber, prefix nama file."""
    key = media_path.name.split("-", 1)[0]
    for source in settings.sources:
        if source.id == key and source.campaign:
            pinned = settings.campaign(source.campaign)
            if pinned is not None and pinned.usable():
                return pinned
            break
    return settings.best_campaign(key)


def _watermark_image_for(settings: Settings, media_path: Path) -> Path | None:
    campaign = campaign_for_media(settings, media_path)
    if campaign is None or not campaign.watermark_image:
        return None
    candidate = Path(campaign.watermark_image)
    if not candidate.is_absolute():
        candidate = settings.root / candidate
    return candidate if candidate.exists() else None


def process_source(
    settings: Settings,
    conn,
    source,
    account: Account,
    force: bool = False,
) -> list[int]:
    source_id = int(source["id"])
    if source["status"] == "processed" and not force:
        log.info("source #%s sudah diproses", source_id)
        return []
    media_path = Path(source["path"])
    if not media_path.exists():
        set_source_status(conn, source_id, "failed", "file sumber hilang")
        return []

    set_source_status(conn, source_id, "processing")
    created_clips: list[int] = []
    job = create_job(conn, source_id, "transcribe")
    try:
        transcript = ensure_transcript(settings, source, force=force)
    except Exception as exc:
        finish_job(conn, job, "failed", str(exc))
        set_source_status(conn, source_id, "failed", str(exc))
        log.exception("transkripsi gagal untuk source #%s", source_id)
        return []
    finish_job(conn, job, "done")

    job = create_job(conn, source_id, "select")
    try:
        candidates = select_clips(transcript, settings, account)
    except Exception as exc:
        finish_job(conn, job, "failed", str(exc))
        set_source_status(conn, source_id, "failed", str(exc))
        log.exception("seleksi gagal untuk source #%s", source_id)
        return []
    finish_job(conn, job, "done")
    if not candidates:
        message = "tidak ada kandidat lolos ambang skor"
        set_source_status(conn, source_id, "processed", message)
        log.warning("source #%s: %s", source_id, message)
        return []

    try:
        info = probe(media_path)
    except MediaError as exc:
        set_source_status(conn, source_id, "failed", str(exc))
        log.error("probe gagal: %s", exc)
        return []

    transcript = _subtitles_in_target_language(settings, transcript, candidates)
    candidates = _titles_in_target_language(settings, candidates)

    job = create_job(conn, source_id, "render")
    try:
        for candidate in candidates:
            try:
                rendered = render_clip(
                    media_path,
                    info,
                    candidate.start,
                    candidate.end,
                    candidate.title,
                    settings,
                    transcript,
                    settings.paths.review / "clips",
                    source_id,
                    watermark=_watermark_for(settings, media_path),
                    watermark_image=_watermark_image_for(settings, media_path),
                )
            except Exception as exc:
                log.exception(
                    "render gagal source #%s %.1f-%.1f",
                    source_id,
                    candidate.start,
                    candidate.end,
                )
                continue
            clip_id = add_clip(
                conn,
                source_id=source_id,
                account_id=account.id,
                start=candidate.start,
                end=candidate.end,
                file_path=str(rendered.path),
                file_hash=rendered.sha256,
                title=candidate.title,
                topic=candidate.topic,
                scores_json=json.dumps(candidate.as_dict(), ensure_ascii=False),
                viral_score=candidate.viral_score,
                niche_fit=candidate.niche_fit,
                final_score=candidate.final_score(),
            )
            created_clips.append(clip_id)
            log.info(
                "clip #%s %.1fs-%.1fs score=%.1f %s",
                clip_id,
                candidate.start,
                candidate.end,
                candidate.final_score(),
                candidate.title,
            )
            if len(created_clips) >= settings.safety.max_clips_per_source:
                break
    except Exception as exc:
        finish_job(conn, job, "failed", str(exc))
        set_source_status(conn, source_id, "failed", str(exc))
        return created_clips
    finish_job(conn, job, "done")
    if not created_clips:
        set_source_status(conn, source_id, "failed", "semua render gagal")
        return []
    set_source_status(conn, source_id, "processed")
    if settings.upload.auto_publish:
        _auto_publish(settings, conn, created_clips)
    return created_clips


def _youtube_allowed(settings: Settings, conn, clip_id: int) -> bool:
    """Klip campaign TikTok-only tidak boleh diunggah ke YouTube."""
    row = conn.execute(
        "SELECT s.path FROM clips c JOIN sources s ON s.id = c.source_id WHERE c.id = ?",
        (clip_id,),
    ).fetchone()
    if row is None:
        return True
    campaign = campaign_for_media(settings, Path(str(row[0])))
    if campaign is None:
        return True
    return "youtube" in campaign.platforms


def _auto_publish(settings: Settings, conn, clip_ids: list[int]) -> None:
    # pilih slot bebas pertama; slot yang sudah dipakai (terjadwal) dilewati
    # agar tidak dobel antar-run.
    used = future_scheduled_slots(conn)
    for clip_id in clip_ids:
        if not _youtube_allowed(settings, conn, clip_id):
            set_clip_status(conn, clip_id, "approved")
            log.info(
                "clip #%s: campaign TikTok-only, lewati upload YouTube", clip_id
            )
            continue
        try:
            set_clip_status(conn, clip_id, "approved")
            slot = schedule_slot(settings, 0, used)
            remote = publish_clip(settings, conn, clip_id, publish_at=slot)
            used.add(slot)
            log.info("auto-publish clip #%s -> %s", clip_id, remote)
        except Exception as exc:
            log.warning("auto-publish clip #%s gagal: %s", clip_id, exc)


def resqueeze_source(
    settings: Settings,
    conn,
    source_id: int,
    extra_clips: int = 5,
    min_score: float | None = None,
) -> list[int]:
    """Cari klip tambahan dari sumber yang sudah diproses, tanpa duplikasi."""
    source = get_source(conn, source_id)
    account = _pick_account(settings)
    media_path = Path(source["path"])
    if not media_path.exists():
        raise RuntimeError(f"file sumber hilang: {media_path}")
    transcript = ensure_transcript(settings, source, force=False)

    selection = replace(
        settings.selection,
        clips_per_video=extra_clips + 4,
        min_score=min_score if min_score is not None else settings.selection.min_score,
    )
    safety = replace(settings.safety, max_clips_per_source=extra_clips + 4)
    squeeze = replace(settings, selection=selection, safety=safety)
    candidates = select_clips(transcript, squeeze, account)
    if not candidates:
        return []

    existing = clips_for_source(conn, source_id)

    def overlaps(candidate: Any) -> bool:
        for row in existing:
            s = float(row["start"])
            e = float(row["end"])
            inter = max(0.0, min(candidate.end, e) - max(candidate.start, s))
            short = min(candidate.duration, e - s)
            if short > 0 and inter / short > 0.4:
                return True
        return False

    fresh = [c for c in candidates if not overlaps(c)][:extra_clips]
    if not fresh:
        log.info("resqueeze #%s: semua kandidat tumpang tindih", source_id)
        return []

    info = probe(media_path)
    transcript_t = _subtitles_in_target_language(settings, transcript, fresh)
    cand_t = _titles_in_target_language(settings, fresh)
    created: list[int] = []
    for candidate in cand_t:
        try:
            rendered = render_clip(
                media_path,
                info,
                candidate.start,
                candidate.end,
                candidate.title,
                settings,
                transcript_t,
                settings.paths.review / "clips",
                source_id,
                watermark=_watermark_for(settings, media_path),
                watermark_image=_watermark_image_for(settings, media_path),
            )
        except Exception as exc:
            log.exception(
                "render gagal (resqueeze) #%s %.1f-%.1f",
                source_id,
                candidate.start,
                candidate.end,
            )
            continue
        clip_id = add_clip(
            conn,
            source_id=source_id,
            account_id=account.id,
            start=candidate.start,
            end=candidate.end,
            file_path=str(rendered.path),
            file_hash=rendered.sha256,
            title=candidate.title,
            topic=candidate.topic,
            scores_json=json.dumps(candidate.as_dict(), ensure_ascii=False),
            viral_score=candidate.viral_score,
            niche_fit=candidate.niche_fit,
            final_score=candidate.final_score(),
        )
        created.append(clip_id)
        log.info(
            "clip #%s %.1fs-%.1fs score=%.1f %s (resqueeze)",
            clip_id,
            candidate.start,
            candidate.end,
            candidate.final_score(),
            candidate.title,
        )
    if created and settings.upload.auto_publish:
        _auto_publish(settings, conn, created)
    return created


def cleanup_work(settings: Settings) -> None:
    days = settings.safety.retain_work_days
    if days <= 0:
        return
    cutoff = time.time() - days * 86400
    work = settings.paths.work
    if not work.exists():
        return
    for path in work.rglob("*.transcript.json"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink(missing_ok=True)
                log.info("hapus cache lama: %s", path.name)
        except OSError:
            pass


def run(
    settings: Settings, limit: int | None = None, account_id: str | None = None
) -> dict[str, Any]:
    settings.validate_for_run()
    conn = connect(settings.paths.database)
    init_db(conn)
    summary: dict[str, Any] = {
        "scanned": 0,
        "downloaded": 0,
        "processed": 0,
        "clips": 0,
        "published": 0,
        "errors": [],
    }
    try:
        with RunLock(settings.paths.database.parent / "run.lock"):
            synced = sync_sources(settings, account=account_id)
            summary["downloaded"] = len(synced["downloaded"])
            summary["errors"].extend(synced["errors"])
            summary["scanned"] = len(scan(settings, conn))
            maximum = min(
                limit or settings.safety.max_sources_per_run,
                settings.safety.max_sources_per_run,
            )
            sources = list_sources(conn, "new")
            if account_id is not None:
                sources = [
                    s
                    for s in sources
                    if source_account_id(settings, s["path"]) == account_id
                ]
            for source in sources[:maximum]:
                try:
                    source_account = account_for_source(settings, source)
                    clips = process_source(settings, conn, source, source_account)
                    summary["processed"] += 1
                    summary["clips"] += len(clips)
                except Exception as exc:
                    summary["errors"].append(f"source #{source['id']}: {exc}")
                    log.exception("source #%s gagal", source["id"])
            if sources:
                write_review_html(settings, conn, account_id=account_id)
            published = publish_approved(settings, conn, account_id=account_id)
            summary["published"] = len(published["published"])
            summary["errors"].extend(published["errors"])
            cleanup_work(settings)
    finally:
        conn.close()
    return summary

def longcut_source(
    settings: Settings,
    conn,
    source_id: int,
    *,
    minutes: int = 10,
    start: float | None = None,
) -> int | None:
    """Satu video panjang 16:9 (default 10 menit) dari sumber yang sudah diproses.

    ponytail: memilih jendela berdasarkan kerapatan bicara, bukan semantik.
    Kalau butuh momen puncak, pakai `resqueeze` lalu gabung manual.
    """
    from .select import snap_to_speech

    source = get_source(conn, source_id)
    media_path = Path(source["path"])
    if not media_path.exists():
        raise RuntimeError(f"file sumber hilang: {media_path}")
    transcript = ensure_transcript(settings, source, force=False)
    duration = float(transcript.get("duration") or source["duration"] or 0)
    target = max(120.0, minutes * 60.0)
    if duration < target:
        raise RuntimeError(
            f"sumber #{source_id} hanya {duration/60:.1f} menit, tidak cukup untuk {minutes} menit"
        )
    begin = float(start) if start is not None else 0.0
    end = min(duration, begin + target)
    begin, end = snap_to_speech(transcript.get("segments") or [], begin, end)

    account = account_for_source(settings, source)
    info = probe(media_path)
    label = f"{Path(source['path']).name.split('-', 1)[0].title()} {int(end - begin)//60} Menit"
    rendered = render_clip(
        media_path,
        info,
        begin,
        end,
        label,
        settings,
        transcript,
        settings.paths.review / "clips",
        source_id,
        watermark=_watermark_for(settings, media_path),
        watermark_image=None,
        longform=True,
    )
    clip_id = add_clip(
        conn,
        source_id=source_id,
        account_id=account.id,
        start=begin,
        end=end,
        file_path=str(rendered.path),
        file_hash=rendered.sha256,
        title=label,
        topic="longform",
        scores_json="{}",
        viral_score=0.0,
        niche_fit=0.0,
        final_score=0.0,
    )
    set_clip_status(conn, clip_id, "approved")
    log.info(
        "longcut #%s %.1fs-%.1fs (%.1f menit) -> %s",
        clip_id,
        begin,
        end,
        (end - begin) / 60,
        rendered.path,
    )
    return clip_id
