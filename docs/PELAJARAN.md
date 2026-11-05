# Pelajaran & Keputusan (jangan diulang salahnya)

## 2026-11-03 — Editing, facecam, longform

### ffmpeg diblokir Application Control
`C:\ProgramData\chocolatey\bin\ffmpeg.exe` (shim) diblokir kebijakan
Application Control dengan `WinError 4551`. Binary asli di
`chocolatey\lib\ffmpeg\tools\ffmpeg\bin\` **tidak** diblokir.
→ `ffmpeg_bin()` sekarang menguji tiap kandidat dengan `-version` dan memilih
yang benar-benar jalan. Override: env `AUTOCLIP_FFMPEG`.
→ Fixture tes juga harus pakai `ffmpeg_bin()`, bukan `"ffmpeg"` dari PATH.

### Wajah harus tetap terlihat (permintaan pemilik akun)
Wajah Windah ada di **facecam overlay sudut bawah**, ukurannya kecil (<8%
area frame). Detektor lama (skor 0.9, pilih wajah terbesar) sering
melewatkannya → crop jatuh ke tengah → wajah hilang.
→ `face_center_ratio()`: ambang diturunkan ke 0.55, wajah kecil diutamakan,
skor dikali 1.6 kalau posisinya di bawah 45% tinggi frame.
→ Untuk longform 16:9 tidak ada crop, jadi facecam otomatis utuh.

### Judul: ikuti ucapan, bukan karangan
Data 11 klip: korelasi skor vs views **+0.147**. Klip yang audionya cocok
dengan judul dapat 1349 views; yang mismatch dapat 0.
→ `_opening_quote()` mengambil ucapan 3,5 detik pertama, buang kata pengisi
(guys/jadi/nah), potong di batas kata utuh (bukan potong karakter).

### Batas klip: potong di ucapan, bukan di angka
Bukti: 3 dari 11 klip tepat `20.0s` (mentok minimum), #20 mulai 16,83s
sebelum kata pertama (17 detik tanpa suara), #17 kehilangan 0,96s kata terakhir.
→ `snap_to_speech()`: buang lead-in, tarik sampai kalimat selesai.

### Tag & kategori
`#fyp` dan `#shorts` adalah sinyal TikTok, bukan YouTube. Kategori default
"People & Blogs" (22) meleset untuk konten hiburan → jadi 24 (Entertainment)
dan bisa diatur lewat `upload.category_id`.

### Kompilasi longform (ala channel kompilasi)
Referensi: `4THglzTQBzU` (YTGaming Moments, 636s, 207rb views) — kompilasi
momen lucu dari beberapa video sumber.
→ `longcut <source> --minutes N` (default 15): pilih momen skor tinggi yang
tidak bertumpuk, kalau kurang tambah dari kandidat heuristik, gabung dengan
hard cut. Kalau butuh transisi xfade, itu kerja render terpisah yang jauh
lebih mahal — jangan dikerjakan sebelum terbukti perlu.
→ `--start` mempertahankan mode lama (satu potongan utuh).

### Kesalahan yang sempat terjadi dan cara menghindarinya
1. `-af loudnorm` **tidak boleh** dipakai bersama `-filter_complex`; harus
   jadi filter di dalam graf (`[ac]loudnorm...[acn]`). ffmpeg keluar kode
   `4294967274`.
2. Watermark hilang di kompilasi karena `render_compilation` tidak memanggil
   `hook_ass`. → ditambah `drawtext` dengan font yang dicari lewat `_font_path()`.
   Jalur font di filter ffmpeg butuh `:` di-escape jadi `\:`.
3. Playwright MCP hanya boleh membaca/menulis file di `C:\Users\<user>` dan
   `C:\Users\<user>\.playwright-mcp`; file dari drive lain harus disalin dulu.
4. TikTok Edit profile: Save tidak menyimpan nama sampai dialog kedua
   "Set nickname? … once every 7 days" diklik **Confirm**.
   Ganti foto profil butuh klik **Apply** di panel crop.

---

## 2026-11-04 - Kenapa Shorts sepi: metadata salah sasaran

### Diagnosis (bukan dugaan, dari API YouTube langsung)
Dari 31 video terunggah, **19 belum tayang** (`private` + `publishAt` di masa
depan) dan 12 sudah publik. Dari yang publik, **79% views menumpuk di 1 video**
(1349 views), sisanya 0-256. Median 0.

Yang benar-benar salah: **semua video memakai metadata JKT48**, termasuk
video Windah, Don't Play Play, dan Main Hakim Sendiri:

    TAGS : ['fyp','idol','jkt48','jkt48tv','shorts']
    DESC : "Sumber: JKT48 TV. Klip dikutip untuk sorotan."
    CAT  : 22

Akibatnya YouTube mengklasifikasikan video gaming/podcast sebagai konten idol
dan menayangkannya ke audiens yang tidak mencarinya. Ini penyebab utama, bukan
algoritma.

Penyebab kode: `upload.hashtags` dan `upload.credit` di `settings.yaml`
bersifat **global** - satu nilai untuk semua sumber.

### Perbaikan
1. `Source` sekarang punya `hashtags` dan `credit` sendiri (opsional,
   fallback ke global). `publish._source_meta()` memilih metadata berdasarkan
   nama file sumber (`windah-xxxx.mp4` -> source `windah`).
2. Campaign hanya dipakai kalau platform-nya cocok. Campaign MotionKlip
   itu `platforms: [tiktok]`, jadi tidak boleh menempel di upload YouTube.
3. Sumber tak terdaftar (mis. `radityadika`) memakai namanya sendiri, **tidak
   lagi** meminjam metadata global. Ini yang membuat video Radityadika
   berlabel JKT48.
4. `youtube._description()` tidak lagi menulis `clip["topic"]` (label internal
   seperti "salah sambung lucu") ke deskripsi publik.
5. `pipeline.longcut_source()` menyimpan span `(min(start), max(end))`, bukan
   `(spans[0][0], spans[-1][1])`. Urutan spans mengikuti skor, bukan waktu,
   sehingga klip #42 tercatat `start=883.45 end=88.52` (durasi -794.9s).
   File videonya sendiri selalu benar; hanya metadata DB yang rusak.
6. `select._candidate_from_llm()` tidak lagi **memaksa** `end = start +
   min_duration` saat LLM memberi klip lebih pendek. Paksaan itu membuat 7 klip
   berhenti persis di 20.0s dengan kalimat menggantung. Sekarang klip yang
   terlalu pendek **ditolak**, bukan dipaksa.
7. `youtube.update_video()` memakai variabel `upload` yang tidak ada di
   parameternya - bug laten yang baru terpicu saat mengubah deskripsi video
   lama. Sudah dihapus, `categoryId` kini selalu dari `CATEGORY_ID`.

### Tindakan pada video lama
`data/fix_published_meta.py` + `data/fix_category.py` memperbaiki 31 video
yang sudah tayang: deskripsi/hashtag per sumber dan categoryId 22 -> 24.
Semua 31 berhasil (`ok=29`, 2 sudah 24).

### Pelajaran umum
- **Selalu verifikasi dari API, jangan dari database sendiri.** DB bilang
  "published", kenyataannya 19 masih private. Views 0 bukan berarti algoritma
  menghukum; sering berarti video belum pernah tayang.
- Metadata global untuk banyak channel adalah bug desain, bukan sekadar
  ketidaknyamanan. Hashtag/credit harus melekat pada sumber.
- Kalau sebuah fungsi menyimpan daftar hasil berbasis skor, jangan asumsikan
  urutannya kronologis. Ambil min/max eksplisit.
- Like-rate 0,2% (3 like dari 1349 views) adalah sinyal audiens salah, bukan
  sinyal konten buruk. Like-rate Shorts normal 2-5%.

## 2026-11-05 — Pipeline tanpa LLM & penjadwalan

- **Ambang skor harus mencerminkan skala penyedia.** Heuristik mentok 48-58,
  LLM 80-95. `min_score: 60` membuat pipeline menghasilkan nol klip setiap kali
  LLM mati (Gemini 503, Ollama 404). Set 45.
- **Provider `auto` berbahaya saat LLM tidak tersedia.** Setiap sumber membuang
  ~2 menit retry sebelum jatuh ke heuristik. Pakai `provider: heuristic` kalau
  LLM tidak stabil.
- **Auto-detect bahasa Whisper bisa salah total.** Video JKT48 dengan lagu
  Jepang di awal terdeteksi `ja`; seluruh transkrip jadi Jepang dan skor jatuh.
  Paksa `language: id`.
- **Cache transkrip wajib membandingkan bahasa**, bukan hanya nama model.
- **Judul dari LLM harus divalidasi, bukan dibuang.** Aturan lama mengganti
  judul LLM dengan kutipan audio mentah sehingga tayang "Baru aja sarapan, buat".
  Urutan benar: judul utuh -> caption -> payoff -> kutipan.
- **`payoff_summary` bisa keluar bahasa lain.** Instruksi "wajib Bahasa
  Indonesia" harus eksplisit untuk semua field, bukan hanya caption.
- **Satu `filter_complex` dengan 12+ cabang trim menghabiskan RAM.** Decode
  sumber berkali-kali bersamaan -> ffmpeg exit -12. Potong per segmen lalu
  gabung lewat `concat` demuxer.
- **`schedule_slot(settings, 0)` tanpa daftar slot terpakai** menjadwalkan semua
  klip di jam yang sama. Selalu kirim `future_scheduled_slots(conn)`.
- **Kuota upload per akun, bukan per channel.** `utama` kena
  `uploadLimitExceeded` setelah 9 upload; `kedua` masih bisa. Reset tengah malam
  Waktu Pasifik (~14:00 WIB).
- **Video panjang sebaiknya 1 per hari.** Tiga kompilasi 15 menit tayang
  bersamaan saling memakan impresi.

## 2026-11-05 (lanjutan) - Kualitas klip: payoff, wajah, replay

- **Klip harus memuat pemicu DAN punchline.** Contoh nyata: klip Windah mulai
  setelah "gue tau jalan keluar di mana" dan berhenti 8 detik sebelum
  "it's scam guys"; penonton tidak tahu apa yang bikin dia terkejut. Perbaikan:
  mundur satu segmen ucapan sebelum batas awal, lalu tarik ujung sampai kalimat
  selesai (maks 9 detik).
- **Urutan pelebaran batas penting**: perluas payoff dulu, sisa durasi baru
  dipakai untuk konteks. Kalau konteks diambil lebih dulu, jatah 60 detik habis
  dan punchline terpotong.
- **Kalau melebihi batas durasi, potong DARI AWAL, jangan dari ujung.**
  Memotong ujung membuang payoff; menggeser awal hanya mengurangi konteks.
- **Watermark harus menghindari wajah, bukan pojok tetap.** Facecam Windah ada
  di kanan bawah, jadi logo MKLP di kanan bawah menutupi wajahnya. Deteksi
  wajah mengembalikan (x, y); pilih sudut ASS berseberangan (7/9/1/3).
- **Data "paling sering di-replay" ada di HTML halaman watch**, bukan di Data
  API: `heatmap.markers` berisi startMillis + intensityScoreNormalized. Satu
  request HTTP, cache 24 jam. Pakai untuk (a) menaikkan skor kandidat yang
  menutup puncak replay, (b) menyemai kandidat di sekitar puncak. Tanpa
  penyemaian, momen yang diputar ulang bisa tidak pernah jadi kandidat.
- **Bonus heat wajib dipasang SEBELUM dedupe.** Kalau sesudah, kandidat puncak
  kalah dari tetangganya yang skornya sedikit lebih tinggi tapi tidak memuat
  momen yang diputar ulang.
- **Prefix nama file != id sumber.** `windah3-xxx.mp4` harus dipetakan ke
  sumber `windah`; pencocokan persis membuat hashtag/credit/kampanye jatuh ke
  metadata global channel lain (video Windah tayang dengan tag JKT48).
- **Kompilasi longform menutupi hampir seluruh sumber.** Saat mencari klip
  tambahan, baris longform harus diabaikan di cek tumpang tindih; kalau tidak,
  semua kandidat baru dianggap tumpang tindih.
- **TikTok Studio punya jadwal native** (radio Schedule + Allow + tanggal/jam),
  tapi timepicker-nya sulit diotomasi: klik DOM pada daftar jam sering
  mendarat di angka lain (18:00 jadi 18:25 / 15:00). Jalur manual lewat panel
  browser terbukti berhasil; otomasi belum stabil.
- **Akun `kedua` juga punya batas harian.** Setelah 4 upload hari ini, kuota
  habis; sisa klip harus menunggu reset.

## 2026-11-05 (review 51 video) - Hasil audit

- **Percobaan upload yang GAGAL tetap memakan kuota.** Beberapa kali
  `uploadLimitExceeded` dicoba ulang (utama, kedua, #68, #71, ganti video Windah)
  dan tiap percobaan menghabiskan jatah `Video Uploads per day` di level
  *project* Google Cloud (bukan per channel). Karena kedua channel berbagi
  project, kuota mereka satu kolam.
- **Kuota upload reset 00:00 Waktu Pasifik = 15:00 WIB**, dan jumlah efektifnya
  kecil (~4-6 upload/hari). Jangan buang percobaan upload hanya untuk mengecek.
- **Audit metadata lebih murah daripada upload.** 51 video bisa diperiksa dan
  diperbaiki (judul, tag, deskripsi) tanpa upload sama sekali — cukup
  `videos.update`.
- **Cek tumpang tindih harus mengabaikan baris longform**, dan **prefix nama
  file harus dipetakan ke id sumber**; keduanya penyebab metadata salah dan
  kandidat klip "tumpang tindih" palsu.
- **Video lama tanpa penonton aman diganti.** 7 klip Windah lama (0-1 views)
  dirender ulang; urutan aman = unggah dulu, hapus lama setelah sukses, supaya
  tidak ada video hilang kalau kuota habis di tengah jalan.
- **Watermark lama di kanan-bawah menutupi facecam Windah** (wajah di
  x≈0,87 y≈0,87). Semua render baru memakai sudut berlawanan.
