from __future__ import annotations

import hashlib
import os
import shutil
import time

import pytest

from autoclip.db import (
    add_clip,
    connect,
    create_source,
    get_clip,
    init_db,
)
from autoclip.media import sha256_file
from autoclip.review import ReviewError, approve, write_review_html
from autoclip.scan import scan


def test_scan_dedupe(settings, video):
    target = settings.paths.incoming / video.name
    shutil.copyfile(video, target)
    old = time.time() - 3600
    os.utime(target, (old, old))
    conn = connect(settings.paths.database)
    init_db(conn)
    assert scan(settings, conn) == [1]
    assert scan(settings, conn) == []
    conn.close()


def test_approve_hash_invalidation(settings, tmp_path):
    clip_file = tmp_path / "clip.mp4"
    clip_file.write_bytes(b"video-bytes")
    digest = hashlib.sha256(b"video-bytes").hexdigest()
    conn = connect(":memory:")
    init_db(conn)
    source_id = create_source(conn, "a.mp4", "hash-a", 100)
    clip_id = add_clip(
        conn,
        source_id=source_id,
        account_id="utama",
        start=10,
        end=40,
        file_path=str(clip_file),
        file_hash=digest,
        title="Judul",
        topic="bisnis",
        scores_json="{}",
        viral_score=80,
        niche_fit=90,
        final_score=83,
    )
    approve(conn, clip_id, "tester")
    assert get_clip(conn, clip_id)["status"] == "approved"

    clip_file.write_bytes(b"video-bytes-changed")
    assert sha256_file(clip_file) != digest
    from autoclip.db import set_clip_status

    set_clip_status(conn, clip_id, "pending")
    with pytest.raises(ReviewError):
        approve(conn, clip_id, "tester")
    assert get_clip(conn, clip_id)["status"] == "stale"

    html_path = write_review_html(settings, conn)
    assert html_path.exists()
    assert "Judul" in html_path.read_text(encoding="utf-8")
