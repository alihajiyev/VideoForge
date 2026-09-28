@echo off
cd /d "%~dp0\.."
title VideoForge - Bot Kontrol Paneli
color 0B
echo =======================================================
echo       VIDEOFORGE - YOUTUBE TEMIZLEYICI ^& SESLENDIRICI
echo =======================================================
echo.
echo Kanal secimi:
echo   1 - Kino Sekrety (Film Sirlari)
echo   2 - Fakt Za 15 (Ilginc Bilgiler)
echo   3 - PopkornFakty (Film Hikayeleri - Rus Anlatim)
echo.
set /p CHANNEL="Secim (1/2/3): "
if "%CHANNEL%"=="" set CHANNEL=1
echo.
set /p YOUTUBE_LINK="Youtube linkini buraya yapistir ve Enter'a bas: "
echo.

if "%CHANNEL%"=="1" goto ch1
if "%CHANNEL%"=="2" goto ch2
if "%CHANNEL%"=="3" goto ch3
echo Gecersiz secim!
goto end

:ch1
    echo ^>^> Kino Sekrety kanali icin video isleniyor...
    echo.
    echo =======================================================
    echo [!] Motor atesleniyor, lutfen pencereyi kapatma...
    echo =======================================================
    echo.
    python -m modal run kinosekrety.py --link "%YOUTUBE_LINK%"
    goto end

:ch2
    echo ^>^> Fakt Za 15 kanali icin video isleniyor...
    echo.
    echo =======================================================
    echo [!] Motor atesleniyor, lutfen pencereyi kapatma...
    echo.
    python -m modal run faktza15.py --link "%YOUTUBE_LINK%"
    goto end

:ch3
    echo ^>^> PopkornFakty kanali icin video isleniyor...
    echo.
    echo =======================================================
    echo [!] Motor atesleniyor, lutfen pencereyi kapatma...
    echo 3. kanal: Soru cumlesi yasak, sinematik anlatici mod, transcript'e sadik
    echo.
    python -m modal run kinok_syjet.py --link "%YOUTUBE_LINK%"
    goto end

:end

echo.
echo =======================================================
echo Islem tamamlandi! Temizlenen video Masaustunde.
echo Cikmak icin herhangi bir tusa bas.
pause >nul