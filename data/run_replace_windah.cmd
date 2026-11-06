@echo off
cd /d D:\clipper
set PYTHONPATH=D:\clipper
set PYTHONIOENCODING=utf-8
rem 1) klip yang belum pernah tayang (kuota habis kemarin)
.venv\Scripts\python.exe -m autoclip publish 71 --platform youtube --account utama --schedule
rem 2) ganti 7 video Windah lama dengan render baru
.venv\Scripts\python.exe data\replace_windah.py
