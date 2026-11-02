import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from autoclip.subtitles import clip_srt, ts_srt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)


def transcribe(video, model_size, lang, compute):
    from faster_whisper import WhisperModel

    print(f"[*] model={model_size} compute={compute}", file=sys.stderr)
    model = WhisperModel(model_size, device="cpu", compute_type=compute)
    segments, info = model.transcribe(
        str(video), word_timestamps=True, language=lang, vad_filter=True
    )
    print(f"[*] lang={info.language} dur={info.duration:.1f}s", file=sys.stderr)

    segs = []
    for s in segments:
        words = [
            {"w": w.word, "s": w.start, "e": w.end} for w in (s.words or [])
        ]
        segs.append({"start": s.start, "end": s.end, "text": s.text.strip(), "words": words})
        print(f"  {ts_srt(s.start)} {s.text.strip()}", file=sys.stderr)

    data = {
        "file": str(video),
        "language": info.language,
        "duration": info.duration,
        "segments": segs,
    }
    jpath = video.with_suffix(".transcript.json")
    jpath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    spath = video.with_suffix(".srt")
    with spath.open("w", encoding="utf-8") as f:
        for i, s in enumerate(segs, 1):
            f.write(f"{i}\n{ts_srt(s['start'])} --> {ts_srt(s['end'])}\n{s['text']}\n\n")

    print(f"[+] {jpath}", file=sys.stderr)
    print(f"[+] {spath}", file=sys.stderr)
    return jpath


def load_transcript(video):
    jpath = video.with_suffix(".transcript.json")
    if not jpath.exists():
        sys.exit(f"transcript missing: {jpath} (jalankan: clip.py transcribe)")
    return json.loads(jpath.read_text(encoding="utf-8"))


def cut_one(video, clip, transcript, vertical, burn, style, crf):
    start, end = float(clip["start"]), float(clip["end"])
    title = clip.get("title") or f"clip_{int(start)}_{int(end)}"
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title).strip() or "clip"
    outp = OUT / f"{safe}.mp4"

    tmp = Path(tempfile.mkdtemp(prefix="clip_"))
    vf = []
    if vertical:
        vf.append(
            "crop=w='min(iw,ih*9/16)':h='min(ih,iw*16/9)':"
            "x='(iw-ow)/2':y='(ih-oh)/2',scale=1080:1920:flags=lanczos,setsar=1"
        )
    if burn:
        n = clip_srt(transcript, start, end, tmp / "sub.srt")
        if n:
            vf.append(f"subtitles=sub.srt:force_style='{style}'")

    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    cmd += ["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(video)]
    if vf:
        cmd += ["-vf", ",".join(vf)]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p"]
    cmd += ["-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(outp)]

    print(f"[*] {title}: {start:.1f}-{end:.1f}s -> {outp.name}", file=sys.stderr)
    subprocess.run(cmd, cwd=str(tmp), check=True)
    print(f"[+] {outp}", file=sys.stderr)
    return outp


DEFAULT_STYLE = (
    "FontName=Arial,FontSize=8,Bold=1,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=0.7,Shadow=0,"
    "Alignment=2,MarginV=45"
)


def main():
    ap = argparse.ArgumentParser(description="Whisper clipper: transcribe + cut 9:16 + burn subs")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("transcribe")
    t.add_argument("video", type=Path)
    t.add_argument("--model", default="small")
    t.add_argument("--lang", default=None)
    t.add_argument("--compute", default="int8")

    c = sub.add_parser("cut")
    c.add_argument("video", type=Path)
    c.add_argument("--clips", type=Path, required=True, help="JSON list [{start,end,title}]")
    c.add_argument("--no-vertical", action="store_true")
    c.add_argument("--no-subs", action="store_true")
    c.add_argument("--style", default=DEFAULT_STYLE)
    c.add_argument("--crf", type=int, default=20)

    a = ap.parse_args()
    if a.cmd == "transcribe":
        transcribe(a.video, a.model, a.lang, a.compute)
        return
    if a.cmd == "cut":
        transcript = load_transcript(a.video)
        clips = json.loads(a.clips.read_text(encoding="utf-8"))
        if isinstance(clips, dict):
            clips = clips.get("clips", [])
        for clip in clips:
            cut_one(
                a.video,
                clip,
                transcript,
                vertical=not a.no_vertical,
                burn=not a.no_subs,
                style=a.style,
                crf=a.crf,
            )


if __name__ == "__main__":
    main()
