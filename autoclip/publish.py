from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import tiktok, youtube
from .config import Account, Settings
from .db import (
    begin_publication,
    count_future_scheduled,
    finish_publication,
    future_scheduled_slots,
    get_clip,
    get_publication,
    get_source,
    list_clips,
)
from .media import sha256_file
from .transcribe import transcript_path

log = logging.getLogger(__name__)


class PublishError(RuntimeError):
    pass


def _source_meta(
    settings: Settings, conn, clip, platform: str = "youtube"
) -> tuple[str, str]:
    """(hashtags, credit) milik sumber klip.

    Tanpa ini, semua klip memakai credit/hashtag global (mis. JKT48) walau
    sumbernya Windah atau podcast lain: metadata salah sasaran membuat
    YouTube menayangkan klip ke audiens yang tidak mencarinya.
    """
    fallback = (settings.upload.hashtags, settings.upload.credit)
    try:
        source = get_source(conn, int(clip["source_id"]))
    except Exception:
        return fallback
    key = Path(str(source["path"])).name.split("-", 1)[0]
    cfg = settings.source_by_key(key)
    if cfg is not None:
        key = cfg.id
    for campaign in settings.campaigns_for_source(key):
        if campaign.active and campaign.hashtags and platform in campaign.platforms:
            return campaign.hashtags, ""
    if cfg is not None:
        return cfg.hashtags or fallback[0], cfg.credit or fallback[1]
    if key:
        # sumber lama/tak terdaftar: turunkan metadata dari nama file, jangan
        # pakai global (global bisa milik channel lain -> audiens salah).
        return f"#{key} #shortsindonesia", f"Sumber: {key.title()}. Klip dikutip untuk sorotan."
    return fallback


def _upload_for(settings: Settings, conn, clip, platform: str = "youtube"):
    """UploadConfig dengan credit/hashtag milik sumber klip."""
    hashtags, credit = _source_meta(settings, conn, clip, platform)
    return replace(settings.upload, hashtags=hashtags, credit=credit)


def _account(settings: Settings, account_id: str) -> Account:
    for account in settings.accounts:
        if account.id == account_id:
            return account
    raise PublishError(f"akun tidak ditemukan: {account_id}")


def _slot_times(settings: Settings, count: int) -> list[str]:
    zone = timezone(timedelta(hours=settings.upload.utc_offset_hours))
    now = datetime.now(zone)
    day = now.date()
    result: list[str] = []
    while len(result) < count:
        clocks = getattr(settings.upload, "slots_by_day", {}).get(
            day.strftime("%A"), settings.upload.slots
        )
        for clock in clocks:
            hour, minute = (int(part) for part in clock.split(":"))
            when = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
            if when > now:
                result.append(when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
                if len(result) >= count:
                    break
        day += timedelta(days=1)
    return result


def schedule_slot(
    settings: Settings, offset: int = 0, used: set[str] | None = None
) -> str:
    upload = settings.upload
    if upload.slots or getattr(upload, "slots_by_day", {}):
        if used:
            pool = _slot_times(settings, offset + 1 + len(used) + 10)
            free = [slot for slot in pool if slot not in used]
            if offset < len(free):
                return free[offset]
            return pool[-1]
        return _slot_times(settings, offset + 1)[-1]
    if upload.schedule_start:
        try:
            start = datetime.fromisoformat(upload.schedule_start.replace("Z", "+00:00"))
        except ValueError as exc:
            raise PublishError(
                f"upload.schedule_start bukan ISO-8601: {upload.schedule_start}"
            ) from exc
        if start.tzinfo is None:
            raise PublishError("upload.schedule_start harus menyertakan zona waktu (mis. Z)")
    else:
        start = datetime.now(timezone.utc) + timedelta(hours=1)
    when = start.astimezone(timezone.utc) + timedelta(
        hours=upload.schedule_interval_hours * offset
    )
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


HORROR_WORDS = ("opah", "hantu", "seram", "jumpscare", "backroom", "pocong")


def _payoff_line(clip, transcript: dict | None) -> str:
    """Kalimat punchline klip = segmen terakhir di dalam rentang klip."""
    if not transcript:
        return ""
    segments = transcript.get("segments") or []
    start, end = float(clip["start"]), float(clip["end"])
    if 0 < end <= start + 1:
        end = start + end
    inside = [
        s
        for s in segments
        if float(s.get("start", 0.0)) >= start - 1.0
        and float(s.get("end", 0.0)) <= end + 1.0
    ]
    if not inside:
        return ""
    return " ".join(str(inside[-1].get("text") or "").split())


def _meme_caption(text: str, limit: int = 60) -> str:
    """Potong satu kalimat meme pada batas kata, tanpa tanda kutip."""
    clean = " ".join(str(text).replace('"', "").replace("“", "").replace("”", "").split())
    if len(clean) <= limit:
        return clean
    cut = clean[:limit].rsplit(" ", 1)[0].rstrip(" ,.-")
    return cut or clean[:limit]


def _tiktok_caption(settings: Settings, conn, clip, transcript: dict | None = None) -> str:
    """Caption TikTok = baris payoff, bukan caption naratif LLM."""
    caption = _meme_caption(_payoff_line(clip, transcript))
    if not caption:
        try:
            data = json.loads(clip["scores_json"] or "{}")
        except (TypeError, ValueError):
            data = {}
        caption = _meme_caption(str(data.get("caption") or "").strip())
    if not caption:
        caption = _meme_caption(str(clip["title"]))
    low = caption.lower()
    emoji = "😱" if any(word in low for word in HORROR_WORDS) else "😹"
    caption = f"{caption} {emoji}"
    hashtags, _credit = _source_meta(settings, conn, clip, "tiktok")
    missing = [tag for tag in hashtags.split() if tag and tag not in caption]
    if missing:
        caption = f"{caption} {' '.join(missing)}"
    return caption[:2200]


def _clip_transcript(settings: Settings, conn, clip) -> dict | None:
    """Transkrip sumber klip; dipakai untuk caption payoff."""
    try:
        source = get_source(conn, int(clip["source_id"]))
        path = transcript_path(settings, str(source["sha256"]))
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        log.debug("transkrip klip #%s tidak terbaca", clip["id"])
    return None


def _publish_tiktok(
    settings: Settings, conn, clip, account: Account, publish_at: str | None
) -> str:
    if publish_at is None:
        raise PublishError("TikTok wajib dijadwalkan; pakai --schedule")
    existing = get_publication(conn, int(clip["id"]), "tiktok", account.id)
    if existing and existing["status"] == "published":
        return str(existing["remote_id"])
    when = datetime.strptime(publish_at, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=timezone.utc
    ).astimezone(timezone(timedelta(hours=settings.upload.utc_offset_hours)))
    caption = _tiktok_caption(settings, conn, clip, _clip_transcript(settings, conn, clip))
    begin_publication(conn, int(clip["id"]), "tiktok", account.id, scheduled_at=publish_at)
    try:
        url = tiktok.publish_clip(settings, clip, caption, when)
    except Exception as exc:
        finish_publication(
            conn, int(clip["id"]), "tiktok", account.id, error=str(exc)[:1000]
        )
        raise PublishError(str(exc)) from exc
    finish_publication(conn, int(clip["id"]), "tiktok", account.id, remote_id=url)
    log.info("clip #%s terjadwal di TikTok: %s", clip["id"], when.strftime("%Y-%m-%d %H:%M"))
    return url


def publish_clip(
    settings: Settings,
    conn,
    clip_id: int,
    *,
    platform: str = "youtube",
    account_id: str | None = None,
    publish_at: str | None = None,
) -> str:
    clip = get_clip(conn, clip_id)
    if clip["status"] != "approved":
        raise PublishError(f"clip {clip_id} berstatus {clip['status']}, belum approved")
    account = _account(settings, account_id or clip["account_id"])
    if not account.enabled or not account.rights_approved:
        raise PublishError(f"akun {account.id} belum enabled/rights_approved")
    if platform == "tiktok":
        if not account.tiktok_enabled:
            raise PublishError(f"platform tiktok belum enabled untuk akun {account.id}")
        return _publish_tiktok(settings, conn, clip, account, publish_at)
    if platform != "youtube":
        raise PublishError(f"platform tidak dikenal: {platform}")
    if not account.youtube_enabled:
        raise PublishError(f"platform youtube belum enabled untuk akun {account.id}")
    path = Path(clip["file_path"])
    try:
        digest = sha256_file(path)
    except OSError as exc:
        raise PublishError(f"file klip tidak bisa dibaca: {exc}") from exc
    if digest != clip["file_hash"]:
        raise PublishError("hash klip berubah; render ulang sebelum upload")
    existing = get_publication(conn, clip_id, platform, account.id)
    if existing and existing["status"] == "published":
        return str(existing["remote_id"])
    begin_publication(conn, clip_id, platform, account.id, scheduled_at=publish_at)
    upload = _upload_for(settings, conn, clip, platform)
    try:
        remote_id = youtube.upload_video(
            settings,
            account.id,
            clip,
            privacy=account.youtube_privacy,
            upload=upload,
            publish_at=publish_at,
            extra_hashtags="",
        )
    except Exception as exc:
        finish_publication(
            conn,
            clip_id,
            platform,
            account.id,
            error=str(exc)[:1000],
        )
        raise PublishError(str(exc)) from exc
    finish_publication(
        conn,
        clip_id,
        platform,
        account.id,
        remote_id=remote_id,
    )
    log.info("clip #%s terunggah ke YouTube: %s", clip_id, remote_id)
    return remote_id


def release_clip(
    settings: Settings,
    conn,
    clip_id: int,
    *,
    account_id: str | None = None,
    privacy: str = "public",
) -> dict[str, Any]:
    clip = get_clip(conn, clip_id)
    if clip is None:
        raise PublishError(f"clip {clip_id} tidak ditemukan")
    account = _account(settings, account_id or str(clip["account_id"]))
    publication = get_publication(conn, clip_id, "youtube", account.id)
    if publication is None or publication["status"] != "published":
        raise PublishError(f"clip {clip_id} belum terunggah ke YouTube")
    description = youtube._description(clip, _upload_for(settings, conn, clip, "youtube"))
    hashtags = _source_meta(settings, conn, clip, "youtube")[0]
    tags = [tag.lstrip("#") for tag in youtube._hashtag_list(hashtags)][:15]
    youtube.update_video(
        settings,
        account.id,
        str(publication["remote_id"]),
        description=description,
        tags=tags,
        privacy=privacy,
    )
    log.info("clip #%s dirilis %s: %s", clip_id, privacy, publication["remote_id"])
    return {"remote_id": str(publication["remote_id"]), "privacy": privacy}


def publish_approved(
    settings: Settings,
    conn,
    limit: int | None = None,
    *,
    only_auto: bool = True,
    schedule: bool = False,
    account_id: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {"published": [], "errors": []}
    accounts = [
        a
        for a in settings.enabled_accounts()
        if a.youtube_enabled and (a.auto_publish or not only_auto)
    ]
    if account_id is not None:
        accounts = [a for a in accounts if a.id == account_id]
    if not accounts:
        return summary
    account_ids = {a.id for a in accounts}
    used = future_scheduled_slots(conn, "youtube") if schedule else set()
    count = 0
    for clip in list_clips(conn, "approved"):
        if clip["account_id"] not in account_ids:
            continue
        existing = get_publication(
            conn, int(clip["id"]), "youtube", str(clip["account_id"])
        )
        if existing and existing["status"] == "published":
            continue
        slot = schedule_slot(settings, 0, used) if schedule else None
        try:
            remote_id = publish_clip(
                settings,
                conn,
                int(clip["id"]),
                publish_at=slot,
            )
        except PublishError as exc:
            summary["errors"].append(f"clip #{clip['id']}: {exc}")
            log.error("publish clip #%s gagal: %s", clip["id"], exc)
            continue
        if slot:
            used.add(slot)
        summary["published"].append((int(clip["id"]), remote_id))
        count += 1
        if limit and count >= limit:
            break
    return summary

