from __future__ import annotations

import hashlib
import textwrap

import pytest

from autoclip import pipeline
from autoclip.config import load_settings
from autoclip.db import clips_for_source, connect, create_source, get_source, init_db
from autoclip.pipeline import AlreadyRunning, RunLock, account_for_source, process_source
from autoclip.render import RenderedClip
from autoclip.select import Candidate


def test_lock_prevents_double_run(tmp_path):
    path = tmp_path / "run.lock"
    with RunLock(path):
        with pytest.raises(AlreadyRunning):
            with RunLock(path):
                pass
    with RunLock(path):
        pass


def test_process_source_flow(settings, video, monkeypatch):
    conn = connect(settings.paths.database)
    init_db(conn)
    source_id = create_source(conn, str(video), "hash-pipeline", 6.0)
    assert source_id is not None
    source = get_source(conn, source_id)
    account = settings.accounts[0]

    monkeypatch.setattr(
        pipeline,
        "ensure_transcript",
        lambda settings, source, force=False: {
            "duration": 6.0,
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "Ini rahasia bisnis."},
                {"start": 2.0, "end": 5.0, "text": "Jadi solusinya begini."},
            ],
        },
    )
    monkeypatch.setattr(
        pipeline,
        "select_clips",
        lambda transcript, settings, account, heatmap_markers=None: [
            Candidate(
                start=0.0,
                end=4.0,
                scores={
                    "hook": 80,
                    "payoff": 80,
                    "retention": 80,
                    "emotion": 70,
                    "clarity": 80,
                    "av": 65,
                },
                niche_fit=85,
                topic="bisnis",
                title="Rahasia bisnis",
                caption="",
            )
        ],
    )

    def fake_render(
        video, info, start, end, title, settings, transcript, output_dir, source_id, **kwargs
    ):
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / "fake.mp4"
        path.write_bytes(b"fake-video")
        return RenderedClip(path=path, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    monkeypatch.setattr(pipeline, "render_clip", fake_render)
    clip_ids = process_source(settings, conn, source, account, force=True)
    assert len(clip_ids) == 1
    assert get_source(conn, source_id)["status"] == "processed"
    clips = clips_for_source(conn, source_id)
    assert clips[0]["title"] == "Rahasia bisnis"
    assert clips[0]["status"] == "pending"
    conn.close()



def test_process_source_renders_tiktok_variant(settings, video, monkeypatch):
    from dataclasses import replace

    conn = connect(settings.paths.database)
    init_db(conn)
    source_id = create_source(conn, str(video), "hash-dual", 6.0)
    source = get_source(conn, source_id)
    account = replace(settings.accounts[0], tiktok_enabled=True)
    settings = replace(settings, accounts=(account,))

    monkeypatch.setattr(
        pipeline,
        "ensure_transcript",
        lambda settings, source, force=False: {
            "duration": 6.0,
            "segments": [{"start": 0.0, "end": 5.0, "text": "Opah nya seram."}],
        },
    )
    monkeypatch.setattr(
        pipeline,
        "select_clips",
        lambda transcript, settings, account, heatmap_markers=None: [
            Candidate(
                start=0.0, end=4.0,
                scores={"hook": 80, "payoff": 80, "retention": 80,
                        "emotion": 70, "clarity": 80, "av": 65},
                niche_fit=85, topic="roblox", title="Opah seram", caption="",
            )
        ],
    )

    profiles: list[str] = []

    def fake_render(video, info, start, end, title, settings, transcript,
                    output_dir, source_id, **kwargs):
        profile = kwargs.get("profile", "shorts")
        profiles.append(profile)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{profile}.mp4"
        path.write_bytes(b"fake")
        return RenderedClip(path=path, sha256=hashlib.sha256(b"fake").hexdigest())

    monkeypatch.setattr(pipeline, "render_clip", fake_render)
    clip_ids = process_source(settings, conn, source, account, force=True)
    assert profiles == ["shorts", "tiktok"]
    clip = clips_for_source(conn, source_id)[0]
    assert str(clip["tiktok_path"]).endswith("tiktok.mp4")
    assert len(clip_ids) == 1
    conn.close()


def test_account_for_source_maps_prefix(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text(
        textwrap.dedent(
            """
            app:
              name: auto-clipper
            paths:
              incoming: storage/incoming
              work: storage/work
              review: storage/review
              published: storage/published
              database: data/autoclip.db
              logs: logs
            transcription:
              model: tiny
              compute_type: int8
              vad: true
            selection:
              clips_per_video: 3
              min_duration_seconds: 20
              max_duration_seconds: 60
              min_score: 50
              chunk_seconds: 120
              provider: heuristic
            render:
              width: 1080
              height: 1920
              crf: 28
              preset: ultrafast
              encoder: libx264
            rights:
              status: approved
              reference: "test"
            safety:
              max_sources_per_run: 1
              max_clips_per_source: 3
              require_rights_approved: true
              min_source_age_seconds: 0
              retain_work_days: 14
            """
        ),
        encoding="utf-8",
    )
    (config / "accounts.yaml").write_text(
        textwrap.dedent(
            """
            accounts:
              - id: utama
                display_name: "Utama"
                niche: umum
                enabled: true
                rights_approved: true
              - id: kedua
                display_name: "Kedua"
                niche: umum
                enabled: true
                rights_approved: true
            """
        ),
        encoding="utf-8",
    )
    (config / "sources.yaml").write_text(
        textwrap.dedent(
            """
            sources:
              - id: jkt48
                url: "https://www.youtube.com/@JKT48TV/videos"
                account: utama
                enabled: true
                rights_risk_accepted: true
                rights_reference: "test"
              - id: channeldua
                url: "https://www.youtube.com/@ChannelDua/videos"
                account: kedua
                enabled: true
                rights_risk_accepted: true
                rights_reference: "test"
            """
        ),
        encoding="utf-8",
    )
    settings = load_settings(tmp_path)
    assert account_for_source(settings, {"path": "jkt48-abc.mp4"}).id == "utama"
    assert account_for_source(settings, {"path": "channeldua-xyz.mp4"}).id == "kedua"
    # prefix tak dikenal -> akun default pertama
    assert account_for_source(settings, {"path": "lain-1.mp4"}).id == "utama"
