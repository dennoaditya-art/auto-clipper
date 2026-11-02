from __future__ import annotations

import json
import logging
from hashlib import sha256
from pathlib import Path
from typing import Any

from .select import _extract_json, _gemini_call

log = logging.getLogger(__name__)

BATCH = 40


class TranslateError(RuntimeError):
    pass


def _prompt(lines: list[str], target: str) -> str:
    numbered = json.dumps(lines, ensure_ascii=False, indent=0)
    return (
        f"Terjemahkan setiap baris teks berikut ke bahasa {target}. "
        "Pertahankan jumlah baris dan urutannya, jangan menambah atau menghapus. "
        "Nada santai seperti subtitle video media sosial, bukan terjemahan harfiah. "
        'Balas HANYA JSON: {"lines": ["terjemahan 1", "terjemahan 2", ...]}\n\n'
        f"{numbered}"
    )


def _translate_batch(lines: list[str], target: str, model: str, api_key: str) -> list[str]:
    data = _extract_json(_gemini_call(_prompt(lines, target), model, api_key))
    out = data.get("lines")
    if not isinstance(out, list):
        raise TranslateError("respons terjemahan tanpa 'lines'")
    if len(out) != len(lines):
        raise TranslateError(f"jumlah baris tidak cocok: {len(out)} != {len(lines)}")
    return [str(item).strip() for item in out]


def _translate_lines(lines: list[str], target: str, model: str, api_key: str) -> list[str]:
    try:
        return _translate_batch(lines, target, model, api_key)
    except (TranslateError, ValueError) as exc:
        if len(lines) <= 1:
            log.warning("terjemahan gagal (%s), pakai teks asli", exc)
            return list(lines)
        mid = len(lines) // 2
        log.warning("batch %s baris gagal (%s), dipecah", len(lines), exc)
        return _translate_lines(lines[:mid], target, model, api_key) + _translate_lines(
            lines[mid:], target, model, api_key
        )


def translate_texts(
    texts: list[str],
    target: str,
    model: str,
    api_key: str,
    cache_dir: Path,
) -> list[str]:
    if not texts:
        return []
    key = sha256(("\u0000".join(texts) + target + model).encode("utf-8")).hexdigest()[:20]
    cache = cache_dir / f"{key}.translation.json"
    if cache.exists():
        try:
            cached = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(cached, list) and len(cached) == len(texts):
                return [str(item) for item in cached]
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("cache terjemahan rusak, ulang: %s", exc)

    translated: list[str] = []
    for index in range(0, len(texts), BATCH):
        chunk = texts[index : index + BATCH]
        translated.extend(_translate_lines(chunk, target, model, api_key))
        log.info("terjemahan %s/%s baris", len(translated), len(texts))

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(translated, ensure_ascii=False), encoding="utf-8")
    return translated


def translate_segments(
    segments: list[dict[str, Any]],
    target: str,
    model: str,
    api_key: str,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    texts = [str(seg.get("text", "")).strip() for seg in segments]
    translated = translate_texts(texts, target, model, api_key, cache_dir)
    return [{**seg, "text": text} for seg, text in zip(segments, translated)]
