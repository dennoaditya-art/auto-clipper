# Roblox/Opah TikTok + Shorts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ubah output klip pendek jadi format ala akun pembanding (letterbox + kutipan + stiker, Roblox/Opah saja) dan sambungkan penjadwalan TikTok otomatis.

**Architecture:** Satu mesin seleksi menghasilkan klip; pipeline merender dua varian (TikTok letterbox, Shorts crop-fill) dari sumber yang sama. Publikasi per platform memakai slot dan caption sendiri, dengan jalur file terpisah.

**Tech Stack:** Python 3.12, ffmpeg/ffprobe, ASS subtitle, Playwright (TikTok), SQLite, pytest.

**Spec:** `docs/superpowers/specs/2026-11-06-tiktok-format-design.md`

## Global Constraints

- Kanvas klip pendek: 1080x1920.
- Durasi klip pendek: 22–45 detik; payoff di ≤8 detik terakhir.
- Caption TikTok: kalimat meme ≤60 karakter + 1 emoji + hashtag tetap, tanpa caption LLM.
- Hashtag wajib tidak berubah: dari `campaigns`/`sources` (`#windahbasudara` dll).
- Niche: hanya sumber di `focus.sources`; bonus kata kunci `focus.keywords`.
- Tanpa dependency baru. Test pakai pytest, gaya yang sudah ada di `tests/`.
- Commit kecil, pesan imperatif bahasa Indonesia seperti commit sebelumnya.

## Review Focus

- Transkrip kosong/segmen tanpa kata → render harus gagal jelas, bukan menghasilkan video bisu tanpa teks.
- Sumber 4:3 atau vertikal (JKT48/daily48) → mode letterbox tidak boleh menghasilkan crop aneh (mereka keluar dari `focus.sources`, tapi renderer tetap harus aman).
- Klip <22 detik di ujung sumber → seleksi tidak boleh memaksa 22 detik ke luar durasi sumber.
- Publish TikTok gagal di tengah → tidak boleh menandai klip `published` atau menghapus file.
- Slot YouTube dan TikTok yang berdekatan → satu klip tidak boleh memakai slot yang sama di dua platform.

---

### Task 1: Kunci niche Roblox/Opah

**Files:**
- Modify: `autoclip/config.py` (dataclass `FocusConfig`, field `Settings.focus`, parse di loader)
- Modify: `autoclip/pipeline.py` (sumber yang diproses difilter)
- Modify: `autoclip/select.py` (`_focus_bonus` dipakai di `_make_candidate`)
- Modify: `config/settings.yaml` (blok `focus:`)
- Test: `tests/test_focus.py`

**Interfaces:**
- Produces: `FocusConfig(sources: tuple[str, ...], keywords: tuple[str, ...], keyword_bonus: float)`; `Settings.focus: FocusConfig`; `select._focus_bonus(text: str, focus: FocusConfig) -> float`.

- [ ] **Step 1: Write the failing test**

```python
def test_focus_bonus_counts_keywords():
    focus = FocusConfig(sources=("windah3",), keywords=("opah", "roblox"), keyword_bonus=2.5)
    assert _focus_bonus("Opah nya seram, ini roblox", focus) == 5.0
    assert _focus_bonus("main gta biasa", focus) == 0.0


def test_focus_sources_filter(settings_factory):
    settings = settings_factory(focus_sources=("windah3",))
    names = [s.id for s in settings.focus_active_sources()]
    assert names == ["windah3"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_focus.py -v`
Expected: FAIL `ImportError: cannot import name 'FocusConfig'`

- [ ] **Step 3: Implement**

`config.py`: dataclass beku `FocusConfig` dengan default `sources=()`, `keywords=()`, `keyword_bonus=0.0`; loader membaca `focus:` dari `settings.yaml`; `Settings.focus_active_sources()` mengembalikan `active_sources()` difilter `focus.sources` (kosong = semua).

`select.py`: `_focus_bonus` menjumlahkan `keyword_bonus` untuk setiap kata kunci yang muncul (case-insensitive) di teks segmen. Di `_make_candidate`, tambahkan hasilnya ke `scores["focus"]`.

`pipeline.py`: sumber yang diproses = `settings.focus_active_sources()`.

`config/settings.yaml`:

```yaml
focus:
  sources: ["windah", "windah3"]
  keywords: ["opah", "roblox", "backroom", "hantu", "jumpscare"]
  keyword_bonus: 2.5
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_focus.py tests/test_select.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoclip/config.py autoclip/pipeline.py autoclip/select.py config/settings.yaml tests/test_focus.py
git commit -m "Kunci niche klip ke Roblox/Opah"
```

---

### Task 2: Durasi 22–45 detik, payoff di 8 detik terakhir

**Files:**
- Modify: `autoclip/select.py:255-330` (`_shape_bounds`, `_extend_context`)
- Modify: `config/settings.yaml` (`selection.min_duration_seconds: 22`, `max_duration_seconds: 45`)
- Test: `tests/test_select.py`

**Interfaces:**
- Consumes: `SelectionConfig.min_duration_seconds`, `.max_duration_seconds`.
- Produces: `_shape_bounds` tetap `(start, end)`; jaminan `end - payoff_end <= 8.0`.

- [ ] **Step 1: Write the failing test**

```python
def test_payoff_within_last_8_seconds():
    segments = _fake_segments([(0, 3), (3, 6), (6, 9), (9, 40)])
    start, end = _shape_bounds(segments, 6.0, 9.0, cfg(max_duration_seconds=45))
    assert end - 9.0 <= 8.0
    assert 22 <= end - start <= 45


def test_short_source_not_padded_past_duration():
    start, end = _shape_bounds(_fake_segments([(0, 3), (3, 18)]), 3.0, 18.0, cfg())
    assert end <= 18.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_select.py -k payoff_within -v`
Expected: FAIL (payoff bisa >8 detik dari akhir)

- [ ] **Step 3: Implement**

Di `_shape_bounds`: setelah payoff ditetapkan, ekor (`after`) dibatasi `max(0, min(8.0, cap - payoff_len))`; sisa durasi ke bawah diisi lewat `_extend_context(before=...)` sampai `min_duration_seconds`. Jangan pernah melewati durasi sumber (`duration` parameter baru, default `float("inf")`).

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_select.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoclip/select.py config/settings.yaml tests/test_select.py
git commit -m "Batasi klip pendek 22-45 detik dengan payoff di ekor"
```

---

### Task 3: Subtitle wajib (render gagal kalau kosong)

**Files:**
- Modify: `autoclip/render.py:473-500`
- Test: `tests/test_render.py`

**Interfaces:**
- Produces: `render_clip` melempar `RenderError("subtitle kosong")` bila `render.subtitles` benar dan tidak ada cue.

- [ ] **Step 1: Write the failing test**

```python
def test_render_fails_without_subtitles(tmp_path, settings_factory, video_with_speech):
    with pytest.raises(RenderError, match="subtitle kosong"):
        render_clip(video_with_speech, probe(video_with_speech), 0, 5, "tes",
                    settings_factory(subtitles=True), {"segments": []},
                    tmp_path, 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_render.py -k subtitle -v`
Expected: FAIL (tidak ada exception)

- [ ] **Step 3: Implement**

Setelah `clip_karaoke_ass`/`clip_srt` dipanggil, jika keduanya menghasilkan 0 dan `render.subtitles` benar → `raise RenderError("subtitle kosong")` sebelum ffmpeg dijalankan.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoclip/render.py tests/test_render.py
git commit -m "Gagalkan render klip tanpa subtitle"
```

---

### Task 4: Profil render TikTok (letterbox 9:16)

**Files:**
- Modify: `autoclip/render.py` (`_letterbox_filter`, parameter `profile`)
- Test: `tests/test_render.py`

**Interfaces:**
- Produces: `render_clip(..., profile: str = "shorts")`; `profile="tiktok"` memakai `_letterbox_filter(info, render) -> str` yang menghasilkan `scale=1080:-2,pad=1080:1920:0:240:black` (footage tinggi 608 di y=240) dan **tidak** memanggil `_zoom_filter`.

- [ ] **Step 1: Write the failing test**

```python
def test_letterbox_filter_geometry():
    info = VideoInfo(duration=10, width=854, height=480, has_audio=True, fps=30)
    f = _letterbox_filter(info, cfg_render(width=1080, height=1920))
    assert "scale=1080:-2" in f
    assert "pad=1080:1920:0:240" in f


def test_letterbox_filter_handles_4_3():
    info = VideoInfo(duration=10, width=640, height=480, has_audio=True, fps=30)
    f = _letterbox_filter(info, cfg_render(width=1080, height=1920))
    assert "pad=1080:1920:0:" in f
    assert "810" in f  # 1080 / (4/3)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_render.py -k letterbox -v`
Expected: FAIL `NameError: _letterbox_filter`

- [ ] **Step 3: Implement**

`_letterbox_filter` menghitung tinggi footage dari rasio sumber, memakai `pad` hitam dengan `y=240` untuk rasio 16:9 (dan `y=(1920-h)/2` untuk rasio lain). Di `render_clip`, `profile="tiktok"` → filter letterbox, `face_crop=False`, `zoom_punch=False`, stiker judul tampil seluruh durasi (bukan `hook_seconds`).

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoclip/render.py tests/test_render.py
git commit -m "Tambah profil render TikTok letterbox"
```

---

### Task 5: Profil Shorts (crop-fill + hook 2 detik)

**Files:**
- Modify: `autoclip/render.py` (cabang `profile="shorts"`)
- Modify: `config/settings.yaml` (`render.hook_seconds: 2`)
- Test: `tests/test_render.py`

**Interfaces:**
- Produces: `profile="shorts"` = perilaku sekarang (crop-fill + zoom + hook), dengan `hook_seconds` 2.0.

- [ ] **Step 1: Write the failing test**

```python
def test_shorts_profile_uses_crop_not_letterbox(monkeypatch, ...):
    captured = {}
    monkeypatch.setattr(render, "_crop_filter", lambda *a: captured.setdefault("crop", "yes") and "crop")
    render_clip(..., profile="shorts")
    assert "crop" in captured
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_render.py -k shorts_profile -v`
Expected: FAIL (parameter `profile` belum ada)

- [ ] **Step 3: Implement**

Cabang `shorts` mempertahankan filter lama; `hook_seconds` dibaca dari config (2 detik). `profile` divalidasi: hanya `shorts`/`tiktok`; nilai lain → `ValueError`.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_render.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoclip/render.py config/settings.yaml tests/test_render.py
git commit -m "Pisahkan profil render Shorts dengan hook 2 detik"
```

---

### Task 6: Simpan dua varian per klip

**Files:**
- Modify: `autoclip/db.py:120-127` (`_migrate`: `ALTER TABLE clips ADD COLUMN tiktok_path TEXT`), `add_clip` (parameter `tiktok_path: str | None = None`)
- Modify: `autoclip/pipeline.py` (render dua profil untuk klip pendek, isi `tiktok_path`)
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `render_clip(..., profile=...)` dari Task 4–5.
- Produces: kolom `clips.tiktok_path`; `add_clip(..., tiktok_path=None)`.

- [ ] **Step 1: Write the failing test**

```python
def test_clip_stores_tiktok_path(tmp_path):
    conn = connect(tmp_path / "db.sqlite")
    init_db(conn)
    cid = add_clip(conn, 1, 0.0, 5.0, "judul", "sku", {"total": 1}, "/f.mp4", "h",
                   tiktok_path="/t.mp4")
    assert get_clip(conn, cid)["tiktok_path"] == "/t.mp4"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -k tiktok_path -v`
Expected: FAIL `TypeError: add_clip() got an unexpected keyword argument`

- [ ] **Step 3: Implement**

Migrasi kolom; `add_clip` menulis nilainya. `pipeline` merender `profile="shorts"` (YouTube) dan `profile="tiktok"` (hanya bila ada akun `tiktok_enabled`), lalu menyimpan keduanya.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoclip/db.py autoclip/pipeline.py tests/test_db.py
git commit -m "Simpan varian TikTok terpisah per klip"
```

---

### Task 7: Caption TikTok dari baris payoff

**Files:**
- Modify: `autoclip/publish.py:123-134` (`_tiktok_caption`)
- Test: `tests/test_publish.py`

**Interfaces:**
- Produces: `_tiktok_caption(settings, conn, clip, transcript: dict | None = None) -> str`; baris payoff = teks segmen terakhir di dalam `[start, end]`, dipotong 60 karakter, tambah emoji dan hashtag yang belum ada.

- [ ] **Step 1: Write the failing test**

```python
def test_caption_uses_payoff_line(settings_factory, conn):
    tr = {"segments": [{"start": 0, "end": 2, "text": "awal"},
                       {"start": 40, "end": 45, "text": "opah nya baik banget sih"}]}
    cap = _tiktok_caption(settings_factory(), conn, clip_row(start=0, end=45), tr)
    assert cap.startswith("opah nya baik banget")
    assert "#windahbasudara" in cap
    assert len(cap.split("#")[0]) <= 63
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_publish.py -k payoff -v`
Expected: FAIL (caption masih dari `scores_json`)

- [ ] **Step 3: Implement**

Ambil segmen dengan `end` terbesar di dalam rentang klip, `strip()`, buang tanda kutip, potong ke 60 karakter pada batas kata, tambahkan satu emoji dari daftar tetap (`😭 😹 🗿 😱 🔥` dipilih berdasarkan ada/tidaknya kata kunci horor), lalu hashtag yang belum ada. Fallback ke `clip["title"]` kalau transkrip kosong.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_publish.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoclip/publish.py tests/test_publish.py
git commit -m "Buat caption TikTok dari baris payoff"
```

---

### Task 8: Auto-jadwal TikTok

**Files:**
- Modify: `autoclip/db.py:365-372` (`future_scheduled_slots(conn, platform: str | None = None)`)
- Modify: `autoclip/pipeline.py:346-364` (`_auto_publish`)
- Modify: `autoclip/publish.py:159-180` (`publish_clip` memakai `tiktok_path` untuk TikTok)
- Modify: `config/settings.yaml` (`upload.slots` + `slots_by_day` versi baru)
- Test: `tests/test_publish.py`

**Interfaces:**
- Produces: `future_scheduled_slots(conn, platform=None) -> set[str]`; `_auto_publish` memanggil `publish_clip(..., platform="youtube")` lalu `publish_clip(..., platform="tiktok")` dengan set slot masing-masing.

- [ ] **Step 1: Write the failing test**

```python
def test_slots_are_per_platform(conn):
    begin_publication(conn, 1, "youtube", "utama", scheduled_at="2026-11-08T11:00:00Z")
    assert future_scheduled_slots(conn, "youtube") == {"2026-11-08T11:00:00Z"}
    assert future_scheduled_slots(conn, "tiktok") == set()


def test_tiktok_failure_does_not_block_youtube(monkeypatch, settings_factory, conn):
    calls = []

    def fake_publish(settings, conn, clip_id, *, platform="youtube", publish_at=None):
        calls.append(platform)
        if platform == "tiktok":
            raise RuntimeError("tiktok mati")
        return "yt-id"

    monkeypatch.setattr(pipeline, "publish_clip", fake_publish)
    pipeline._auto_publish(settings_factory(), conn, [1])
    assert calls == ["youtube", "tiktok"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_publish.py -k per_platform -v`
Expected: FAIL (`future_scheduled_slots` tidak menerima `platform`)

- [ ] **Step 3: Implement**

`future_scheduled_slots` menambah `AND platform = ?` bila `platform` diisi. `_auto_publish` merawat dua set `used` dan memanggil `publish_clip` per platform; kegagalan satu platform tidak membatalkan yang lain (log warning). `publish_clip` untuk platform `tiktok` memakai `Path(clip["tiktok_path"] or clip["file_path"])`.

`config/settings.yaml`:

```yaml
  slots: ["15:00", "16:00", "17:00", "18:00", "19:30", "21:00", "22:00"]
  slots_by_day:
    Friday: ["15:00", "16:00", "17:00", "19:00", "20:00", "21:00"]
    Saturday: ["11:00", "15:00", "17:00", "19:00", "20:00", "21:00"]
    Sunday: ["11:00", "15:00", "17:00", "19:00", "20:00", "21:00"]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_publish.py tests/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoclip/db.py autoclip/pipeline.py autoclip/publish.py config/settings.yaml tests/test_publish.py
git commit -m "Jadwalkan TikTok otomatis dengan slot terpisah"
```

---

### Task 9: Laporan views mingguan

**Files:**
- Create: `autoclip/tiktok_report.py` (`parse_content_rows(text: str) -> list[dict]`)
- Create: `data/tiktok_report.py` (skrip Playwright yang membuka Studio dan mencetak median)
- Test: `tests/test_tiktok_report.py`

**Interfaces:**
- Produces: `parse_content_rows(text)` → `[{"caption": str, "when": str, "views": int}]`; skrip mencetak `n`, `median`, `max`.

- [ ] **Step 1: Write the failing test**

```python
def test_parse_rows():
    rows = parse_content_rows("01:00\nCaption satu\nNov 13, 8:00 PM\nEveryone\n0\n10\n2\n")
    assert rows == [{"when": "Nov 13, 8:00 PM", "caption": "Caption satu", "views": 0}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_tiktok_report.py -v`
Expected: FAIL `ModuleNotFoundError`

- [ ] **Step 3: Implement**

Parser memecah `innerText` Studio per blok (durasi → caption → waktu → privacy → views → likes → comments) dan mengambil views. Skrip memakai `tiktok.py` yang sudah ada untuk membuka sesi, lalu mencetak statistik.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_tiktok_report.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add autoclip/tiktok_report.py data/tiktok_report.py tests/test_tiktok_report.py
git commit -m "Tambah laporan views TikTok mingguan"
```
