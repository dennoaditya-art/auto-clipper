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
