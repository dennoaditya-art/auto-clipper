# Alur Kerja: Clip Windah → Upload TikTok → Claim MotionKlip

Diperbarui 2026-11-02. Semua angka diambil langsung dari Discord MotionKlip.

## 1. Campaign yang masih hidup

| Campaign | Budget | Mode | Min views | Maks payout/video | Platform |
|---|---|---|---|---|---|
| `nautilus-windah-interview` | **100%** | per 1.000 views | 3.000 | Rp4.500.000 | TikTok |
| `sunforged-windah` | **97%** | per 1.000 views | 3.000 | Rp4.500.000 | TikTok |
| `nautilus-windah` | 82% | per 1.000 views | 3.000 | Rp4.500.000 | TikTok |
| `velixir-windah` | 82,42% | per 1.000 views | 5.000 | Rp3.000.000 | TikTok |
| ~~`windah-mklip`~~ | **0%** | fixed | 200.000 | Rp400.000 | mati |

Rumus: `payout = (views / 1000) × CPM`. Cap 1.000.000 views per video.

Cek ulang kapan saja:

```powershell
D:\clipper\.venv\Scripts\python.exe -m autoclip.cli campaign list
```

## 2. Ambil video Windah yang belum pernah dipakai

```powershell
# daftar video dengan durasi paling masuk akal (30-90 menit)
D:\clipper\.venv\Scripts\python.exe -c "import subprocess,sys; subprocess.run([sys.executable,'-m','yt_dlp','--force-ipv4','--flat-playlist','--playlist-end','15','--print','%(id)s|%(duration)s|%(title)s','https://www.youtube.com/@WindahBasudara/videos'])"
```

Pilih durasi 30–90 menit. Hindari yang > 2 jam.

## 3. Daftarkan sumber lalu proses

Edit `config/sources.yaml`, tambah entri (id unik):

```yaml
  - id: windah3
    url: "https://www.youtube.com/watch?v=<VIDEO_ID>"
    account: utama
    enabled: true
    rights_approved: false
    rights_risk_accepted: true
    rights_reference: "Campaign resmi MotionKlip (Windah x MotionKlip)"
    campaign: nautilus-windah-interview
    watermark: "MKLP"
    latest: 1
```

> Kalau video sama sudah pernah dipakai, `sources.sha256` UNIQUE akan menolak.
> Pakai video lain.

Lalu:

```powershell
# unduh
D:\clipper\.venv\Scripts\python.exe -m autoclip.cli sync --source windah3

# scan + transkripsi + pilih klip + render (watermark otomatis)
D:\clipper\.venv\Scripts\python.exe -m autoclip.cli run --account utama
```

Klip keluar di `storage\review\clips\`. Status `approved`, **tidak** diunggah ke
YouTube karena campaign-nya TikTok-only.

## 4. Ambil caption siap-tempel

```powershell
D:\clipper\.venv\Scripts\python.exe -m autoclip.cli campaign caption <CLIP_ID>
```

Output: judul + `#windahbasudara #windahMKLIP2 #motionklip #ezklip`.
**Urutan hashtag wajib persis itu.**

## 5. Upload ke TikTok

1. Buka `https://www.tiktok.com/upload`
2. Upload file dari `storage\review\clips\`
3. Tempel caption dari langkah 4
4. Pastikan watermark MotionKlip + teks `MKLP` terlihat di video
5. Publish

Platform yang diterima: **TikTok saja** untuk keempat campaign aktif.
(`windah-mklip` menerima YouTube/IG/X/Threads tapi budget-nya sudah 0%.)

## 6. Catat klaim

```powershell
D:\clipper\.venv\Scripts\python.exe -m autoclip.cli campaign claim <CLIP_ID> `
  --campaign nautilus-windah-interview `
  --url "https://www.tiktok.com/@akun/video/123..." `
  --views 12000
```

Cek status & total:

```powershell
D:\clipper\.venv\Scripts\python.exe -m autoclip.cli campaign status
```

## 7. Submit Google Form di Discord

1. Buka channel `#💸┃claim-reward-<campaign>` di Discord MotionKlip
2. Klik **LINK CLAIM REWARD**
3. Isi: email, nama, no. telepon, akun sosmed, campaign, link video,
   jumlah views, screenshot analytics
4. Tunggu approval; uang masuk ke **GoPay / DANA**

Setelah uang masuk:

```powershell
D:\clipper\.venv\Scripts\python.exe -m autoclip.cli campaign paid <CLAIM_ID>
```

## Syarat yang tidak boleh dilewat

- **Server Tag Discord harus `MKLP`** — sudah di-set 2026-11-02
- Watermark template MotionKlip wajib ada di setiap video
- Hashtag urutan: `#windahbasudara #windahMKLIP2 #motionklip #ezklip`
- Klaim hanya boleh di **minggu yang sama** dengan upload (`windah-mklip`)
- Dilarang view botting / paid views / ads boosting — didiskualifikasi
- Dilarang reupload tanpa editing

## Catatan realistis

- Target minimum 3.000 views/video relatif ringan, tapi **Rp13.500 per 3.000
  views** artinya perlu volume besar untuk uang yang berarti.
- 100.000 views ≈ Rp450.000. Ini side income, bukan gaji.
- Budget campaign bisa habis kapan saja — cek `campaign list` sebelum upload.
- Belum ada konfirmasi pembayaran independen; bukti transfer di Discord adalah
  klaim pihak MotionKlip.
