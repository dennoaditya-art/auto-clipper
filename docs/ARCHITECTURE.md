# AI Shorts Studio — Architecture & Implementation Plan (Milestone 0)

Status: DRAFT — menunggu approval sebelum Milestone 1.
Tanggal audit: 2026-11-01. Repo: `D:\clipper`.

---

## 1. Hasil audit repository (kondisi saat ini)

**Yang ada sekarang = clipper 9:16 dari video panjang milik channel pihak ketiga.** Bukan studio produksi.

| Aspek | Temuan |
|---|---|
| Bahasa | Python 3.11.15 (`.venv`), tanpa `pyproject.toml`/`requirements.txt` (dependency di-install manual) |
| Bentuk | CLI monolit: `python -m autoclip <cmd>` (~17 modul flat di `autoclip/`) |
| Web/API | **Tidak ada**. Review berupa HTML statis (`storage/review/review.html`) |
| DB | SQLite `data/autoclip.db` (sumber, jobs, clips, reviews, publications) |
| Transkripsi | faster-whisper `small` int8, CPU, word-timestamps |
| Pemilihan klip | Gemini (`gemini-3.5-flash-lite`) + fallback heuristik/Ollama (`select.py`) |
| Render | FFmpeg + QuickSync `h264_qsv` (fallback libx264); karaoke ASS, emoji hook, zoompan |
| Upload | YouTube Data API v3, OAuth PKCE, scope `youtube.force-ssl`, token dienkripsi DPAPI (`secure.py`) |
| Unduh sumber | yt-dlp (module) + resume/retry |
| Penjadwalan | slot per hari (WIB) + `publishAt`, task Windows (`AutoClipper`, `AutoclipRetryPublish`) |
| Tes | 34 pytest lulus |
| Aset runtime | ffmpeg/ffprobe (choco), Node v24.13.1, npm 11.8, Deno tidak ada |
| Hardware | i3-1315U (6C/8T), **RAM 7.7 GB**, disk D: 96 GB free, tanpa GPU diskrit |

**Reusable (jangan ditulis ulang):**
- `transcribe.py` (whisper + cache), `subtitles.py` (SRT/karaoke ASS/hook), `render.py` (crop wajah, QSV, thumbnail, zoom, emoji), `media.py` (probe/sha256), `select.py` (scoring + provider LLM), `translate.py`, `youtube.py` (OAuth/enkripsi/upload/thumbnail/update), `publish.py` (slot + idempotensi publikasi), `db.py`, `secure.py`, `config.py`, `sources.py`/`scan.py`, `review.py` (approval + hash guard).
- **Penting:** `review.py` sudah menegakkan aturan bisnis "hash berubah → approval batal" — jadi fondasi rule *editing invalidates approval* sudah ada.

**Utang/risiko yang harus diselesaikan desain baru:**
1. Sumber = konten pihak ketiga (`rights_risk_accepted`) → risiko claim. Studio baru harus default **milik sendiri / berlisensi**.
2. Tidak ada concept Project/Niche/Script/Asset/Voiceover/Storyboard → seluruh alur "generate original" belum ada.
3. Status hanya YouTube; TikTok/IG belum ada (adapter kosong).
4. SQLite single-writer; belum ada queue durable.
5. Analitik & revenue belum ada sama sekali.

---

## 2. Dua mode produksi (jelaskan sejak awal)

Plan menyebut "Hybrid AI production" — artinya **dua sumber bahan**, satu pipeline hilir:

- **Mode A — Clip (ada sekarang):** video panjang (milik sendiri/berlisensi) → klip 9:16. Memakai `sources/scan/process`.
- **Mode B — Generate (baru):** ide → naskah → storyboard → aset → TTS → render. Memakai modul baru.

Keduanya menghasilkan **Video Version** yang sama, lalu masuk alur yang sama: Review → Approve → Schedule → Publish → Analytics.

> Rekomendasi: bangun Mode B sebagai jalur baru yang **memakai ulang** engine render/voice/subtitle yang sudah ada. Jangan merombak Mode A.

---

## 3. Keputusan teknologi (rekomendasi tegas, sadar RAM 8 GB)

Plan meminta evaluasi. Keputusan + alasan:

| Area | Rekomendasi | Alasan (8 GB) |
|---|---|---|
| Bahasa backend | **Python + FastAPI** | Engine inti sudah Python. Menambah Node backend = dua runtime + dua ekosistem. FastAPI ringan (~80 MB). |
| Dashboard | **Next.js (App Router)** — build `output: standalone`, dipakai sebagai UI saja | Node sudah ada (v24). Dijalankan **hanya saat dipakai**; bukan proses permanen di mesin produksi. Alternatif ringan: static export. |
| DB | **SQLite (WAL) untuk lokal single-user**; jalur migrasi ke **PostgreSQL** disiapkan (SQLAlchemy/Alembic) | Postgres (~150–250 MB) + Redis + workers di 8 GB itu mepet. SQLite cukup untuk 1 operator. Naik ke Postgres saat multi-user/paralel. |
| Queue | **DB-backed job queue + 1 worker proses** (bukan Redis/Celery dulu) | Hemat ~200–400 MB; idempotensi lewat tabel `jobs` + `UNIQUE`. Redis hanya bila butuh prioritas/rate-limit lintas proses. |
| Render | **FFmpeg (QSV)** sebagai utama; **Remotion opsional** untuk motion graphic kelak | FFmpeg sudah terbukti + QSV. Remotion butuh Chromium (~300–500 MB) → jadikan fitur opsional, bukan default. |
| TTS | **Provider adapter**: Edge-TTS lokal/`piper` (offline) sebagai default, cloud (ElevenLabs/OpenAI) opsional | CPU-only → offline TTS lebih hemat & tak butuh kuota. |
| AI teks | Adapter **Ollama (lokal)** + **Gemini** (cloud) — pola `select.py` sudah ada | Sudah terimplementasi; tinggal digeneralisasi. |
| Storage | **Filesystem lokal**; adapter **S3-compatible (MinIO)** opsional | Media besar (video) → jangan di DB. |
| Auth sesi | Single-user lokal; API key/token lokal | Belum perlu multi-tenant. |

**Prinsip:** satu proses API + satu proses worker + FFmpeg subprocess. Tidak menambah Redis/Postgres/Chromium sampai terbukti perlu.

---

## 4. Target struktur folder (modular monolith)

Lapisan: **Presentation → Application → Domain → Infrastructure**. Aturan: Domain tidak mengimpor Infrastructure; Application mengorkestrasi; Infrastructure mengimplementasi port.

```
D:\clipper\
├─ pyproject.toml                 # baru: deps + tooling (belum dibuat)
├─ apps/
│  ├─ api/                        # FastAPI (Presentation HTTP)
│  │  ├─ main.py                  # app factory, router mount
│  │  ├─ deps.py                  # DI: db session, current user, settings
│  │  ├─ routes/                  # projects, niches, ideas, scripts, storyboards,
│  │  │                           # assets, voiceovers, renders, reviews, schedules,
│  │  │                           # publications, analytics, revenue, providers
│  │  └─ schemas/                 # Pydantic DTO (request/response)
│  ├─ worker/                     # 1 proses background (poll job queue)
│  │  ├─ runner.py
│  │  └─ handlers/                # render, tts, publish, analytics_sync
│  └─ web/                        # Next.js dashboard (UI only, panggil /api/v1)
├─ autoclip/                      # ENGINE LAMA — dipertahankan, jadi Infrastructure/Domain lama
│  ├─ media.py  transcribe.py  subtitles.py  render.py  translate.py
│  ├─ select.py  youtube.py  publish.py  secure.py  config.py  sources.py  scan.py
│  └─ db.py        # akan di-supersede bertahap oleh repositories baru
├─ shorts/                        # paket baru (Domain + Application)
│  ├─ domain/                     # entity + aturan bisnis murni (tanpa I/O)
│  │  ├─ project.py niche.py idea.py script.py storyboard.py
│  │  ├─ asset.py voiceover.py render.py review.py schedule.py publication.py
│  │  ├─ analytics.py revenue.py ai_disclosure.py
│  │  └─ policies.py              # aturan: approval→schedule, edit→invalidasi, dsb.
│  ├─ application/                # use case / service orkestrasi
│  │  ├─ idea_service.py script_service.py storyboard_service.py
│  │  ├─ render_service.py review_service.py schedule_service.py
│  │  ├─ publish_service.py analytics_service.py revenue_service.py
│  │  └─ ports.py                 # Protocol/ABC: AiProvider, TtsProvider, Renderer,
│  │                              # StoragePort, PlatformAdapter, JobQueue
│  └─ infrastructure/             # implementasi port
│     ├─ db/                      # SQLAlchemy models, repositories, migrations
│     ├─ ai/                      # ollama_adapter.py gemini_adapter.py (+ reuse autoclip.select)
│     ├─ tts/                     # piper_adapter.py edge_adapter.py cloud_*
│     ├─ render/                  # ffmpeg_renderer.py (wrap autoclip.render) | remotion_*
│     ├─ storage/                 # local_storage.py s3_storage.py
│     ├─ platforms/               # youtube_adapter.py (wrap autoclip.youtube) tiktok_* instagram_*
│     └─ queue/                   # db_queue.py (job tabel) redis_queue.py (opsional)
├─ config/                        # settings.yaml, accounts.yaml, sources.yaml (dipertahankan)
├─ storage/                       # incoming / projects / renders / review / published / work
├─ tests/
│  ├─ unit/                       # domain + policy (murni)
│  ├─ integration/                # repo + api (tmp sqlite)
│  └─ e2e/                        # alur approval→schedule (fake adapters)
└─ docs/                          # dokumen ini + ADR
```

**Aturan migrasi:** `autoclip/*` tidak diubah dulu; dibungkus adapter. Setelah modul baru stabil, pindahkan bertahap (strangler pattern).

---

## 5. Desain database (entitas & relasi)

Konvensi: semua waktu **UTC** (`TIMESTAMP WITH TZ` / ISO-8601 `Z`), tampilan sesuai timezone user. Semua tabel punya `id`, `created_at`, `updated_at`.

### 5.1 Inti produksi

```
projects(id, name, niche_id, target_platforms[], timezone, created_by, status)
niches(id, slug, name, keywords[], style_guide)
ai_providers(id, kind[ollama|gemini|openai], name, model, base_url, api_key_encrypted, enabled, cost_hint)

ideas(id, project_id, title, hook, angle, source[manual|research], research_refs[], score, status)
scripts(id, idea_id, version, language, body, disclosure_ai_generated, status)
storyboards(id, script_id, version, total_duration_s, status)
scenes(id, storyboard_id, idx, start_s, end_s, narration, on_screen_text, visual_prompt)
```

### 5.2 Aset & produksi media

```
assets(id, project_id, kind[image|video|music|sfx|broll], uri, mime, width, height,
       duration_s, source_type[generated|stock|own|licensed], license_id, checksum, meta_json)
asset_licenses(id, asset_id, license_name, license_url, attribution, expires_at, permitted_use)
voiceovers(id, script_id, provider, voice_id, language, uri, duration_s, checksum)
render_versions(id, project_id, script_id|clip_source_id, version_no, uri, duration_s,
       width, height, checksum, engine[ffmpeg|remotion], status[draft|rendered|failed],
       ai_disclosure_id)
ai_disclosures(id, kind[text|image|voice|video], tool, model, generated_at, metadata_json)
```

> `render_versions` menyatukan Mode A (klip) & Mode B (generate). Mode A: `clip_source_id` diisi; Mode B: `script_id` diisi.

### 5.3 Review & approval (aturan bisnis)

```
approvals(id, render_version_id, decision[approved|rejected], reviewer, approved_checksum,
          decided_at, note)
   -- UNIQUE aktif per render_version; approval hanya sah bila approved_checksum == render_versions.checksum
review_comments(id, render_version_id, scene_id?, author, body, created_at)
```

Aturan (ditegakkan di domain, diuji unit):
- Hanya `render_version` dengan **approval aktif & checksum cocok** boleh dijadwalkan.
- Render ulang/edit → `checksum` baru → approval lama otomatis **invalid** (`superseded`).
- Setiap platform punya status publikasi sendiri.

### 5.4 Jadwal & publikasi (idempoten, retry terbatas)

```
schedule_slots(id, project_id, platform, run_at_utc, timezone, status[free|reserved|used])
publication_jobs(id, render_version_id, platform, account_id, run_at_utc,
                 status[queued|running|succeeded|failed|needs_manual],
                 attempts, max_attempts, last_error, idempotency_key UNIQUE,
                 scheduled_at, published_at, remote_id)
platform_accounts(id, platform, display_name, credentials_encrypted, enabled, scopes[])
```

Idempotensi: `idempotency_key = hash(render_version_id, platform, account_id, version_no)`. Publikasi ulang dengan key sama tidak membuat duplikat (UNIQUE + cek status).
Retry: `attempts < max_attempts` (mis. 5) dengan backoff eksponensial; setelah habis → `needs_manual` + export manual.

### 5.5 Analitik & revenue

```
analytics_snapshots(id, publication_job_id, platform, captured_at_utc,
                    views, likes, comments, shares, watch_time_s, ctr, avg_view_s, raw_json)
affiliate_links(id, publication_job_id, program, url, utm_json)
revenue_events(id, affiliate_link_id?, publication_job_id?, platform, kind[ad|affiliate|sponsor],
               amount, currency, occurred_at_utc, raw_json)
audit_log(id, actor, action, entity, entity_id, before_json, after_json, at_utc)
oauth_credentials(id, platform_account_id, provider, encrypted_blob, scopes[], expires_at)
```

### 5.6 Relasi ringkas

```
projects 1─* ideas 1─* scripts 1─* storyboards 1─* scenes
projects 1─* assets 1─1 asset_licenses
scripts 1─* voiceovers
projects 1─* render_versions *─1 ai_disclosure
render_versions 1─* approvals / review_comments
render_versions 1─* publication_jobs 1─* analytics_snapshots
publication_jobs 1─* affiliate_links 1─* revenue_events
```

---

## 6. Batas modul & kontrak API

API REST `/api/v1`, JSON, semua timestamp ISO-8601 UTC. Error standar: `{code, message, details}`.

| Modul | Endpoint utama | Aturan kunci |
|---|---|---|
| Projects | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` | project wajib punya niche + ≥1 platform |
| Niches | `GET/POST /niches` | slug unik |
| AI Providers | `GET/POST /providers`, `POST /providers/{id}/test` | key tak pernah keluar (masked) |
| Ideas | `POST /projects/{id}/ideas:generate`, `GET /ideas`, `PATCH /ideas/{id}` | hasil simpan `research_refs` |
| Scripts | `POST /ideas/{id}/scripts:generate`, `GET/PATCH /scripts/{id}` | versi immutable; edit → versi baru
| Storyboards | `POST /scripts/{id}/storyboards:generate`, `GET /storyboards/{id}` | scenes berurutan, total durasi ≤ limit |
| Assets | `POST /assets` (upload/link), `GET /assets`, `PATCH /assets/{id}` | wajib `source_type` + `license` |
| Voiceover | `POST /scripts/{id}/voiceovers:generate` | simpan provider/voice |
| Renders | `POST /render-versions` (enqueue), `GET /render-versions/{id}`, `POST /render-versions/{id}:rerender` | hasil async; checksum wajib |
| Review | `GET /render-versions/{id}/review`, `POST /render-versions/{id}/approve`, `POST .../reject` | approve ONLY if checksum cocok & belum disetujui |
| Scheduling | `POST /render-versions/{id}/schedule`, `GET /schedule` | **tolak** bila belum approved/checksum mismatch |
| Publication jobs | `GET /publication-jobs`, `POST /publication-jobs/{id}/retry`, `POST .../export` | idempoten; retry ≤ max; export manual |
| Analytics | `GET /publications/{id}/analytics`, `POST /analytics:sync` | snapshot per waktu |
| Revenue | `GET /revenue`, `POST /revenue` | currency wajib |

**Port (interface domain):**
```python
class AiProvider(Protocol):
    def generate(self, prompt: str, *, schema: dict | None = None) -> dict: ...
class TtsProvider(Protocol):
    def synthesize(self, text: str, *, voice: str, lang: str) -> bytes: ...
class Renderer(Protocol):
    def render(self, spec: RenderSpec) -> RenderResult: ...   # spec→uri+checksum
class StoragePort(Protocol):
    def put(self, key: str, data: bytes, mime: str) -> str: ...
    def url(self, key: str) -> str: ...
class PlatformAdapter(Protocol):
    def publish(self, req: PublishRequest) -> PublishResult: ...
    def update_schedule(self, remote_id: str, when: datetime) -> None: ...
class JobQueue(Protocol):
    def enqueue(self, job: Job) -> str: ...
    def claim(self) -> Job | None: ...
    def complete(self, job_id: str, ok: bool, err: str | None) -> None: ...
```

`YoutubeAdapter` membungkus `autoclip.youtube`; `FfmpegRenderer` membungkus `autoclip.render` + `transcribe` + `subtitles`.

---

## 7. Rencana dependency & infrastruktur (8 GB)

**Python (tambahan dari yang terpasang):**
- `fastapi`, `uvicorn[standard]`, `pydantic`, `sqlalchemy>=2`, `alembic`, `python-multipart`, `jinja2` (opsional), `apscheduler` (opsional).
- Sudah ada: `faster-whisper`, `onnxruntime`, `opencv-python-headless`, `httpx`, `PyYAML`, `yt-dlp`, `numpy`, `pytest`.
- TTS: `piper-tts` (offline, ringan) — alternatif `edge-tts`.

**Node (dashboard):** Next.js, React, TypeScript, Tailwind, shadcn/ui. Tanpa state manager berat.

**Proses runtime (produksi lokal):**
```
1× uvicorn  (~100 MB)   1× worker (~150 MB saat transkripsi)   1× ffmpeg (transien)
Whisper small int8 (~0.5–1 GB saat jalan)   → jalankan 1 job paralel (RunLock sudah ada)
```
**Aturan hemat RAM:** hanya satu job render/transkripsi bersamaan; FFmpeg QSV; hindari Chromium/Remotion default.

**Penyimpanan:** video besar → filesystem; pertimbangkan MinIO hanya bila multi-mesin.

---

## 8. External API — kebutuhan, batasan, biaya

| Layanan | Dipakai untuk | Batasan/biaya | Catatan |
|---|---|---|---|
| YouTube Data API v3 | upload/thumbnail/update/publishAt/analytics | Kuota harian; *upload* mahal (~1600 unit/upload); default 10.000 unit/hari → efektif ±6 upload/hari; **batas jumlah video/hari akun** (sudah pernah kena `uploadLimitExceeded`) | Sudah diimplementasi; butuh audit project agar tak dipaksa private |
| TikTok Content Posting API | upload/publish | Direct Post butuh audit; unaudited = `SELF_ONLY`; rate limit per app/audit | Belum diimplementasi |
| Instagram Graph API (Reels) | publish | Butuh Business/Creator + App Review; rate limit; format khusus | Belum diimplementasi |
| Gemini API | ide/naskah/scoring/terjemah | Kuota & harga per token; model lite lebih murah | Sudah dipakai (`gemini-3.5-flash-lite`) |
| Ollama (lokal) | generasi teks offline | Gratis; butuh RAM/CPU | Adapter sudah ada (`select.py`) |
| TTS cloud (opsional) | voiceover | Berbayar per karakter | Default offline (piper) |
| yt-dlp | unduh sumber (Mode A) | Bukan API resmi; bisa berubah | **Hanya** untuk konten milik sendiri/berlisensi |

**Prinsip kepatuhan:** hanya API resmi; **tidak ada browser automation untuk publish**; sediakan export manual.

---

## 9. Rencana per milestone (default: verifikasi di tiap langkah)

**M0 — Audit & arsitektur (DOKUMEN INI).** Tanpa ubah source, tanpa install.
**M1 — Fondasi DB/API/Dashboard.** SQLAlchemy models + Alembic (SQLite), FastAPI skeleton, Next.js shell, worker loop, `projects/niches` CRUD.
**M2 — Abstraksi AI & generasi multi-niche.** Port `AiProvider`, adapter Ollama+Gemini; idea→script→storyboard generator; versi immutable.
**M3 — Aset, TTS, subtitle.** Storage lokal (S3 opsional), license tracking, TTS adapter, karaoke/ASS (reuse `subtitles.py`).
**M4 — Render otomatis.** `FfmpegRenderer` membungkus `autoclip.render`; `render_versions` + status async; Mode A & B.
**M5 — Review & approval.** Hash-guard (reuse `review.py`), approval aktif, edit→invalidasi, UI review.
**M6 — Scheduling & adapter platform.** Slot, idempotensi, retry terbatas, YouTube adapter (reuse), TikTok/IG di balik port + export manual.
**M7 — Analytics & revenue.** Sync metrik, snapshots, affiliate/revenue.

---

## 10. Kriteria penerimaan & tes otomatis per milestone

| Milestone | Acceptance criteria | Tes otomatis |
|---|---|---|
| M1 | API start; CRUD project/niche; migrasi jalan; worker klaim job | `pytest tests/integration/test_api_projects.py`, `test_migrations.py`, `test_queue.py`; smoke: `/health` |
| M2 | Generate idea→script→storyboard via adapter fake; versi immutable | `test_ai_ports.py` (fake AiProvider), `test_script_versioning.py`, `test_storyboard_order.py` |
| M3 | Upload aset + license wajib; TTS menghasilkan file; subtitle ASS valid | `test_assets_license_required.py`, `test_tts_adapter.py`, `test_karaoke_ass.py` |
| M4 | Render async → `render_versions.checksum` terisi; gagal→status failed | `test_render_job.py` (fake ffmpeg/fixture), `test_render_checksum.py` |
| M5 | Approve hanya bila checksum cocok; edit → approval invalid | `test_approval_checksum_guard.py`, `test_edit_invalidates_approval.py` |
| M6 | Schedule tolak belum-approved; publish idempoten; retry ≤ max; export manual | `test_schedule_requires_approval.py`, `test_publish_idempotent.py`, `test_retry_bounded.py`, `test_manual_export.py` |
| M7 | Snapshot metrik tersimpan; revenue multi-currency | `test_analytics_snapshot.py`, `test_revenue_currency.py` |

**Definition of Done tiap milestone:** tes lulus, tidak ada `eslint-disable`/`# type: ignore` baru, tidak ada dependency tak terpakai, migrasi reversible, dokumentasi endpoint diperbarui.

**Aturan tes (murah & deterministik):** adapter eksternal (YouTube/TikTok/IG/AI/TTS) **selalu** di-fake di tes; tidak ada panggilan network nyata di CI lokal; fixture video kecil (<2 s) untuk render.

---

## 11. Keputusan final (disetujui 2026-11-01)

| # | Keputusan | Nilai |
|---|---|---|
| 1 | Database | **SQLite WAL** untuk lokal; jalur Postgres via SQLAlchemy/Alembic disiapkan |
| 2 | Dashboard | **Next.js penuh** (App Router, UI-only) |
| 3 | TTS default | **piper offline** |
| 4 | Remotion | **Ditunda ke M7** (FFmpeg QSV utama sampai itu) |
| 5 | Repo lama | **Pertahankan `autoclip/` sebagai adapter** (strangler) |
| 6 | Sumber konten | **Pihak ketiga TETAP dipakai** (override user) — lihat catatan kepatuhan di bawah |

### 11.1 Catatan khusus: sumber pihak ketiga dipertahankan

Karena sumber pihak ketiga (mis. JKT48 TV, Daily48, Raditya Dika) tetap dipakai, mode produksi **Mode A (clip)** tetap berjalan dengan pengaturan risiko:

- Tandai setiap sumber `rights_risk_accepted: true` + `rights_reference` bertanggal; **jangan** set `rights_approved: true` untuk sumber yang belum berizin.
- Semua output tetap lewat **review manusia wajib** sebelum scheduling (aturan inti tidak berubah).
- Simpan `ai_disclosures` + metadata sumber/atribusi di setiap `render_version`.
- Risiko claim/strike/demonetisasi ditanggung pemilik akun (pernyataan tertulis di `rights.reference`).
- Adapter platform & alur lain tetap mengikuti plan (API resmi, tanpa browser automation, export manual cadangan).

> Konsekuensi: fitur komersial/analitik tetap dibangun, tetapi tidak dijanjikan aman dari klaim pihak ketiga. Bila kelak ingin monetisasi aman, gunakan jalur konten berlisensi (mis. program kampanye) tanpa mengubah arsitektur.

---

## 12. Yang TIDAK dilakukan di Milestone 0

- Tidak mengubah source apa pun.
- Tidak meng-install dependency.
- Tidak membuat skema DB nyata / migrasi.
- Tidak menulis kode fitur.

**Menunggu approval untuk mulai Milestone 1.**
