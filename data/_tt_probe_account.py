"""Terbitkan video uji (bukan repost) untuk memisahkan masalah akun vs konten.

Pakai: python data/_tt_account_test.py data\\browser\\tes_akun.mp4 "tes akun"
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autoclip import tiktok  # noqa: E402
from autoclip.config import load_settings  # noqa: E402

video = Path(sys.argv[1]).resolve()
caption = sys.argv[2]

settings = load_settings(ROOT)
url = tiktok.publish_clip(settings, {"tiktok_path": str(video)}, caption, None)
print("terbit:", url)
