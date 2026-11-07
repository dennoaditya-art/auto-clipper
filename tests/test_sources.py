from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from autoclip import sources
from autoclip.config import ConfigError, load_settings

SOURCE_YAML = """
sources:
  - id: demo
    url: "https://www.youtube.com/@demo/videos"
    account: utama
    enabled: true
    rights_approved: true
    rights_reference: "video milik sendiri"
    latest: 2
"""


RISK_YAML = """
sources:
  - id: demo
    url: "https://www.youtube.com/@demo/videos"
    account: utama
    enabled: true
    rights_approved: false
    rights_risk_accepted: true
    rights_reference: "izin belum ada; risiko ditanggung"
    latest: 1
"""


def _write_source(root: Path, yaml: str) -> None:
    (root / "config" / "sources.yaml").write_text(yaml, encoding="utf-8")


def test_sync_skips_unapproved(settings, monkeypatch):
    _write_source(
        settings.root,
        SOURCE_YAML.replace("rights_approved: true", "rights_approved: false").replace(
            'rights_reference: "video milik sendiri"',
            'rights_reference: ""',
        ),
    )
    loaded = load_settings(settings.root)
    called = []
    monkeypatch.setattr(sources, "_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr(sources, "_verify_download", lambda path: path)
    monkeypatch.setattr(
        sources.subprocess,
        "run",
        lambda *a, **kw: called.append(a) or SimpleNamespace(returncode=0),
    )
    result = sources.sync_sources(loaded)
    assert result == {"downloaded": [], "errors": []}
    assert called == []


def test_sync_downloads_risk_accepted(settings, monkeypatch):
    _write_source(settings.root, RISK_YAML)
    loaded = load_settings(settings.root)
    called = []

    def fake_run(command, **kwargs):
        called.append(command)
        (loaded.paths.incoming / "demo-abc.mp4").write_bytes(b"video")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(sources, "_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr(sources, "_verify_download", lambda path: path)
    monkeypatch.setattr(sources.subprocess, "run", fake_run)
    result = sources.sync_sources(loaded)
    assert result["downloaded"] == ["demo-abc.mp4"]
    assert called


def test_sync_downloads_and_marks_ready(settings, monkeypatch):
    _write_source(settings.root, SOURCE_YAML)
    loaded = load_settings(settings.root)
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        (loaded.paths.incoming / "demo-abc.mp4").write_bytes(b"video")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(sources, "_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr(sources, "_verify_download", lambda path: path)
    monkeypatch.setattr(sources.subprocess, "run", fake_run)
    result = sources.sync_sources(loaded)
    assert result["errors"] == []
    assert result["downloaded"] == ["demo-abc.mp4"]
    assert commands[0][-2:] == ["--", "https://www.youtube.com/@demo/videos"]
    assert "--playlist-end" in commands[0]
    assert commands[0][commands[0].index("--playlist-end") + 1] == "2"
    path = loaded.paths.incoming / "demo-abc.mp4"
    assert path.stat().st_mtime < path.stat().st_ctime


def test_sync_reports_failure(settings, monkeypatch):
    _write_source(settings.root, SOURCE_YAML)
    loaded = load_settings(settings.root)
    monkeypatch.setattr(sources, "_ytdlp", lambda: "yt-dlp")
    monkeypatch.setattr(sources, "_verify_download", lambda path: path)
    monkeypatch.setattr(
        sources.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=1, stderr="boom", stdout=""),
    )
    result = sources.sync_sources(loaded)
    assert result["downloaded"] == []
    assert "demo: boom" in result["errors"][0]


def test_popular_recent_picks_most_viewed_new_video(settings, monkeypatch):
    _write_source(
        settings.root,
        SOURCE_YAML.replace("latest: 2", "latest: 1\n    popular_recent: true"),
    )
    loaded = load_settings(settings.root)
    (loaded.root / "data").mkdir(parents=True, exist_ok=True)
    (loaded.root / "data" / "ytdlp-archive.txt").write_text(
        "youtube sudah_pernah\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        sources,
        "popular_videos",
        lambda *a, **kw: [
            {"id": "baru_a", "views": 100, "title": "", "duration": 600},
            {"id": "baru_b", "views": 900, "title": "", "duration": 600},
            {"id": "sudah_pernah", "views": 5000, "title": "", "duration": 600},
            {"id": "kepanjangan", "views": 9000, "title": "", "duration": 7200},
        ],
    )
    picked = []

    def fake_download(settings, source_id, url, latest):
        picked.append(url)
        (loaded.paths.incoming / f"{source_id}-ok.mp4").write_bytes(b"video")

    monkeypatch.setattr(sources, "_download", fake_download)
    monkeypatch.setattr(sources, "_verify_download", lambda path: path)
    result = sources.sync_sources(loaded)
    assert result["errors"] == []
    assert picked == ["https://www.youtube.com/watch?v=baru_b"]


def test_source_url_must_be_youtube(settings):
    _write_source(
        settings.root,
        SOURCE_YAML.replace(
            "https://www.youtube.com/@demo/videos", "https://example.com/@demo"
        ),
    )
    with pytest.raises(ConfigError):
        load_settings(settings.root)


def test_source_requires_rights_reference(settings):
    _write_source(
        settings.root,
        SOURCE_YAML.replace(
            'rights_reference: "video milik sendiri"', 'rights_reference: ""'
        ),
    )
    with pytest.raises(ConfigError):
        load_settings(settings.root)


def test_risk_accepted_requires_reference(settings):
    _write_source(
        settings.root,
        RISK_YAML.replace(
            'rights_reference: "izin belum ada; risiko ditanggung"',
            'rights_reference: ""',
        ),
    )
    with pytest.raises(ConfigError):
        load_settings(settings.root)

