from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from . import youtube
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

log = logging.getLogger(__name__)


class PublishError(RuntimeError):
    pass


def _campaign_hashtags(settings: Settings, conn, clip) -> str:
    """Hashtag wajib dari campaign yang terhubung ke sumber klip."""
    try:
        source = get_source(conn, int(clip["source_id"]))
    except Exception:
        return ""
    key = Path(str(source["path"])).name.split("-", 1)[0]
    for campaign in settings.campaigns_for_source(key):
        if campaign.active and campaign.hashtags:
            return campaign.hashtags
    return ""


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
    if platform != "youtube":
        raise PublishError(
            "TikTok belum diimplementasikan; Direct Post publik juga butuh audit TikTok."
        )
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
    try:
        remote_id = youtube.upload_video(
            settings,
            account.id,
            clip,
            privacy=account.youtube_privacy,
            upload=settings.upload,
            publish_at=publish_at,
            extra_hashtags=_campaign_hashtags(settings, conn, clip),
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
    description = youtube._description(clip, settings.upload)
    tags = [
        tag.lstrip("#") for tag in youtube._hashtag_list(settings.upload.hashtags)
    ][:15]
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
    used = future_scheduled_slots(conn) if schedule else set()
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

