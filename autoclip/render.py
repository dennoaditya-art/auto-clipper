from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import median

from .config import RenderConfig, Settings
from .media import MediaError, VideoInfo, ffmpeg_bin, sha256_file
from .subtitles import clip_karaoke_ass, clip_srt, hook_ass

log = logging.getLogger(__name__)

_QSV_SUPPORT: bool | None = None
_ROOT = Path(__file__).resolve().parents[1]
_FACE_MODEL = _ROOT / "models" / "face_detection_yunet_2023mar.onnx"
_FACE_MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)


@dataclass(frozen=True)
class RenderedClip:
    path: Path
    sha256: str


def _has_qsv() -> bool:
    global _QSV_SUPPORT
    if _QSV_SUPPORT is None:
        try:
            result = subprocess.run(
                [ffmpeg_bin(), "-hide_banner", "-encoders"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            _QSV_SUPPORT = "h264_qsv" in result.stdout
        except (OSError, MediaError):
            _QSV_SUPPORT = False
    return bool(_QSV_SUPPORT)


def _face_model() -> Path | None:
    if _FACE_MODEL.exists() and _FACE_MODEL.stat().st_size > 100_000:
        return _FACE_MODEL
    try:
        _FACE_MODEL.parent.mkdir(parents=True, exist_ok=True)
        temp = _FACE_MODEL.with_suffix(".tmp")
        log.info("unduh model deteksi wajah...")
        urllib.request.urlretrieve(_FACE_MODEL_URL, temp)
        if temp.stat().st_size < 100_000:
            raise OSError("file model terlalu kecil")
        temp.replace(_FACE_MODEL)
        return _FACE_MODEL
    except (OSError, urllib.error.URLError) as exc:
        log.warning("model wajah tidak tersedia (%s); crop tengah", exc)
        return None


def face_center_ratio(
    video: Path, start: float, end: float, sample_fps: float
) -> float | None:
    try:
        import cv2
    except ImportError:
        log.info("opencv tidak tersedia; crop tengah")
        return None
    if not hasattr(cv2, "FaceDetectorYN"):
        log.info("FaceDetectorYN tidak tersedia; crop tengah")
        return None
    model = _face_model()
    if model is None:
        return None
    detector = cv2.FaceDetectorYN.create(str(model), "", (320, 320), 0.9, 0.3, 5000)
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        return None
    capture.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    step = 1.0 / max(0.1, sample_fps)
    next_sample = start
    centers: list[float] = []
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if timestamp > end:
                break
            if timestamp + 0.001 < next_sample:
                continue
            next_sample = timestamp + step
            height, width = frame.shape[:2]
            detector.setInputSize((width, height))
            _, faces = detector.detect(frame)
            if faces is not None and len(faces):
                x, _, w, h = max(
                    faces, key=lambda f: float(f[2]) * float(f[3])
                )[:4]
                center = (float(x) + float(w) / 2) / max(1, width)
                if 0.15 <= center <= 0.85:
                    centers.append(center)
            if len(centers) >= 120:
                break
    finally:
        capture.release()
    if not centers:
        return None
    return float(median(centers))


def _crop_filter(
    info: VideoInfo, render: RenderConfig, face_ratio: float | None
) -> str:
    target_ratio = render.width / render.height
    src_ratio = info.width / max(1, info.height)
    if src_ratio > target_ratio:
        crop_h = float(info.height)
        crop_w = crop_h * target_ratio
    else:
        crop_w = float(info.width)
        crop_h = crop_w / target_ratio
    crop_w = min(crop_w, float(info.width))
    crop_h = min(crop_h, float(info.height))
    x = (info.width - crop_w) / 2
    y = (info.height - crop_h) / 2
    if face_ratio is not None:
        x = face_ratio * info.width - crop_w / 2
    x = max(0.0, min(float(info.width) - crop_w, x))
    y = max(0.0, min(float(info.height) - crop_h, y))
    return (
        f"crop={crop_w:.0f}:{crop_h:.0f}:{x:.0f}:{y:.0f},"
        f"scale={render.width}:{render.height}:flags=lanczos,setsar=1"
    )


def _slug(title: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title).strip()
    safe = "_".join(safe.split())[:40]
    return safe or "clip"


_EMOJI = [
    (("lucu", "ngakak", "ketawa", "komed", "funny", "kocak", "gelak", "canda"), "😂"),
    (("gila", "parah", "shock", "kaget", "aneh", "misteri", "horor", "serem", "menyeram"), "😱"),
    (("keren", "hebat", "luar biasa", "menakjub", "epic", "wow", "juara"), "🔥"),
    (("cinta", "sayang", "romantis", "love", "bucin"), "💖"),
    (("sedih", "nangis", "haru", "galau"), "😭"),
    (("masak", "makan", "resep", "kuliner"), "🍽️"),
    (("jkt48", "idol", "dance", "kpop", "jkt"), "✨"),
]


def _emoji_for(text: str) -> str:
    low = text.lower()
    for keys, emoji in _EMOJI:
        if any(key in low for key in keys):
            return emoji
    return "🔥"


def _zoom_filter(info: VideoInfo, render: RenderConfig) -> str:
    fps = int(round(info.fps)) if info.fps and info.fps > 0 else 30
    return (
        f"zoompan=z='min(zoom+0.0025,1.14)':x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':d=1:s={render.width}x{render.height}:fps={fps}"
    )


def _encode_command(
    video: Path,
    output: Path,
    start: float,
    end: float,
    filters: list[str],
    render: RenderConfig,
    has_audio: bool,
    encoder: str,
    watermark_image: Path | None = None,
) -> list[str]:
    command = [
        ffmpeg_bin(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(video),
    ]
    if watermark_image is not None:
        command += ["-i", str(watermark_image)]
    if watermark_image is None:
        command += ["-map", "0:v:0"]
        if has_audio:
            command += ["-map", "0:a:0"]
        command += ["-vf", ",".join(filters)]
    else:
        chain = ",".join(filters)
        graph = f"[0:v]{chain}[bg];[bg][1:v]overlay=0:0[vout]"
        command += ["-filter_complex", graph, "-map", "[vout]"]
        if has_audio:
            command += ["-map", "0:a:0"]
    if has_audio and render.loudnorm:
        command += ["-af", "loudnorm=I=-14:TP=-1.5:LRA=11"]
    if encoder == "qsv":
        command += ["-c:v", "h264_qsv", "-global_quality", "23", "-preset", "veryfast"]
    else:
        command += [
            "-c:v",
            "libx264",
            "-preset",
            render.preset,
            "-crf",
            str(render.crf),
        ]
    command += ["-pix_fmt", "yuv420p"]
    if has_audio:
        command += ["-c:a", "aac", "-b:a", "160k"]
    command += ["-movflags", "+faststart", str(output)]
    return command


def make_thumbnail(video: Path, at: float = 1.0) -> Path | None:
    target = video.with_suffix(".jpg")
    command = [
        ffmpeg_bin(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{at:.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(target),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        log.warning("thumbnail gagal: %s", exc)
        return None
    if not target.exists() or target.stat().st_size == 0:
        return None
    return target


def render_clip(
    video: Path,
    info: VideoInfo,
    start: float,
    end: float,
    title: str,
    settings: Settings,
    transcript: dict,
    output_dir: Path,
    source_id: int,
    watermark: str = "",
    watermark_image: Path | None = None,
    longform: bool = False,
) -> RenderedClip:
    render = settings.render
    if longform:
        # 16:9 penuh, tanpa crop vertikal; karaoke dimatikan (dibaca ulang di bawah)
        render = replace(
            render, width=1920, height=1080, face_crop=False, zoom_punch=False
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = "".join(c if c.isalnum() or c in "-_" else "_" for c in title)[:48]
    output = output_dir / f"s{source_id:03d}_{int(start):05d}_{_slug(suffix)}.mp4"
    temp_dir = Path(tempfile.mkdtemp(prefix="autoclip_"))
    try:
        filters = []
        face_ratio = None
        if longform:
            # ponytail: longform = 16:9 utuh tanpa crop/zoom, subtitle biasa.
            # Kalau butuh framing vertikal juga, pakai mode pendek.
            filters.append(
                "scale=1920:1080:force_original_aspect_ratio=decrease,"
                "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1"
            )
        else:
            if render.face_crop:
                face_ratio = face_center_ratio(
                    video, start, end, render.face_sample_fps
                )
                if face_ratio is not None:
                    log.info("wajah terdeteksi di x=%.2f", face_ratio)
            filters.append(_crop_filter(info, render, face_ratio))
            if render.zoom_punch:
                filters.append(_zoom_filter(info, render))

        hook_title = "" if longform else (title if render.hook_overlay else "")
        if render.emoji_hook and hook_title:
            hook_title = f"{_emoji_for(hook_title)} {hook_title}"
        if (render.hook_seconds > 0 and not longform) or watermark:
            if hook_ass(
                hook_title,
                render.hook_seconds if not longform else 0.0,
                temp_dir / "hook.ass",
                render.width,
                render.height,
                watermark=watermark,
            ):
                filters.append("ass=hook.ass")

        if render.subtitles:
            karaoke = 0
            if not longform:
                karaoke = clip_karaoke_ass(
                    transcript,
                    start,
                    end,
                    temp_dir / "sub.ass",
                    render.width,
                    render.height,
                    margin_v=int(render.height * 0.26) if watermark_image else 0,
                )
            if not karaoke:
                count = clip_srt(
                    transcript,
                    start,
                    end,
                    temp_dir / "sub.srt",
                    max_chars=render.subtitle_max_chars,
                )
                if count:
                    filters.append(
                        f"subtitles=sub.srt:force_style='{render.subtitle_style}'"
                    )

        encoders = (
            ["qsv", "libx264"] if render.encoder == "auto" else [render.encoder]
        )
        last_error: Exception | None = None
        for index, encoder in enumerate(encoders):
            command = _encode_command(
                video,
                output,
                start,
                end,
                filters,
                render,
                info.has_audio,
                encoder,
                watermark_image=watermark_image,
            )
            try:
                subprocess.run(
                    command, cwd=str(temp_dir), check=True, capture_output=True
                )
                if encoder == "qsv":
                    log.info("render pakai QuickSync")
                last_error = None
                break
            except subprocess.CalledProcessError as exc:
                stderr = (exc.stderr or b"").decode("utf-8", "replace")[-500:]
                last_error = exc
                if index + 1 < len(encoders):
                    log.warning("encoder %s gagal, fallback: %s", encoder, stderr)
        if last_error is not None:
            raise last_error
        if not output.exists() or output.stat().st_size == 0:
            raise MediaError(f"file hasil render kosong: {output}")
        if settings.upload.thumbnail:
            make_thumbnail(output)
        return RenderedClip(path=output, sha256=sha256_file(output))
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)