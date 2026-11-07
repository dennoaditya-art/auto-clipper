# SDD ledger — plan: docs/superpowers/plans/2026-11-06-roblox-tiktok-shorts.md

Ruling (setup): eksekusi langsung di D:\clipper master, tanpa worktree — pipeline
berjalan dari path absolut ini (venv, storage, config) dan seluruh riwayat repo
memang direct-to-master. Biaya kalau salah: tidak ada isolasi, revert harus
manual per commit.

Ruling (setup): fixture `settings_factory` di plan tidak ada. Semua test memakai
fixture `settings` yang sudah ada + `dataclasses.replace`. Biaya kalau salah:
test lebih verbose, perilaku sama.

Task 1: complete (commit 1d021db, pytest -q -> 65 passed)
Task 2: complete (pytest -q -> 67 passed)
Ruling (Task 2): batas payoff memakai hasil snap_to_speech, bukan timestamp
mentah — perpanjangan kalimat masih bagian punchline. Biaya kalau salah: ekor
bisa lebih 1-2 detik dari 8.
Task 3: complete (pytest -q -> 68 passed)
Task 4: complete (pytest -q -> 72 passed)
Ruling (Task 4): `_letterbox_filter` memakai tinggi eksplisit (608/810), bukan
`scale=1080:-2`, supaya padding tidak pernah ganjil. Biaya kalau salah: tidak ada.
Task 5: complete (pytest -q -> 73 passed)
Task 6: complete (pytest -q -> 75 passed)
Task 7: complete (pytest -q -> 76 passed)
Ruling (Task 7): hashtag di test tidak boleh di-hardcode `#windahbasudara` — nilainya
datang dari campaign/sumber, dan fixture test tidak punya sumber Windah. Test
memeriksa bentuk caption, bukan isi hashtag. Biaya kalau salah: hashtag salah
tidak tertangkap test ini (tetap tertangkap test_source_meta).
Task 8: complete (pytest -q -> 78 passed)
Ruling (Task 8): batas "maks 2 per jam" dijamin oleh daftar slot (satu slot per
jam), bukan pengecekan terpisah. Biaya kalau salah: kalau nanti slot dirapatkan,
batasnya tidak ditegakkan kode.
Task 9: complete (pytest -q -> 81 passed)
Ruling (Task 9): parser mencari baris tanggal, caption = baris sebelumnya kecuali
baris itu durasi, views = angka pertama sesudah privacy. Biaya kalau salah:
caption multi-baris hanya terbaca baris terakhir.
Review: letterbox ditaruh di tengah (240 salah: memakai lebar, bukan tinggi);
publish_approved & CLI sekarang memfilter slot per platform.
Bug (produksi): `filters.append("ass=sub.ass")` hilang sejak b9ba7ce sehingga
semua klip 3-6 Nov tayang tanpa subtitle karaoke. Sudah dikembalikan + test
regresi. Varian TikTok juga menimpa file Shorts (nama sama) — sekarang berakhiran
`_tt`. 6 post TikTok 7-8 Nov dihapus dari Studio, dirender ulang, dijadwalkan
ulang dengan file bersubtitle.
Tindak lanjut: 9 post lama 11-13 Nov (render crop-fill tanpa subtitle) juga
dihapus; 9 klip dirender ulang sebagai letterbox bersubtitle dan dijadwalkan
ulang 8-9 Nov. Total 15 post terjadwal 7-9 Nov. Alat: data/tiktok_delete.py,
data/rerender_tt.py.
Bug: retry task (`publish_approved`) mengunggah klip campaign TikTok-only ke
YouTube (kuota harian 10 video habis untuk konten yang bukan haknya). Guard
campaign dipindah ke Settings.campaign_for_media + dipakai publish_approved;
test baru di tests/test_publish.py.
Verifikasi: 15/15 post TikTok 7-9 Nov ada di Studio (1 baris masing-masing).
Alat baru: data/tiktok_verify.py (cocokkan caption lewat kotak pencarian),
data/tiktok_list.py. Catatan: pencarian Studio gagal kalau kata kunci memuat
emoji - emoji dibuang sebelum mencari.
Bukti tayang: baris Studio yang masih terjadwal punya ikon jam di label tanggal;
tanpa ikon = sudah tayang. Per 7 Nov 15:30 clip 72 tayang, 14 sisanya terjadwal.
Task `autoclip-replace-windah` tidak jalan 7 Nov (PC tidur saat 15:10, LastRun
tetap 6 Nov). StartWhenAvailable diaktifkan. Kuota kanal YouTube masih penuh
pukul 15:13 WIB (limit tampak rolling 24 jam, bukan reset tengah malam PT), jadi
penggantian 7 video dijalankan lewat loop data\replace_retry.log tiap 30 menit
sampai data\replace_windah.done muncul.
Baseline TikTok 7 Nov 15:30 WIB: 4 pengikut, 17 mengikuti, 52 suka, 4 video
publik. Pembanding: akun referensi 1.436 / 224 / 410 pengikut.

Akar masalah jangkauan (analisis 7 Nov malam):
1. Marka heatmap YouTube = 100 bucket 1% durasi video (~50 detik), bukan momen
   persis. Kode lama memakai awal bucket -4 detik lalu memotong 45-60 detik,
   jadi sub-jendela diambil acak dan banyak jeda mati.
2. _shape_bounds melakukan backfill 15 detik tanpa syarat setiap masih ada sisa
   durasi, sehingga klip bisa dibuka 20-30 detik jeda mati. Bukti: #72 bicara
   26% (jeda 10.5 detik), #74 21% (jeda 31.8 detik), #75 27% (jeda 32.4 detik),
   #70 hook 3 detik pertama 0.0 detik bicara.
3. Sumber basi: windah3 = satu video tetap (sQS6zVkqYGA) yang sudah dipanen 21
   kali; windah hanya latest 1 tanpa fallback. Kanal Windah punya 786 video,
   pool 15 terbaru berisi 5.3M/2.8M/1.7M/1.6M/1.5M tayangan.
Perbaikan (commit 9877d88, e7ff9bc):
- _densest_window: pilih kluster kata terpadat di dalam bucket (+margin 5s).
- backfill konteks maksimal 2s; lompatan jeda >2s saat mengejar durasi minimum
  dilarang; kandidat dengan kepadatan bicara <35% dibuang.
- bonus kata kunci fokus tidak lagi tertimpa bonus replay (+=).
- popular_recent: pilih views tertinggi dari 15 video terbaru kanal (<=90 menit),
  bukan video tetap; focus.sources kini hanya windah.
- Tes: 88 passed. Diverifikasi pada transkrip sumber 11: 3 kandidat baru dengan
  bicara 36-62%, bukan 21-27%.
Catatan operasional: unduhan windah-2kfmi_U2sVI (1.6M tayangan, 60 menit)
sedang berjalan; setelah selesai pipeline memakai pemilihan baru.

Tindak lanjut 7 Nov 18:20-18:35:
- Pratinjau sumber 8 (windah-JFax1qrU_ow, 1.7M tayangan, 60 menit, baru 4 klip):
  pemilihan baru menghasilkan 3 kandidat dengan bicara 74%/80%/70%.
- resqueeze 8 -> klip #78/#79/#80, hook 3 detik = 2.8/2.5/1.9 detik bicara;
  TikTok terjadwal 9 Nov 19:30/21:00/22:00 (video asli baru 6 hari, populer).
- Klip lama #68-#71 (60 detik, hook buruk) dihapus dari Studio; publikasi DB
  ditandai deleted agar slot bebas. Verifikasi Studio: 72/73 tayang, 74-77,
  47-51, 78-80 terjadwal, tanpa masalah.
- Unduhan video terbaru 2kfmi_U2sVI (1.6M, 60 menit) terhambat throttle YouTube
  ~35 KB/s setelah ~130 MB. Loop resume 24x tiap 15 menit berjalan di background
  (data\download_2kfmi.log, resolusi 720p agar cepat). Ini batas jaringan/IP,
  bukan bug kode.
