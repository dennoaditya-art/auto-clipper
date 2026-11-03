from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi"}


class MediaError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int
    height: int
    has_audio: bool
    fps: float = 0.0


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


_FFMPEG_CACHE: str | None = None


def _runnable(path: str) -> bool:
    """Cek binary benar-benar bisa dieksekusi (Application Control bisa blokir shim)."""
    try:
        done = subprocess.run(
            [path, "-version"], capture_output=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def ffmpeg_bin() -> str:
    """Cari ffmpeg yang benar-benar bisa dijalankan.

    ponytail: shim chocolatey (C:\\ProgramData\\chocolatey\\bin) bisa diblokir
    Application Control walau binary aslinya tidak. Kalau butuh versi lain,
    set env AUTOCLIP_FFMPEG.
    """
    global _FFMPEG_CACHE
    if _FFMPEG_CACHE:
        return _FFMPEG_CACHE
    candidates: list[str] = []
    override = os.environ.get("AUTOCLIP_FFMPEG", "").strip()
    if override and Path(override).exists():
        candidates.append(override)
    found = shutil.which("ffmpeg")
    if found:
        candidates.append(found)
    candidates += [
        r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffmpeg.exe",
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"D:\ffmpeg\bin\ffmpeg.exe",
    ]
    seen: set[str] = set()
    for path in candidates:
        if path in seen or not Path(path).exists():
            continue
        seen.add(path)
        if _runnable(path):
            _FFMPEG_CACHE = path
            return path
    raise MediaError(
        "tidak ada ffmpeg yang bisa dijalankan (cek Application Control / set AUTOCLIP_FFMPEG)"
    )


def ffprobe_bin() -> str | None:
    override = os.environ.get("AUTOCLIP_FFPROBE", "").strip()
    if override and Path(override).exists() and _runnable(override):
        return override
    found = shutil.which("ffprobe")
    if found and _runnable(found):
        return found
    for path in (
        r"C:\ProgramData\chocolatey\lib\ffmpeg\tools\ffmpeg\bin\ffprobe.exe",
        r"C:\ffmpeg\bin\ffprobe.exe",
        r"D:\ffmpeg\bin\ffprobe.exe",
    ):
        if Path(path).exists() and _runnable(path):
            return path
    return None


def _parse_fps(value: str | None) -> float:
    try:
        num, _, den = str(value or "").partition("/")
        num, den = float(num), float(den or 1)
        return num / den if den > 0 else 0.0
    except ValueError:
        return 0.0


def probe(path: Path) -> VideoInfo:
    probe_bin = ffprobe_bin()
    if probe_bin:
        result = subprocess.run(
            [
                probe_bin,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0:
            data = json.loads(result.stdout or "{}")
            streams = data.get("streams", [])
            video = next((s for s in streams if s.get("codec_type") == "video"), None)
            if video is None:
                raise MediaError(f"tidak ada stream video: {path}")
            duration = float(data.get("format", {}).get("duration") or 0)
            if duration <= 0:
                duration = float(video.get("duration") or 0)
            return VideoInfo(
                duration=duration,
                width=int(video.get("width") or 0),
                height=int(video.get("height") or 0),
                has_audio=any(s.get("codec_type") == "audio" for s in streams),
                fps=_parse_fps(video.get("avg_frame_rate") or video.get("r_frame_rate")),
            )
    return _probe_with_ffmpeg(path)


def _probe_with_ffmpeg(path: Path) -> VideoInfo:
    result = subprocess.run(
        [ffmpeg_bin(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    text = result.stderr
    duration = 0.0
    width = 0
    height = 0
    has_audio = "Audio:" in text
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            raw = line.split("Duration:", 1)[1].split(",", 1)[0].strip()
            try:
                hours, minutes, seconds = raw.split(":")
                duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
            except ValueError:
                pass
        if "Video:" in line and "x" in line:
            for token in line.split(","):
                token = token.strip()
                if "x" in token:
                    left, _, right = token.partition("x")
                    if left.isdigit() and right[:4].isdigit():
                        width, height = int(left), int(right[:4])
                        break
    if duration <= 0 or width <= 0 or height <= 0:
        raise MediaError(f"gagal membaca metadata: {path}")
    return VideoInfo(duration=duration, width=width, height=height, has_audio=has_audio)


def format_timestamp(seconds: float) -> str:
    total = max(0.0, seconds)
    hours = int(total // 3600)
    minutes = int((total % 3600) // 60)
    secs = total % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
