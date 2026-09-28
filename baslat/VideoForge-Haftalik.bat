@echo off
title VideoForge Haftalik - Kanal Sec + Tam Otomatik Zincir
color 0A
cd /d "%~dp0\.."
echo =======================================================
echo   VIDEOFORGE HAFTALIK MODU
echo   Adim 1: Kesif 7 video bulur (skor sirasi = gun sirasi)
echo   Adim 2: VideoForge temizler + SEO + ses (Gun klasorleri)
echo   Adim 3: ShortsStudio montaj yapar (final_*.mp4 Masaustune)
echo =======================================================
echo.
echo   KANAL SECIMI
echo   1) Kino Sekrety - Film
echo   2) Fakt Za 15 - Ilginc Bilgiler
echo   3) PopkornFakty - Film Hikayeleri
echo.
:kanal_sec
set CHN=
set /p CHN="Kanal seciniz (1-3): "
set CHN=%CHN: =%
if "%CHN%"=="" set CHN=1
if not "%CHN%"=="1" if not "%CHN%"=="2" if not "%CHN%"=="3" (
  echo Gecersiz secim, lutfen 1-3 arasi girin.
  goto kanal_sec
)
echo.
echo Secilen kanal: %CHN% - zincir basliyor, baska soru yok.
echo.
if exist haftalik_plan.json del haftalik_plan.json
python kesif.py --haftalik --chn %CHN% --evet
echo.
if not exist haftalik_plan.json (
  echo [X] Plan olusmadi - kesif sonuc uretemedi, yukaridaki hataya bak.
  goto son
)
python haftalik_islet.py --evet
:son
echo.
echo =======================================================
echo [V] ISLEM BITTI. Finaller Masaustunde.
echo =======================================================
echo.
pause
