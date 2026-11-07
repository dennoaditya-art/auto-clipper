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
