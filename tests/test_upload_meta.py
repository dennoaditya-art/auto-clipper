from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from autoclip.config import UploadConfig
from autoclip.publish import schedule_slot
from autoclip.youtube import UploadError, _check_publish_at, _metadata

CLIP = {"title": "Hook keren", "topic": "hiburan"}
UPLOAD = UploadConfig(
    hashtags="#shorts #fyp",
    credit="Sumber: contoh",
    thumbnail=True,
    schedule_start="",
    schedule_interval_hours=6.0,
)


def test_metadata_description_and_tags():
    meta = _metadata(CLIP, "private", UPLOAD)
    assert "Sumber: contoh" in meta["snippet"]["description"]
    assert meta["snippet"]["tags"] == ["shorts", "fyp"]
    assert "publishAt" not in meta["status"]


def test_publish_at_forces_private():
    meta = _metadata(CLIP, "public", UPLOAD, "2099-01-01T00:00:00Z")
    assert meta["status"]["privacyStatus"] == "private"
    assert meta["status"]["publishAt"] == "2099-01-01T00:00:00Z"


def test_publish_at_rejects_past_and_naive():
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with pytest.raises(UploadError):
        _check_publish_at(past)
    with pytest.raises(UploadError):
        _check_publish_at("2099-01-01T00:00:00")


def test_schedule_slot_step():
    settings = type("S", (), {"upload": UPLOAD})()
    first = schedule_slot(settings, 0)
    second = schedule_slot(settings, 1)
    gap = datetime.fromisoformat(second.replace("Z", "+00:00")) - datetime.fromisoformat(
        first.replace("Z", "+00:00")
    )
    assert gap == timedelta(hours=6)
    assert _check_publish_at(first)
