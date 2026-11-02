import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "out"


def scene_times(video, thr):
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video),
         "-filter:v", f"select='gt(scene,{thr})',showinfo", "-f", "null", "-"],
        capture_output=True, text=True, errors="ignore",
    )
    return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", p.stderr)]


def audio_rms(video, sr=8000):
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(video), "-vn", "-ac", "1",
         "-ar", str(sr), "-f", "s16le", "-"],
        capture_output=True,
    )
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float32) / 32768.0
    n = len(x) // sr
    if n == 0:
        return np.zeros(1, dtype=np.float32), sr
    return np.sqrt((x[: n * sr].reshape(n, sr) ** 2).mean(axis=1)), sr


def z(a):
    s = a.std()
    return (a - a.mean()) / s if s > 1e-9 else a * 0.0


def pick(video, count, length, scene_thr, step):
    print("[*] deteksi scene...", file=sys.stderr)
    cuts = np.array(scene_times(video, scene_thr))
    print(f"    {len(cuts)} cut", file=sys.stderr)
    print("[*] analisa audio...", file=sys.stderr)
    rms, sr = audio_rms(video)
    dur = len(rms)
    print(f"    durasi ~{dur}s", file=sys.stderr)

    L = int(length)
    cuts_sorted = np.sort(cuts)
    starts = np.arange(0, max(1, dur - L + 1), step)
    cut_rate = np.array([
        np.searchsorted(cuts_sorted, s + L) - np.searchsorted(cuts_sorted, s)
        for s in starts
    ], dtype=np.float32) / L
    energy = np.array([
        rms[int(s):int(s) + L].mean() if int(s) < dur else 0.0
        for s in starts
    ], dtype=np.float32)

    score = 0.6 * z(cut_rate) + 0.4 * z(energy)
    order = np.argsort(-score)

    chosen = []
    for i in order:
        s = int(starts[i])
        if any(abs(s - c) < length * 0.8 for c in chosen):
            continue
        chosen.append(s)
        if len(chosen) >= count:
            break

    chosen.sort()
    return [{"start": float(s), "end": float(s + length),
             "title": f"highlight_{n+1}"} for n, s in enumerate(chosen)]


def main():
    ap = argparse.ArgumentParser(description="Auto-highlight: scene + audio energy")
    ap.add_argument("video", type=Path)
    ap.add_argument("--count", type=int, default=5)
    ap.add_argument("--length", type=float, default=40)
    ap.add_argument("--step", type=float, default=5)
    ap.add_argument("--scene", type=float, default=0.4)
    ap.add_argument("--out", type=Path, default=Path("clips.json"))
    a = ap.parse_args()

    clips = pick(a.video, a.count, a.length, a.scene, a.step)
    a.out.write_text(json.dumps(clips, indent=2), encoding="utf-8")
    print(f"[+] {len(clips)} highlight -> {a.out}", file=sys.stderr)
    for c in clips:
        print(f"    {c['title']}: {c['start']:.0f}-{c['end']:.0f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
