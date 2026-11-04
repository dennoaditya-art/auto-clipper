from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

import httpx

from .config import Account, SelectionConfig, Settings

log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

WEIGHTS = {
    "hook": 0.25,
    "payoff": 0.20,
    "retention": 0.20,
    "emotion": 0.15,
    "clarity": 0.10,
    "av": 0.10,
}

HOOK_WORDS = {
    "rahasia", "kesalahan", "jangan", "wajib", "ternyata", "kenapa", "bagaimana",
    "cara", "tips", "trik", "paling", "terbaik", "terburuk", "gagal", "sukses",
    "bahaya", "penting", "stop", "mulai", "bayangkan", "kebanyakan orang",
    "tidak banyak orang", "sebenarnya", "faktanya", "mistake", "secret", "never",
    "why", "how", "best", "worst", "warning", "important", "imagine", "most people",
    "truth", "actually", "really", "nobody",
}
PAYOFF_WORDS = {
    "jadi", "makanya", "hasilnya", "intinya", "kuncinya", "akhirnya",
    "kesimpulannya", "solusinya", "rahasianya", "ternyata", "karena itu",
    "oleh sebab itu", "pesannya", "pelajarannya", "result", "therefore", "the point",
    "the key", "in the end", "conclusion", "solution", "that's why", "lesson",
}
EMOTION_WORDS = {
    "mengejutkan", "kaget", "marah", "sedih", "bangga", "takut", "cinta",
    "benci", "luar biasa", "gila", "parah", "hebat", "keren", "inspirasi",
    "motivasi", "dramatis", "memalukan", "menggila", "surprising", "shocking",
    "angry", "sad", "proud", "afraid", "love", "hate", "amazing", "crazy",
    "terrible", "great", "awesome", "inspiring",
}
FILLER_WORDS = {
    "eee", "emm", "hmm", "apa ya", "gitu", "gitu ya", "oke", "okay", "um", "uh",
    "you know",
}

NICHE_WORDS: dict[str, set[str]] = {
    "bisnis": {
        "bisnis", "usaha", "modal", "untung", "rugi", "strategi", "pelanggan",
        "jualan", "marketing", "omzet", "profit", "karyawan", "manajemen", "brand",
        "business", "customer", "sales", "price", "startup", "revenue",
    },
    "motivasi": {
        "mimpi", "gagal", "bangkit", "disiplin", "konsisten", "hidup", "tujuan",
        "kebiasaan", "mental", "sukses", "perjuangan", "berubah", "dream", "discipline",
        "habit", "growth",
    },
    "teknologi": {
        "ai", "teknologi", "aplikasi", "gadget", "komputer", "software", "coding",
        "internet", "data", "robot", "iphone", "android", "laptop", "chip", "technology",
        "computer", "app",
    },
    "edukasi": {
        "belajar", "penjelasan", "contoh", "definisi", "cara", "langkah", "materi",
        "ilmu", "pengetahuan", "sekolah", "kuliah", "guru",
    },
    "finansial": {
        "uang", "keuangan", "investasi", "tabungan", "hutang", "utang", "budget",
        "anggaran", "saham", "reksadana", "bunga", "gaji", "pengeluaran",
    },
    "kesehatan": {
        "sehat", "kesehatan", "olahraga", "tidur", "makan", "gizi", "diet",
        "dokter", "sakit", "tubuh", "vitamin", "stres",
    },
    "hiburan": {
        "lucu", "humor", "lawak", "seru", "menarik", "cerita", "viral", "ngakak",
    },
}


@dataclass
class Candidate:
    start: float
    end: float
    scores: dict[str, float]
    topic: str
    title: str
    caption: str
    reason: str = ""
    provider: str = "heuristic"
    niche_fit: float = 70.0

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    @property
    def viral_score(self) -> float:
        return round(
            sum(self.scores.get(key, 50.0) * weight for key, weight in WEIGHTS.items()),
            2,
        )

    def final_score(self, niche_weight: float = 0.35) -> float:
        return round(
            self.viral_score * (1 - niche_weight) + self.niche_fit * niche_weight, 2
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.start,
            "end": self.end,
            "scores": self.scores,
            "viral_score": self.viral_score,
            "niche_fit": self.niche_fit,
            "final_score": self.final_score(),
            "topic": self.topic,
            "title": self.title,
            "caption": self.caption,
            "reason": self.reason,
            "provider": self.provider,
        }


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _count_terms(text: str, terms: Iterable[str]) -> int:
    count = 0
    for term in terms:
        if len(term) <= 4 and " " not in term:
            count += 1 if re.search(rf"\b{re.escape(term)}\b", text) else 0
        else:
            count += 1 if term in text else 0
    return count


def _nearest_topic(text: str, niche: str) -> float:
    if niche in {"", "umum", "general", "all"}:
        return 70.0
    words = NICHE_WORDS.get(niche, set())
    if not words:
        return 70.0
    hits = _count_terms(text, words)
    return _clamp(50.0 + hits * 8.0, 40.0, 95.0)


def _guess_topic(text: str) -> str:
    best = ("umum", 0)
    for niche, words in NICHE_WORDS.items():
        hits = _count_terms(text, words)
        if hits > best[1]:
            best = (niche, hits)
    return best[0]


def _segments_between(segments: list[dict], start: float, end: float) -> list[dict]:
    return [s for s in segments if s["end"] > start and s["start"] < end]


def _window_text(segments: list[dict], start: float, end: float) -> str:
    return " ".join(
        s["text"].strip() for s in _segments_between(segments, start, end)
    ).strip()


_SENTENCE_END = re.compile(r"[.!?…]\s*$")


def _word_times(segments: list[dict]) -> list[tuple[float, float, str]]:
    """Daftar (start, end, word) dari seluruh segmen, kalau tersedia."""
    out: list[tuple[float, float, str]] = []
    for segment in segments:
        for word in segment.get("words") or []:
            text = str(word.get("w", "")).strip()
            if not text:
                continue
            out.append(
                (
                    float(word.get("s", segment["start"])),
                    float(word.get("e", segment["end"])),
                    text,
                )
            )
    return out


def snap_to_speech(
    segments: list[dict],
    start: float,
    end: float,
    *,
    lead_in: float = 0.25,
    lead_out: float = 0.35,
) -> tuple[float, float]:
    """Rapatkan batas klip ke ucapan nyata.

    Memperbaiki tiga cacat yang terbukti menurunkan retensi:
    klip dimulai sebelum ada yang bicara, kalimat terpotong di ujung,
    dan potongan mentok batas durasi minimum.
    """
    words = _word_times(segments)
    if not words:
        inside = _segments_between(segments, start, end)
        if inside:
            first = max(start, float(inside[0]["start"]) - lead_in)
            last = min(end, float(inside[-1]["end"]) + lead_out)
            return round(max(0.0, first), 2), round(last, 2)
        return round(start, 2), round(end, 2)

    inside = [w for w in words if w[1] > start and w[0] < end]
    if not inside:
        return round(start, 2), round(end, 2)

    first_start = inside[0][0]
    last_end = inside[-1][1]
    # buang jendela mati sebelum kata pertama (hanya sisakan lead_in kecil)
    new_start = max(0.0, first_start - lead_in)

    # kalau kata terakhir masih jauh dari batas, ikuti kalimat sampai titik
    new_end = max(last_end, min(end, last_end)) + lead_out
    if _SENTENCE_END.search(inside[-1][2]):
        new_end = last_end + 0.12
    else:
        # tarik ke depan selama kalimat belum selesai dan belum lewat batas
        for word in words:
            if word[0] < last_end:
                continue
            if word[0] - last_end > 0.8:
                break
            new_end = word[1] + 0.12
            if _SENTENCE_END.search(word[2]):
                break

    return round(new_start, 2), round(min(new_end, end + 1.5), 2)


def _heuristic_scores(
    segments: list[dict], start: float, end: float, account_niche: str
) -> dict[str, float]:
    window = _segments_between(segments, start, end)
    text = " ".join(s["text"] for s in window).strip()
    low = _norm(text)
    duration = max(0.1, end - start)
    words = re.findall(r"\w+", low)
    first = _norm(
        " ".join(
            s["text"] for s in window if s["start"] < start + 3.5
        )
    )
    tail = _norm(
        " ".join(
            s["text"] for s in window if s["end"] > end - max(5.0, duration * 0.35)
        )
    )
    density = len(low) / duration
    gaps = 0.0
    for prev, cur in zip(window, window[1:]):
        gaps += max(0.0, cur["start"] - prev["end"])
    fillers = _count_terms(low, FILLER_WORDS)

    hook = 38.0
    hook += min(30.0, _count_terms(first, HOOK_WORDS) * 8.0)
    hook += 10.0 if "?" in first else 0.0
    hook += 7.0 if re.search(r"\d", first) else 0.0
    hook += 5.0 if len(first.split()) <= 18 else -5.0

    payoff = 42.0 + min(32.0, _count_terms(tail, PAYOFF_WORDS) * 9.0)
    payoff += 8.0 if re.search(r"[.!?]", tail[-80:]) else 0.0

    retention = 45.0 + min(35.0, density * 1.6)
    retention -= min(25.0, gaps * 4.0)
    retention -= min(15.0, fillers * 5.0)
    retention += 5.0 if len(window) >= 3 else 0.0

    emotion = 38.0 + min(30.0, _count_terms(low, EMOTION_WORDS) * 8.0)
    emotion += min(12.0, low.count("!") * 5.0)
    emotion += 4.0 if re.search(r"\b(aku|saya|kamu|kita)\b", low) else 0.0

    avg_words = len(words) / max(1, len(window))
    clarity = 55.0
    clarity += 10.0 if 8 <= avg_words <= 28 else -8.0
    clarity -= min(20.0, fillers * 6.0)
    clarity += 5.0 if len(window) <= 8 else -5.0

    av = 65.0
    niche_fit = _nearest_topic(low, account_niche)

    return {
        "hook": round(_clamp(hook), 1),
        "payoff": round(_clamp(payoff), 1),
        "retention": round(_clamp(retention), 1),
        "emotion": round(_clamp(emotion), 1),
        "clarity": round(_clamp(clarity), 1),
        "av": round(_clamp(av), 1),
        "niche_fit": round(niche_fit, 1),
    }


def _title_from_text(text: str) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return "Momen menarik"
    sentence = re.split(r"(?<=[.!?])\s+", clean)[0]
    if len(sentence) > 80:
        sentence = sentence[:77].rstrip() + "..."
    return sentence[0].upper() + sentence[1:] if sentence else "Momen menarik"


def _opening_quote(
    segments: list[dict], start: float, end: float, seconds: float = 3.5
) -> str:
    """Kutipan apa yang benar-benar diucapkan di awal klip.

    Judul yang menjanjikan hal lain dari ucapan 3 detik pertama membuat
    penonton langsung swipe; kutipan asli selalu cocok dengan audio.
    """
    words = _word_times(segments)
    if words:
        opening = [w[2] for w in words if w[1] > start and w[0] < start + seconds]
        quote = " ".join(opening).strip()
    else:
        quote = _window_text(segments, start, min(end, start + seconds))
    quote = re.sub(r"\s+", " ", quote).strip(" ,.-")
    if not quote:
        return ""
    # buang kata pengisi pembuka yang tidak berbobot di judul
    quote = re.sub(
        r"^(?:guys|jadi|nah|eh|jadi ya|ok|oke|hmm|eee)\s+", "", quote, flags=re.I
    )
    # transkrip Whisper jarang memberi tanda baca: potong di batas kata utuh,
    # jangan sisakan kata terpotong seperti "rasia"
    words = quote.split()
    while words and len(" ".join(words)) > 62:
        words.pop()
    quote = " ".join(words).rstrip(" ,.-")
    if len(words) < 3:
        return ""
    return quote[:1].upper() + quote[1:]


def heuristic_candidates(
    segments: list[dict],
    duration: float,
    cfg: SelectionConfig,
    account_niche: str,
) -> list[Candidate]:
    if not segments:
        return []
    candidates: list[Candidate] = []
    for index in range(0, len(segments), 2):
        start = float(segments[index]["start"])
        if start >= duration:
            break
        end = start
        window: list[dict] = []
        for segment in segments[index:]:
            if segment["start"] < start:
                continue
            if segment["end"] - start > cfg.max_duration_seconds and window:
                break
            window.append(segment)
            end = float(min(segment["end"], duration))
            if end - start >= cfg.max_duration_seconds:
                break
        if end - start < cfg.min_duration_seconds:
            continue
        end = min(end, start + cfg.max_duration_seconds)
        start, end = snap_to_speech(segments, start, end)
        if end - start < cfg.min_duration_seconds or end - start > cfg.max_duration_seconds + 1.5:
            continue
        scores = _heuristic_scores(segments, start, end, account_niche)
        text = _window_text(segments, start, end)
        topic = _guess_topic(_norm(text))
        title = _opening_quote(segments, start, end)
        if len(title.split()) < 4:
            title = _title_from_text(text)
        candidate = Candidate(
            start=round(start, 2),
            end=round(end, 2),
            scores={k: v for k, v in scores.items() if k != "niche_fit"},
            niche_fit=scores["niche_fit"],
            topic=topic,
            title=title,
            caption="",
            reason="heuristik transkrip",
            provider="heuristic",
        )
        candidates.append(candidate)
    return candidates


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    decoder = json.JSONDecoder()
    payloads: list[dict[str, Any]] = []
    cursor = 0
    while True:
        start = cleaned.find("{", cursor)
        if start == -1:
            break
        try:
            payload, end = decoder.raw_decode(cleaned, start)
        except json.JSONDecodeError:
            cursor = start + 1
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
        cursor = end
    if not payloads:
        raise ValueError("JSON tidak ditemukan")
    if len(payloads) == 1:
        return payloads[0]
    merged = dict(payloads[0])
    merged["candidates"] = [
        item for payload in payloads for item in payload.get("candidates", [])
    ]
    return merged


def _gemini_call(prompt: str, model: str, api_key: str) -> str:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    response = httpx.post(
        url,
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
                "maxOutputTokens": 8192,
            },
        },
        timeout=90.0,
    )
    response.raise_for_status()
    data = response.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(part.get("text", "") for part in parts)


def _ollama_call(prompt: str, model: str, base_url: str) -> str:
    response = httpx.post(
        f"{base_url.rstrip('/')}/api/chat",
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        },
        timeout=120.0,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def _ollama_alive(base_url: str) -> bool:
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/api/tags", timeout=2.0)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def _resolve_provider(cfg: SelectionConfig) -> str:
    if cfg.provider != "auto":
        return cfg.provider
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    if _ollama_alive(cfg.ollama_url):
        return "ollama"
    return "heuristic"


def _chunk_segments(segments: list[dict], chunk_seconds: float) -> list[list[dict]]:
    chunks: list[list[dict]] = []
    current: list[dict] = []
    chunk_start = segments[0]["start"] if segments else 0.0
    for segment in segments:
        if current and segment["end"] - chunk_start > chunk_seconds:
            chunks.append(current)
            current = []
            chunk_start = segment["start"]
        current.append(segment)
    if current:
        chunks.append(current)
    return chunks


def _llm_prompt(
    chunk: list[dict], duration: float, cfg: SelectionConfig, niche: str
) -> str:
    lines = []
    for segment in chunk:
        lines.append(
            f"[{segment['start']:.2f}-{segment['end']:.2f}] {segment['text'].strip()}"
        )
    max_clips = max(2, min(6, cfg.clips_per_video + 2))
    return (
        "Kamu editor video short-form senior dan analis retensi penonton.\n"
        f"Durasi video sumber: {duration:.1f} detik. Niche akun: {niche}.\n"
        f"Pilih maksimal {max_clips} momen paling kuat dari transkrip ini.\n"
        "Aturan:\n"
        f"- Durasi klip {cfg.min_duration_seconds:.0f}-{cfg.max_duration_seconds:.0f} detik.\n"
        "- Mulai dan akhir harus memakai timestamp yang ada di transkrip.\n"
        "- Jangan memilih segmen yang saling tumpang tindih.\n"
        "- Prioritaskan hook kuat, payoff lengkap, retensi, emosi, kejelasan konteks.\n"
        "- Topik antar kandidat harus bervariasi.\n"
        "- Jangan mengarang kutipan atau timestamp. Jangan menjanjikan viralitas.\n"
        "Balas JSON valid tanpa teks lain dengan bentuk:\n"
        '{"candidates":[{"start":0.0,"end":0.0,"hook_text":"","payoff_summary":"",'
        '"topic":"","title":"","caption":"","scores":{"hook":0,"payoff":0,'
        '"retention":0,"emotion":0,"clarity":0,"av":0,"niche_fit":0}}]}\n'
        "Nilai scores 0-100.\n"
        "Transkrip:\n" + "\n".join(lines)
    )


def _llm_candidates(
    transcript: dict[str, Any],
    cfg: SelectionConfig,
    account_niche: str,
    provider: str,
) -> list[Candidate]:
    segments = transcript["segments"]
    duration = float(transcript.get("duration") or segments[-1]["end"])
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if provider == "gemini" and not api_key:
        raise RuntimeError("GEMINI_API_KEY tidak tersedia")
    candidates: list[Candidate] = []
    for chunk in _chunk_segments(segments, cfg.chunk_seconds):
        prompt = _llm_prompt(chunk, duration, cfg, account_niche)
        raw = _call_with_retry(provider, prompt, cfg, api_key)
        try:
            payload = _extract_json(raw)
        except ValueError as exc:
            log.warning("JSON LLM tidak valid (%s), ulang sekali", exc)
            raw = _call_with_retry(provider, prompt, cfg, api_key)
            payload = _extract_json(raw)
        if not payload.get("candidates"):
            for attempt in range(2, 4):
                log.warning(
                    "LLM %s balas 0 kandidat, ulang (%s/3)", provider, attempt
                )
                raw = _call_with_retry(provider, prompt, cfg, api_key)
                try:
                    payload = _extract_json(raw)
                except ValueError:
                    payload = {"candidates": []}
                if payload.get("candidates"):
                    break
        for item in payload.get("candidates", []):
            candidate = _candidate_from_llm(
                item, duration, cfg, account_niche, segments
            )
            if candidate is not None:
                candidates.append(candidate)
    log.info("LLM (%s) mengembalikan %s kandidat", provider, len(candidates))
    return candidates


def _call_with_retry(
    provider: str,
    prompt: str,
    cfg: SelectionConfig,
    api_key: str,
    attempts: int = 5,
) -> str:
    delay = 8.0
    for attempt in range(1, attempts + 1):
        try:
            if provider == "gemini":
                return _gemini_call(prompt, cfg.gemini_model, api_key)
            if provider == "ollama":
                return _ollama_call(prompt, cfg.ollama_model, cfg.ollama_url)
            raise RuntimeError(f"provider tidak didukung: {provider}")
        except Exception as exc:
            if attempt == attempts:
                raise
            log.warning("LLM %s gagal (try %s/%s): %s", provider, attempt, attempts, exc)
            time.sleep(delay)
            delay = min(delay * 2, 90)
    raise RuntimeError("retry habis")


def _candidate_from_llm(
    item: dict[str, Any],
    duration: float,
    cfg: SelectionConfig,
    account_niche: str,
    segments: list[dict] | None = None,
) -> Candidate | None:
    try:
        start = float(item["start"])
        end = float(item["end"])
    except (KeyError, TypeError, ValueError):
        return None
    if start < 0 or start >= duration or end <= start:
        return None
    end = min(end, duration)
    if end - start > cfg.max_duration_seconds:
        end = start + cfg.max_duration_seconds
    if segments:
        start, end = snap_to_speech(segments, start, end)
    if end - start < cfg.min_duration_seconds:
        return None
    if end - start > cfg.max_duration_seconds + 1.5:
        end = start + cfg.max_duration_seconds
    scores_raw = item.get("scores") or {}
    scores: dict[str, float] = {}
    for key in WEIGHTS:
        value = scores_raw.get(key, 50)
        try:
            scores[key] = round(_clamp(float(value)), 1)
        except (TypeError, ValueError):
            scores[key] = 50.0
    try:
        niche_fit = _clamp(float(scores_raw.get("niche_fit", 70)))
    except (TypeError, ValueError):
        niche_fit = _nearest_topic(_norm(str(item.get("topic", ""))), account_niche)
    topic = str(item.get("topic") or "umum").strip().lower()[:40] or "umum"
    title = str(item.get("title") or "").strip()
    if segments:
        quote = _opening_quote(segments, start, end)
        # judul LLM hanya dipakai kalau benar-benar menyebut ucapan pembuka;
        # kalau tidak, kutipan asli lebih aman (tidak mismatch dengan audio)
        if quote and (
            not title
            or not any(w in _norm(title) for w in quote.lower().split()[:3])
        ):
            title = quote
    if not title:
        title = _opening_quote(segments or [], start, end) or _title_from_text(
            str(item.get("hook_text", ""))
        )
    return Candidate(
        start=round(start, 2),
        end=round(end, 2),
        scores=scores,
        niche_fit=round(niche_fit, 1),
        topic=topic,
        title=title[:120],
        caption=str(item.get("caption") or "").strip()[:220],
        reason=str(item.get("payoff_summary") or "").strip()[:300],
        provider="llm",
    )


def _overlap_ratio(a: Candidate, b: Candidate) -> float:
    intersection = max(0.0, min(a.end, b.end) - max(a.start, b.start))
    shortest = min(a.duration, b.duration)
    return intersection / shortest if shortest > 0 else 0.0


def _dedupe(candidates: list[Candidate], max_overlap: float = 0.2) -> list[Candidate]:
    kept: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda c: c.final_score(), reverse=True):
        if any(_overlap_ratio(candidate, other) > max_overlap for other in kept):
            continue
        kept.append(candidate)
    return kept


def _pick_diverse(
    candidates: list[Candidate], count: int, min_score: float
) -> list[Candidate]:
    eligible = [c for c in candidates if c.final_score() >= min_score]
    if not eligible:
        return []
    selected: list[Candidate] = []
    used_topics: set[str] = set()
    for candidate in eligible:
        if candidate.topic in used_topics:
            continue
        selected.append(candidate)
        used_topics.add(candidate.topic)
        if len(selected) >= count:
            return selected
    for candidate in eligible:
        if candidate in selected:
            continue
        selected.append(candidate)
        if len(selected) >= count:
            break
    return selected


def select_clips(
    transcript: dict[str, Any],
    settings: Settings,
    account: Account,
    provider: str | None = None,
) -> list[Candidate]:
    cfg = settings.selection
    segments = transcript.get("segments") or []
    duration = float(transcript.get("duration") or 0)
    if not segments or duration <= 0:
        return []
    heuristic = heuristic_candidates(segments, duration, cfg, account.niche)
    chosen_provider = provider or _resolve_provider(cfg)
    llm: list[Candidate] = []
    if chosen_provider in {"gemini", "ollama"}:
        try:
            llm = _llm_candidates(transcript, cfg, account.niche, chosen_provider)
        except Exception as exc:
            log.warning("LLM gagal (%s), fallback heuristik: %s", chosen_provider, exc)
    combined = _dedupe([*llm, *heuristic])
    limit = min(cfg.clips_per_video, settings.safety.max_clips_per_source)
    return _pick_diverse(combined, limit, cfg.min_score)
