from __future__ import annotations

import textwrap
from pathlib import Path


def ts_srt(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis == 1000:
        secs += 1
        millis = 0
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _cues(text: str, max_chars: int) -> list[str]:
    lines = textwrap.wrap(
        " ".join(text.split()),
        width=max_chars,
        break_long_words=False,
        break_on_hyphens=False,
    )
    return ["\n".join(lines[i : i + 2]) for i in range(0, len(lines), 2)]


def clip_srt(
    transcript: dict,
    start: float,
    end: float,
    srt_path: Path,
    max_chars: int = 32,
) -> int:
    entries: list[tuple[float, float, str]] = []
    for segment in transcript.get("segments", []):
        seg_start = float(segment["start"])
        seg_end = float(segment["end"])
        if seg_end <= start or seg_start >= end:
            continue
        text = str(segment["text"]).strip()
        if not text:
            continue
        absolute_start = max(seg_start, start)
        absolute_end = min(seg_end, end)
        cues = _cues(text, max_chars)
        if not cues:
            continue
        total = sum(len(cue.replace("\n", " ")) for cue in cues) or 1
        cursor = absolute_start
        span = max(0.2, absolute_end - absolute_start)
        for cue in cues:
            share = len(cue.replace("\n", " ")) / total
            cue_end = min(absolute_end, cursor + span * share)
            if cue_end - cursor >= 0.15:
                entries.append((cursor - start, cue_end - start, cue))
            cursor = cue_end

    lines = []
    for index, (cue_start, cue_end, cue_text) in enumerate(entries, 1):
        lines.append(
            f"{index}\n{ts_srt(cue_start)} --> {ts_srt(cue_end)}\n{cue_text}\n"
        )
    srt_path.write_text("\n".join(lines), encoding="utf-8")
    return len(entries)

def _ass_ts(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:d}:{minutes:02d}:{secs:05.2f}"


def hook_ass(
    text: str,
    seconds: float,
    ass_path: Path,
    width: int = 1080,
    height: int = 1920,
    wrap: int = 20,
    watermark: str = "",
    mark_alignment: int = 3,
) -> bool:
    clean = " ".join(str(text).replace("{", "").replace("}", "").split())
    mark = " ".join(str(watermark).replace("{", "").replace("}", "").split())
    if not clean and not mark:
        return False
    lines = textwrap.wrap(clean, width=wrap) or [""]
    body = "\\N".join(lines[:3])
    header = (
        "[Script Info]\n"
        f"ScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Hook,Arial,72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,"
        "-1,0,0,0,100,100,0,0,1,4,0,8,60,60,140,1\n"
        "Style: Mark,Arial,34,&H00E6E6E6,&H00E6E6E6,&H00000000,&H4D000000,"
        f"0,0,0,0,100,100,0,0,1,2,0,{mark_alignment},40,40,260,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    events = ""
    if clean:
        events += (
            f"Dialogue: 1,{_ass_ts(0.0)},{_ass_ts(seconds)},Hook,,0,0,0,,{body}\n"
        )
    if mark:
        events += f"Dialogue: 0,{_ass_ts(0.0)},{_ass_ts(3599.0)},Mark,,0,0,0,,{mark}\n"
    ass_path.write_text(header + events, encoding="utf-8")
    return True


def _highlight(hex_rgb: str) -> str:
    """'#RRGGBB' -> ASS '&H00BBGGRR' (ASS menyimpan BGR)."""
    h = hex_rgb.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}"



def _words_in_window(
    transcript: dict, start: float, end: float
) -> list[dict]:
    """Kata per-kata (dengan timing) di dalam rentang klip."""
    words: list[dict] = []
    for segment in transcript.get("segments", []):
        seg_start = float(segment["start"])
        seg_end = float(segment["end"])
        if seg_end <= start or seg_start >= end:
            continue
        seg_words = segment.get("words") or []
        if seg_words:
            for item in seg_words:
                try:
                    w_start = float(item.get("s", seg_start))
                    w_end = float(item.get("e", seg_end))
                except (TypeError, ValueError):
                    w_start, w_end = seg_start, seg_end
                token = str(item.get("w", "")).strip()
                if not token:
                    continue
                if w_end <= start or w_start >= end:
                    continue
                words.append(
                    {"w": token, "s": max(w_start, start), "e": min(w_end, end)}
                )
            continue
        # fallback: bagi teks segmen merata
        text = str(segment["text"]).strip()
        if not text:
            continue
        tokens = text.split()
        t0 = max(seg_start, start)
        t1 = min(seg_end, end)
        span = max(0.2, t1 - t0)
        total = sum(len(t) for t in tokens) or len(tokens)
        cursor = t0
        for token in tokens:
            step = span * (len(token) + 1) / (total + len(tokens))
            w_end = min(t1, cursor + step)
            words.append({"w": token, "s": cursor, "e": w_end})
            cursor = w_end
    return words


def _group_lines(
    words: list[dict], max_chars: int, max_words: int
) -> list[list[dict]]:
    lines: list[list[dict]] = []
    current: list[dict] = []
    chars = 0
    for word in words:
        length = len(word["w"]) + (1 if current else 0)
        gap = (word["s"] - current[-1]["e"]) if current else 0.0
        if current and (gap > 0.6 or chars + length > max_chars or len(current) >= max_words):
            lines.append(current)
            current = []
            chars = 0
        current.append(word)
        chars += length
    if current:
        lines.append(current)
    return lines


def clip_karaoke_ass(
    transcript: dict,
    start: float,
    end: float,
    ass_path,
    width: int = 1080,
    height: int = 1920,
    max_chars: int = 22,
    max_words: int = 6,
    margin_v: int = 0,
) -> int:
    """ASS karaoke: teks besar, kata aktif ter-highlight menyala (gaya edit fan-made)."""
    words = _words_in_window(transcript, start, end)
    lines = _group_lines(words, max_chars, max_words)
    if not lines:
        return 0
    fontsize = max(34, int(width * 0.052))
    if margin_v <= 0:
        margin_v = int(height * 0.10)
    header = (
        "[Script Info]\n"
        f"ScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\n"
        "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Kara,Arial,{fontsize},&H00FFFFFF,&H00CE00E6,&H00000000,"
        f"&H47000000,-1,0,0,0,100,100,0,0,1,3,0,2,60,60,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )
    events = ""
    for line in lines:
        line_start = line[0]["s"] - start
        line_end = line[-1]["e"] - start
        line_start = max(0.0, line_start)
        line_end = max(line_start + 0.15, line_end)
        text = ""
        for index, word in enumerate(line):
            # tag \k mendahului teks yang di-timing; spasi menjaga kata tidak menempel
            text += f"{{\\k{max(1, int(round((word['e'] - word['s']) * 100)))}}}{word['w']}"
            if index < len(line) - 1:
                text += " "
        events += (
            f"Dialogue: 0,{_ass_ts(line_start)},{_ass_ts(line_end)},Kara,,0,0,0,,{text}\n"
        )
    ass_path.write_text(header + events, encoding="utf-8")
    return len(lines)

