"""Cek kerapatan bicara tiap klip baru (gap > 3 dtk)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autoclip.config import load_settings
from autoclip.transcribe import transcript_path

SHA = "c7d365bc57741ccb7ba2a56e301a89819a5c7f6f6595fb9755d18692e5323785"
s = load_settings(Path(r"D:\clipper"))
segs = json.loads(transcript_path(s, SHA).read_text(encoding="utf-8"))["segments"]

for label, a, b in (("84", 3489.3, 3534.3), ("85", 2396.4, 2441.4), ("86", 2339.7, 2382.9)):
    print("=== clip", label)
    prev = a
    speech = 0.0
    for seg in segs:
        if seg["end"] > a and seg["start"] < b:
            gap = seg["start"] - prev
            if gap > 3:
                print(f"   GAP {gap:.1f}s  ({prev:.1f} -> {seg['start']:.1f})")
            print("  ", round(seg["start"], 1), round(seg["end"], 1), seg["text"][:70])
            speech += min(seg["end"], b) - max(seg["start"], a)
            prev = max(prev, seg["end"])
    print(f"   bicara {speech:.0f}s / {b - a:.0f}s, akhir {prev:.1f}, sisa {b - prev:.1f}s")
