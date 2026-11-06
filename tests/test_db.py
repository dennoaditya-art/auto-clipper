from __future__ import annotations

from autoclip.db import (
    add_clip,
    connect,
    create_source,
    get_clip,
    init_db,
    latest_review,
    record_review,
)


def make_clip(conn, source_id: int, start: float = 10.0):
    return add_clip(
        conn,
        source_id=source_id,
        account_id="utama",
        start=start,
        end=start + 30,
        file_path="clip.mp4",
        file_hash="abc",
        title="Judul",
        topic="bisnis",
        scores_json="{}",
        viral_score=80,
        niche_fit=90,
        final_score=83,
    )


def test_clip_stores_tiktok_path():
    conn = connect(":memory:")
    init_db(conn)
    source_id = create_source(conn, "a.mp4", "hash-a", 100)
    clip_id = add_clip(
        conn,
        source_id=source_id,
        account_id="utama",
        start=10.0,
        end=20.0,
        file_path="shorts.mp4",
        file_hash="abc",
        title="Judul",
        topic="roblox",
        scores_json="{}",
        viral_score=80,
        niche_fit=90,
        final_score=83,
        tiktok_path="tiktok.mp4",
    )
    assert get_clip(conn, clip_id)["tiktok_path"] == "tiktok.mp4"


def test_source_dedupe():
    conn = connect(":memory:")
    init_db(conn)
    first = create_source(conn, "a.mp4", "hash-a", 100)
    second = create_source(conn, "a.mp4", "hash-a", 100)
    assert first is not None
    assert second is None
    assert create_source(conn, "b.mp4", "hash-b", 100) is not None


def test_clip_upsert_and_review():
    conn = connect(":memory:")
    init_db(conn)
    source_id = create_source(conn, "a.mp4", "hash-a", 100)
    clip_id = make_clip(conn, source_id)
    assert get_clip(conn, clip_id)["status"] == "pending"
    record_review(conn, clip_id, "approved", "tester", "abc")
    assert get_clip(conn, clip_id)["status"] == "approved"
    assert latest_review(conn, clip_id)["decision"] == "approved"

    again = make_clip(conn, source_id)
    assert again == clip_id
    assert get_clip(conn, clip_id)["status"] == "pending"
