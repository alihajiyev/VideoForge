@echo off
cd /d "%~dp0\.."
chcp 65001 >nul
title Video Temizleyici (ProPainter)
python temizle.py
