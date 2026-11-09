"""Jadwalkan satu video TikTok dengan caption bebas (tanpa hashtag campaign).

Pakai: python data/_tt_schedule_manual.py <file.mp4> "<caption>" 2026-11-10T19:30
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip import tiktok
from autoclip.config import load_settings

ROOT = Path(__file__).resolve().parents[1]
video = Path(sys.argv[1]).resolve()
caption = sys.argv[2]
when = datetime.fromisoformat(sys.argv[3])

settings = load_settings(ROOT)
url = tiktok.publish_clip(settings, {"tiktok_path": str(video)}, caption, when)
print("terjadwal:", when.isoformat(), url)
