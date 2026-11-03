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
