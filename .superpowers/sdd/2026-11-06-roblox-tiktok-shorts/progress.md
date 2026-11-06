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
