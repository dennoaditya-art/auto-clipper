# Auto-clipper lokal

Video panjang → klip vertikal 9:16 + subtitle → review manusia → upload YouTube private. Gratis, CPU-only.

## Mulai

```powershell
$py = "D:\clipper\.venv\Scripts\python.exe"
& $py -m autoclip doctor
```

Taruh video milik sendiri di `storage\incoming`, lalu:

```powershell
& $py -m autoclip run
```

Review di `storage\review\review.html`. Setelah perbaiki / setujui:

```powershell
& $py -m autoclip list
& $py -m autoclip approve 1
& $py -m autoclip reject 2 --reviewer nama
```

## Perintah

| Perintah | Fungsi |
|---|---|
| `run [--limit N]` | sync channel + scan + proses + auto-publish |
| `sync` | unduh upload baru dari channel di `sources.yaml` |
| `scan` | daftar file baru di `incoming` |
| `process ID --force` | proses ulang satu sumber |
| `list [--status pending] [--sources]` | daftar klip/sumber |
| `approve ID [--publish]` / `reject ID` | review klip |
| `auth youtube --account utama` | OAuth YouTube (token terenkripsi) |
| `publish ID` / `publish --all-approved` | upload klip approved |
| `review` | tulis ulang `review.html` |
| `doctor` | cek ffmpeg, modul, config, folder |

## Channel sumber

`config\sources.yaml` — hanya channel milik sendiri atau yang sudah diizinkan:

```yaml
sources:
  - id: channel-saya
    url: "https://www.youtube.com/@nama/videos"
    account: utama
    enabled: true
    rights_approved: true
    rights_reference: "video milik sendiri"
    latest: 3
```

Mode risiko (hanya jika pemilik akun eksplisit menanggung akibatnya):

```yaml
    rights_approved: false
    rights_risk_accepted: true
    rights_reference: "izin belum terverifikasi; risiko ditanggung (tanggal)"
```

`run` otomatis memanggil `sync` untuk source aktif. Butuh `yt-dlp` di PATH.
Video orang lain tanpa izin berisiko strike/takedown; gunakan hanya dengan persetujuan pemilik akun.

## Upload YouTube

1. Buat project di Google Cloud → aktifkan **YouTube Data API v3**.
2. OAuth consent screen → tambahkan akun sebagai test user.
3. Credentials → **OAuth client ID** → tipe **Desktop app**.
4. Simpan JSON sebagai `config\client_secret.json` (jangan commit).
5. Set `platforms.youtube.enabled: true` di `config\accounts.yaml`.
6. Hubungkan: `python -m autoclip auth youtube --account utama`.
7. Upload: `python -m autoclip approve 1 --publish` atau `publish --all-approved`.

Project belum diaudit bisa dipaksa upload `private` oleh YouTube; pertahankan
`privacy: private` sampai audit selesai. Kuota 2026: sekitar 100 upload/hari.

Set `auto_publish: true` pada akun untuk upload otomatis **setelah** klip
di-approve. Approval tetap manual.

## TikTok

Belum diimplementasikan. Direct Post publik wajib audit TikTok; client
unaudited hanya bisa `SELF_ONLY`. Tidak ada cara aman untuk bypass audit.

## Otomatis saat login

```powershell
powershell -ExecutionPolicy Bypass -File D:\clipper\scripts\install-task.ps1
```

Log: `logs\run.log`. Hapus: `Unregister-ScheduledTask -TaskName AutoClipper`.

## Config

- `config\settings.yaml`: durasi klip, ambang skor, encoder, subtitle, rights.
- `config\accounts.yaml`: akun, niche, izin.
- `GEMINI_API_KEY` (opsional): scoring lebih pintar. Tanpa key → heuristik lokal.
- `rights.status`: `approved` (izin jelas) atau `risk_accepted` (risiko ditanggung pemilik akun).

## Catatan mesin ini

- 1 job sekaligus; model `small` int8; encoder QuickSync → fallback libx264.
- `ffprobe` dan `ffmpeg` tersedia di PATH.
- File sumber tidak dihapus. Cache transkrip di `storage\work`, DB di `data\autoclip.db`.
- Legacy manual: `clip.py transcribe` + `clip.py cut` masih bisa dipakai.
