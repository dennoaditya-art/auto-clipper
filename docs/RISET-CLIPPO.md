# Clippo vs MotionKlip — riset 2026-11-02

Sumber: `clippo.id`, `app.clippo.id/campaigns`, detail campaign `cmv0h59il0kfbcv26ffgw79ut`,
FAQ publik. MotionKlip dari Discord (lihat `ALUR-MOTIONKLIP.md`).

## Clippo

- PT Clippo Media Digital, Jakarta Selatan. Situs publik + app `app.clippo.id`.
- Klaim 300.000+ clipper; halaman "Peringkat" menampilkan payout nyata (top ~Rp825.000/klip).
- **0% platform fee**, withdraw minimal **Rp100.000**.
- **Minimal 10 followers** untuk join campaign (followers hanya salah satu sinyal; like rate
  dan keorganikan views juga dinilai).
- Views dihitung dari **TikTok + Instagram**.
- Data diperbarui tiap 6 jam (01.00/07.00/13.00/19.00 WIB), bukan real-time.
- Pencairan setelah klip **disetujui admin**.
- Ada skema **referral komisi 1%**.
- Campaign hampir semuanya **materi disediakan brand** (footage resmi), bukan bebas ambil
  konten siapa pun. Wajib hashtag + tag + CTA + durasi sesuai brief.

### Contoh campaign (snapshot 2026-11-02)

| Campaign | CPM | Budget sisa |
|---|---|---|
| LIGHT+ X TASYA FARASYA | Rp5.000/1rb | 92% |
| BERL COSMETICS (keranjang kuning) | Rp4.000/video | 98% |
| NO NA X SHOPEE JINGLE | Rp4.000/1rb | 94% |
| KICK AVENUE FAIR 2026 | Rp3.000/1rb | 88% |
| KICK AVENUE X JEJOUW X LUKAS KAHN | Rp3.000/1rb | 90% |
| NEWLAB+ BODY LOTION x Amanda Manopo | Rp2.000/1rb | 74% |
| ANDREAS TOBING (AI) | Rp2.500/1rb | 6% |
| CLIP FOR CLIPPO | Rp1.000/1rb | 95% |
| TERNAK UANG X TIMOTHY RONALD | Rp500/1rb | 9% |
| JUAL EMAS INDONESIA | Rp400/1rb | 12% |

## MotionKlip (pembanding)

| | MotionKlip | Clippo |
|---|---|---|
| CPM Windah | Rp4.500/1rb (Nautilus/Sunforged) | — tidak ada campaign Windah |
| Min views | 3.000/video | tergantung campaign |
| Min followers | tidak ada | 10 |
| Platform | TikTok (campaign Windah) | TikTok + Instagram |
| Withdraw min | tidak dipublikasi | Rp100.000 |
| Sumber materi | bebas klip konten Windah | footage resmi brand |
| Budget | per-campaign, cepat habis | per-campaign, terlihat % |
| Fee | tidak disebut | 0% |

## Kesimpulan untuk pipeline `D:\clipper`

1. **Clippo tidak bisa langsung dipakai pipeline ini** tanpa perubahan: materi berasal dari
   brand (link Instagram/TikTok yang disediakan), bukan channel YouTube yang di-scrape.
   Pipeline sekarang mengambil dari YouTube + `yt_dlp`.
2. Yang **bisa dipakai ulang**: transkripsi, scoring momen, render 9:16 dengan karaoke
   subtitle, watermark overlay, dan pencatatan klaim.
   Yang harus ditambah: unduh materi dari **Instagram/TikTok** (atau input file manual),
   dukungan `instagram` sebagai platform, dan aturan brand (hashtag + tag + CTA + durasi).
3. **CPM Clippo lebih tinggi** di beberapa campaign (Rp5.000 vs Rp4.500), dan min followers
   cuma 10 — akun @saint.gabrieldesign (3 followers) **belum memenuhi**. Perlu naik ke 10
   dulu, atau pakai akun klip yang sudah ada.
4. Risiko: budget campaign habis (beberapa sudah 6–12%), dan pembayaran bergantung approval
   admin. Sama seperti MotionKlip, tidak ada jaminan.

## Langkah realistis

- Jangka pendek: lanjut MotionKlip (sudah jalan, 3 klip live).
- Kalau mau masuk Clippo: butuh modul sumber materi non-YouTube + akun dengan ≥10 followers.
- Jangan pindah sebelum ada bukti pencairan pertama dari salah satu platform.
