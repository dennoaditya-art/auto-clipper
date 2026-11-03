# Diagnosa & Perbaikan Performa (2026-11-03)

Data nyata channel utama: 90 subscriber, 33 video, 11 klip diukur.

## Temuan utama

**Korelasi skor sistem vs views: +0.147** (praktis nol).
Skor 92.2 dapat **0 views**, skor 89.3 dapat 16 views. Sistem penilaian tidak
memprediksi performa, jadi tuning hook saja tidak akan menolong.

| Klip | Skor | Durasi | Views |
|---|---|---|---|
| 13 Dapat kado kocak… | 91.0 | 20.0s | **1349** |
| 11 Seru banget pas buka kado… | 94.1 | 55.7s | 255 |
| 12 Untung gak nyerah… | 92.0 | 60.0s | 36 |
| 16 Bocoran Film Baru… | 89.3 | 37.3s | 16 |
| 20 Sisi Lain Freya… | 90.3 | 24.0s | 11 |
| 14 Topik Skripsi… | 90.7 | 20.0s | 8 |
| 15 Belajar Dance Bebek… | 90.4 | 41.6s | 3 |
| 21 Aksi Jiko Shokai… | 89.8 | 20.0s | 3 |
| 17 Cerita Catchphrase Kristi | 92.2 | 43.1s | **0** |
| 18 Budaya Pouch Sharing | 90.7 | 60.0s | **0** |
| 19 Nonton Sambil Joget | 90.3 | 30.3s | **0** |

## Bukti: judul tidak cocok dengan audio

| Klip | Judul | 3 detik pertama (audio asli) |
|---|---|---|
| 13 | Dapat kado kocak di luar dugaan | "bukan itu guru Zanfir Zanfir?" |
| 17 | Cerita Di Balik Catchphrase Kristi | "guys nah gue mau nanya nih gue takut dirujak" |
| 20 | Sisi Lain Freya JKT48 | *(tidak ada kata sama sekali)* |
| 15 | Belajar Dance Bebek Muter JKT48 | *(tidak ada kata)* |
| 21 | Aksi Jiko Shokai Member JKT48 | "lemah santai terlemah roblox bertema horror" |

Satu-satunya klip yang dapat views (1349) adalah satu-satunya yang audio
awalnya relevan dengan judulnya.

## Empat cacat teknis yang diperbaiki

1. **Potongan mentok batas minimum** — 3 dari 11 klip tepat `20.0s`, tanda
   potongan memukul `min_duration_seconds`, bukan mengikuti kalimat.
2. **Klip dimulai sebelum ada ucapan** — #15 mulai 7,19s lebih awal, #20
   **16,83s** lebih awal (17 detik tanpa ada yang dibicarakan).
3. **Kalimat terpotong di ujung** — #17 kehilangan 0,96s kata terakhir,
   #21 kehilangan 0,08s.
4. **Judul digenerate AI**, bukan dikutip dari audio → mismatch.

## Perubahan yang diterapkan

| Perubahan | File |
|---|---|
| `snap_to_speech()` — rapatkan batas klip ke ucapan, buang lead-in, tarik sampai kalimat selesai | `select.py` |
| `_opening_quote()` — judul dari ucapan 3,5 detik pertama, buang filler (guys/jadi/nah) | `select.py` |
| Snapping diterapkan di jalur heuristik **dan** LLM | `select.py` |
| Judul LLM hanya dipakai kalau menyebut ucapan pembuka | `select.py` |
| `category_id` bisa diatur, default tetap 22 | `config.py`, `youtube.py` |
| Hashtag dibersihkan: buang `#fyp` (sinyal TikTok, bukan YouTube) | `settings.yaml` |
| Fitur `longcut` — video 16:9 8–15 menit | `render.py`, `pipeline.py`, `cli.py` |
| 6 tes regresi batas klip | `tests/test_clip_boundaries.py` |

Tes: **42 → 48 lulus**.

## Fitur longcut

```powershell
# video panjang 10 menit, 1920x1080, tanpa crop/zoom/hook
autoclip longcut 11 --minutes 10
autoclip longcut 11 --minutes 12 --start 1200
```

Karakteristik: 16:9 penuh, subtitle SRT (bukan karaoke vertikal), watermark
tetap dipasang, hasil langsung `approved`. Ceruk berbeda dari Shorts: video
panjang mengejar jam tonton (syarat YPP 4.000 jam), bukan views cepat.

## Yang masih perlu diukur

Perubahan ini belum terbukti menaikkan views — buktinya baru ada setelah klip
baru tayang minimal 7 hari. Yang bisa dipastikan sekarang: cacat batas klip
dan mismatch judul sudah hilang secara terukur.
