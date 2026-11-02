from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from .config import Settings

log = logging.getLogger(__name__)

_MODELS: dict[tuple[str, str], Any] = {}


class TranscriptionError(RuntimeError):
    pass


def transcript_path(settings: Settings, sha256: str) -> Path:
    return settings.paths.work / sha256[:2] / f"{sha256}.transcript.json"


def get_model(model_size: str, compute_type: str):
    key = (model_size, compute_type)
    if key not in _MODELS:
        from faster_whisper import WhisperModel

        threads = min(6, os.cpu_count() or 4)
        log.info("memuat model whisper=%s compute=%s threads=%s", model_size, compute_type, threads)
        _MODELS[key] = WhisperModel(
            model_size,
            device="cpu",
            compute_type=compute_type,
            cpu_threads=threads,
        )
    return _MODELS[key]


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp"
    ) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        temp_name = handle.name
    Path(temp_name).replace(path)


def ensure_transcript(
    settings: Settings, source: Any, force: bool = False
) -> dict[str, Any]:
    path = transcript_path(settings, source["sha256"])
    cfg = settings.transcription
    if path.exists() and not force:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("model") == cfg.model and data.get("segments"):
                return data
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("cache transkrip rusak, ulang: %s", exc)

    media_path = Path(source["path"])
    if not media_path.exists():
        raise TranscriptionError(f"file sumber hilang: {media_path}")

    model = get_model(cfg.model, cfg.compute_type)
    log.info("transkripsi #%s: %s", source["id"], media_path.name)
    segments_iter, info = model.transcribe(
        str(media_path),
        word_timestamps=True,
        language=cfg.language,
        vad_filter=cfg.vad,
        beam_size=5,
    )

    segments: list[dict[str, Any]] = []
    for index, segment in enumerate(segments_iter, 1):
        text = segment.text.strip()
        if not text:
            continue
        words = [
            {"w": word.word, "s": float(word.start), "e": float(word.end)}
            for word in (segment.words or [])
        ]
        segments.append(
            {
                "start": float(segment.start),
                "end": float(segment.end),
                "text": text,
                "words": words,
            }
        )
        if index % 25 == 0:
            log.info("  %s segmen...", index)

    if not segments:
        raise TranscriptionError("tidak ada ucapan yang terdeteksi")

    data = {
        "source_id": source["id"],
        "sha256": source["sha256"],
        "file": str(media_path),
        "model": cfg.model,
        "language": info.language,
        "duration": float(info.duration or source["duration"]),
        "segments": segments,
    }
    _write_atomic(path, data)
    log.info(
        "transkrip selesai: %s segmen, bahasa=%s, durasi=%.1fs",
        len(segments),
        info.language,
        data["duration"],
    )
    return data
