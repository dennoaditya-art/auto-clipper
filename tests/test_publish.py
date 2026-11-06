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


def _clip(conn, tmp_path, status: str = "approved"):
    clip_file = tmp_path / "clip.mp4"
    clip_file.write_bytes(b"clip-bytes")
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
    from autoclip.db import begin_publication, finish_publication, future_scheduled_slots

    _settings(settings)
    conn = connect(":memory:")
    init_db(conn)
    clip_id = _clip(conn, tmp_path)
    begin_publication(
        conn, clip_id, "youtube", "utama", scheduled_at="2026-11-08T11:00:00Z"
    )
    finish_publication(conn, clip_id, "youtube", "utama", remote_id="yt-1")
    assert future_scheduled_slots(conn, "youtube") == {"2026-11-08T11:00:00Z"}
    assert future_scheduled_slots(conn, "tiktok") == set()


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

