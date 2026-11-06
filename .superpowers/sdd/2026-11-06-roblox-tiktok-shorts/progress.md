# SDD ledger — plan: docs/superpowers/plans/2026-11-06-roblox-tiktok-shorts.md

Ruling (setup): eksekusi langsung di D:\clipper master, tanpa worktree — pipeline
berjalan dari path absolut ini (venv, storage, config) dan seluruh riwayat repo
memang direct-to-master. Biaya kalau salah: tidak ada isolasi, revert harus
manual per commit.

Ruling (setup): fixture `settings_factory` di plan tidak ada. Semua test memakai
fixture `settings` yang sudah ada + `dataclasses.replace`. Biaya kalau salah:
test lebih verbose, perilaku sama.
