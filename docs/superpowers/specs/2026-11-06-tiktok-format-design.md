# Format TikTok Windah — design

Tanggal: 2026-11-06
Status: menunggu persetujuan

## Kenapa

Akun TikTok `@saint.gabrieldesign` ("Windah Clips ID"): 4 follower, 4 video,
218–635 views/video. Target: reach cukup untuk dibayar program klip
(Motion Klip / ezklip / campaign Windah) — jalur yang dipakai ketiga akun
pembanding, bukan Creator Rewards.

## Bukti (diambil 6 Nov 2026)

| akun | follower | likes | video | catatan |
|---|---|---|---|---|
| @easeeii | 1.436 | 1,07 jt | 335 | 1,6 jt views saat `#windahcampaign2`; Okt turun 1–3 rb |
| @bngnimz | 224 | 37,6 rb | 312 | 12 video dalam 2 jam; 1 video 165 rb |
| @warxxxyz | 410 | 134,8 rb | 18 | mulai 25 Okt; 658 rb, 129 rb, 139 rb |

Semua: `#windahbasudara #windahMKLIP2 #motionklip #ezklip`, bio
"clipper @motion.klip".

Format pemenang (658 rb, 29 detik, Roblox/Opah) — dicek dari file aslinya:
- kanvas 9:16, footage **letterbox hitam** (tidak di-zoom penuh)
- kutipan punchline putih tebal di tengah, dalam tanda kutip
- strip brand "motion klip" di bar atas
- facecam tetap kelihatan di pojok
- caption meme pendek + emoji

Kita sekarang: crop-fill mengikuti wajah (80% frame dinding), zoom punch,
caption naratif, 1 video/hari.

## Temuan kode yang mengubah rencana

1. **Auto-publish TikTok belum tersambung.** `_auto_publish` memanggil
   `publish_clip` tanpa `platform` → default YouTube, dan `publish_approved`
   hanya memilih akun `youtube_enabled`. TikTok selama ini hanya manual.
2. **Letterbox belum mungkin tanpa mode render baru.** `_crop_filter` selalu
   crop-fill lalu `_zoom_filter` memaksa `s=1080x1920`; `zoom_punch: true`.
3. **"Tidak ada subtitle = tidak tayang" belum ada gerbangnya.** Render
   lanjut diam-diam kalau ASS kosong.
4. **Payoff ≤35 detik bertabrakan dengan `_shape_bounds`** yang justru
   menggeser start mundur agar payoff di akhir klip.
5. **Caption sekarang dari LLM/title**, bukan dari baris payoff.
6. **Views per klip belum bisa diukur**: `remote_id` TikTok berisi URL
   halaman Studio, bukan id video.

## Keputusan

1. **Layout** (`render.py`, mode `vertical_letterbox`): kanvas 1080x1920
   hitam, sumber di-scale lebar 1080 (tinggi 608), ditaruh y=240,
   `zoom_punch` mati, `face_crop` mati. Facecam ikut di dalam frame.
2. **Subtitel wajib**: ASS dari segmen transkrip, putih tebal + outline
   hitam, maks 2 baris, di dalam area footage. Render **gagal** kalau tidak
   ada satu pun baris subtitle.
3. **Stiker judul**: payoff 2–5 kata, kotak putih + teks hitam, y≈120,
   tampil 0 sampai akhir.
4. **Seleksi** (`select.py`): target 22–45 detik; payoff di 8 detik terakhir;
   sisa waktu dipakai untuk lead-in (bukan menambah ekor).
5. **Caption** (`publish.py`): kalimat meme ≤60 karakter dari segmen payoff
   + 1 emoji + hashtag tetap. Tidak pakai caption LLM untuk TikTok.
6. **Auto-jadwal TikTok**: `_auto_publish` mengirim ke TikTok juga (akun
   `tiktok_enabled`), slot terpisah dari YouTube, maks 2 per jam.
   `slots` menjadi `["15:00","16:00","17:00","18:00","19:30","21:00","22:00"]`
   (plus `slots_by_day` disesuaikan).
7. **Ukur**: simpan id video TikTok dari URL post setelah upload;
   `data/tiktok_report.py` ambil views, cetak median per minggu.
8. **Dua profil render** dari klip yang sama:
   - `tiktok`: letterbox 9:16 + quote + stiker + brand strip.
   - `shorts`: crop-fill 9:16 penuh layar + hook 2 detik; subtitle tetap.
   Longform tetap 16:9. Path TikTok disimpan terpisah (`clips.tiktok_path`).
9. **Kunci niche: Roblox + Opah.** Hanya sumber Windah Roblox yang diproses;
   kandidat yang menyebut opah/roblox/backroom/hantu/jumpscare dapat bonus
   skor. Sumber lain (JKT48, Raditya Dika, Maen Hakim) dilewati sampai format
   terbukti.

## Non-tujuan

- Creator Rewards (>1 menit) — tidak sekarang.
- Musik trending otomatis.
- Mengubah longform 16:9 selain judul/thumbnail.
- Menambah sumber baru sampai format Roblox terbukti (minimal 2 video >50rb).

## Risiko

- Sumber Windah 854x480 → upscale tetap blur; sama seperti pembanding.
- Konten repost: tiga akun pembanding identik dan tetap dapat reach.
- Dual-publish menambah beban: satu klip bisa makan kuota YouTube dan slot
  TikTok sekaligus; `_auto_publish` harus idempoten per platform.

## Verifikasi

Satu tes per logika baru: caption dari payoff, ASS subtitle + gerbang gagal,
filter letterbox (tinggi 608 di y=240), dan pemilihan slot TikTok terpisah.
