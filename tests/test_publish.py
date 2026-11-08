from __future__ import annotations

import hashlib

import pytest

from autoclip import publish
from autoclip.config import load_settings
from autoclip.db import (
    add_clip,
    connect,
    create_source,
    get_clip,
    get_publication,
    init_db,
    record_review,
)
from autoclip.publish import PublishError, publish_clip

ACCOUNTS = """
accounts:
  - id: utama
    display_name: "Akun Utama"
    niche: bisnis
    enabled: true
    rights_approved: true
    approval_required: true
    platforms:
      youtube:
        enabled: true
        privacy: private
"""


def _settings(settings):
    (settings.root / "config" / "accounts.yaml").write_text(ACCOUNTS, encoding="utf-8")
    return load_settings(settings.root)


def _clip(conn, tmp_path, status: str = "approved", source_id: int | None = None):
    clip_file = tmp_path / "clip.mp4"
    clip_file.write_bytes(b"clip-bytes")
    if source_id is None:
        source_id = create_source(conn, "source.mp4", "hash-source", 100)
        assert source_id is not None
    clip_id = add_clip(
        conn,
        source_id=source_id,
        account_id="utama",
        start=10,
        end=40,
        file_path=str(clip_file),
        file_hash=hashlib.sha256(b"clip-bytes").hexdigest(),
        title="Judul",
        topic="bisnis",
        scores_json="{}",
        viral_score=80,
        niche_fit=90,
        final_score=83,
    )
    if status == "approved":
        record_review(conn, clip_id, "approved", "tester", "hash")
    return clip_id


def test_caption_uses_payoff_line(settings, tmp_path):
    from dataclasses import replace

    loaded = _settings(settings)
    loaded = replace(
        loaded,
        upload=replace(
            loaded.upload, hashtags="#windahbasudara #windahMKLIP2 #motionklip"
        ),
    )
    conn = connect(":memory:")
    init_db(conn)
    clip_id = _clip(conn, tmp_path)
    clip = get_clip(conn, clip_id)
    transcript = {
        "segments": [
            {"start": 10, "end": 12, "text": "awal cerita biasa"},
            {"start": 35, "end": 40, "text": "opah nya baik banget sih"},
        ]
    }
    caption = publish._tiktok_caption(loaded, conn, clip, transcript)
    assert caption.startswith("opah nya baik banget sih")
    assert "😱" in caption
    assert "#" in caption
    assert len(caption.split("#")[0].strip()) <= 66


def test_slots_are_per_platform(settings, tmp_path):
    from datetime import datetime, timedelta, timezone

    from autoclip.db import begin_publication, finish_publication, future_scheduled_slots

    _settings(settings)
    conn = connect(":memory:")
    init_db(conn)
    clip_id = _clip(conn, tmp_path)
    slot = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    begin_publication(conn, clip_id, "youtube", "utama", scheduled_at=slot)
    finish_publication(conn, clip_id, "youtube", "utama", remote_id="yt-1")
    assert future_scheduled_slots(conn, "youtube") == {slot}
    assert future_scheduled_slots(conn, "tiktok") == set()


def test_publish_approved_skips_tiktok_only_campaign(settings, tmp_path, monkeypatch):
    from dataclasses import replace

    from autoclip.config import Campaign, Source
    from autoclip.db import connect as db_connect, init_db

    campaign = Campaign(
        id="windah-tt", label="Windah TT", source="windah3",
        platforms=("tiktok",), mode="per_video", cpm=4500.0, fixed_payout=0.0,
        min_views=3000, max_claim_views=0, payout_methods=("gopay",),
        hashtags="#windahbasudara", watermark="MKLP", watermark_image="",
        required_tag="MKLP", budget_left_pct=100.0, max_videos_per_month=0,
        active=True, verified=True, note="",
    )
    source = Source(
        id="windah3", url="", account_id="utama", enabled=True,
        rights_approved=True, rights_risk_accepted=False, rights_reference="",
        latest=0, fallback_popular=False, campaign="windah-tt", watermark="MKLP",
    )
    loaded = replace(
        _settings(settings), campaigns=(campaign,), sources=(source,)
    )
    conn = db_connect(":memory:")
    init_db(conn)
    source_id = create_source(conn, "windah3-abc.mp4", "hash-tt", 100)
    _clip(conn, tmp_path, source_id=source_id)

    calls: list[str] = []
    monkeypatch.setattr(
        publish, "publish_clip",
        lambda *args, **kwargs: calls.append("upload") or "yt-id",
    )
    summary = publish.publish_approved(loaded, conn, only_auto=False)
    assert calls == []
    assert summary["published"] == []


def test_publish_is_idempotent(settings, monkeypatch, tmp_path):
    loaded = _settings(settings)
    conn = connect(":memory:")
    init_db(conn)
    clip_id = _clip(conn, tmp_path)
    calls = []

    def fake_upload(settings, account_id, clip, privacy="private", **kwargs):
        calls.append((account_id, privacy))
        return "video-123"

    monkeypatch.setattr(publish.youtube, "upload_video", fake_upload)
    assert publish_clip(loaded, conn, clip_id) == "video-123"
    assert publish_clip(loaded, conn, clip_id) == "video-123"
    assert calls == [("utama", "private")]
    row = get_publication(conn, clip_id, "youtube", "utama")
    assert row["status"] == "published"
    assert row["remote_id"] == "video-123"


def test_publish_requires_approved(settings, tmp_path):
    loaded = _settings(settings)
    conn = connect(":memory:")
    init_db(conn)
    clip_id = _clip(conn, tmp_path, status="pending")
    with pytest.raises(PublishError):
        publish_clip(loaded, conn, clip_id)


def test_publish_rejects_changed_file(settings, monkeypatch, tmp_path):
    loaded = _settings(settings)
    conn = connect(":memory:")
    init_db(conn)
    clip_id = _clip(conn, tmp_path)
    (tmp_path / "clip.mp4").write_bytes(b"changed")
    monkeypatch.setattr(
        publish.youtube, "upload_video", lambda *args, **kwargs: "video-123"
    )
    with pytest.raises(PublishError):
        publish_clip(loaded, conn, clip_id)
    assert get_clip(conn, clip_id)["status"] == "approved"

