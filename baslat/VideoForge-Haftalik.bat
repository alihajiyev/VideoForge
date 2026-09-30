@echo off
title VideoForge Cok Gunlu Plan - Kanal Sec + Tam Otomatik Zincir
color 0A
cd /d "%~dp0\.."
echo =======================================================
echo   VIDEOFORGE COK GUNLU PLAN MODU
echo   Adim 1: Kesif, sectiginiz sayida videoyu bulur (skor sirasi = gun sirasi)
echo   Adim 2: VideoForge temizler + SEO + ses uretir (GunN klasorleri)
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
echo   KAC GUNLUK PLAN?
echo   7 yazarsaniz 7 video, 10 yazarsaniz 10 video uretilir (2-60 arasi).
echo.
:gun_sec
set "GUN="
set /p "GUN=Gun sayisi (Enter = 7): "
rem Bos cevap (sadece Enter) -> varsayilan 7. Once 'defined' kontrolu sart:
rem tanimsiz degiskende %GUN: =% ifadesi cozulmez ve dongu kilitlenirdi.
if not defined GUN set "GUN=7"
set "GUN=%GUN: =%"
if "%GUN%"=="" set "GUN=7"
set "GS=0"
set /a GS=GUN 2>nul
if not "%GS%"=="%GUN%" (
  echo Gecersiz sayi, lutfen 2-60 arasi bir sayi girin.
  goto gun_sec
)
if %GS% LSS 2 (
  echo En az 2 gun gerekir.
  goto gun_sec
)
if %GS% GTR 60 (
  echo En fazla 60 gun secilebilir.
  goto gun_sec
)
set "GUN=%GS%"
echo.
echo Secilen kanal: %CHN% - %GUN% gunluk plan. Zincir basliyor, baska soru yok.
echo.
if "%VIDEOFORGE_TEST%"=="1" (
  echo [TEST] python kesif.py --haftalik %GUN% --chn %CHN% --evet
  echo [TEST] python haftalik_islet.py --evet
  goto son
)
if exist haftalik_plan.json del haftalik_plan.json
python kesif.py --haftalik %GUN% --chn %CHN% --evet
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
