from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import pytest

from autoclip.media import ffmpeg_bin

from autoclip.config import load_settings

SETTINGS_YAML = """
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
  language: id
  vad: true
selection:
  clips_per_video: 3
  min_duration_seconds: 20
  max_duration_seconds: 60
  min_score: 50
  chunk_seconds: 120
  provider: heuristic
  gemini_model: gemini-2.0-flash
  ollama_model: qwen2.5:3b
  ollama_url: http://127.0.0.1:11434
render:
  width: 1080
  height: 1920
  crf: 28
  preset: ultrafast
  encoder: libx264
  face_crop: false
  face_sample_fps: 1.0
  subtitles: true
  subtitle_max_chars: 32
  subtitle_style: "FontName=Arial,FontSize=8,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=0.7,Shadow=0,Alignment=2,MarginV=45"
  loudnorm: true
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

ACCOUNTS_YAML = """
accounts:
  - id: utama
    display_name: "Akun Utama"
    niche: bisnis
    enabled: true
    rights_approved: true
    approval_required: true
"""


@pytest.fixture
def settings(tmp_path: Path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "settings.yaml").write_text(
        textwrap.dedent(SETTINGS_YAML), encoding="utf-8"
    )
    (config / "accounts.yaml").write_text(
        textwrap.dedent(ACCOUNTS_YAML), encoding="utf-8"
    )
    return load_settings(tmp_path)


@pytest.fixture
def video(tmp_path: Path) -> Path:
    path = tmp_path / "sample.mp4"
    subprocess.run(
        [
            ffmpeg_bin(),
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x240:rate=25:duration=6",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=6",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
    )
    return path
