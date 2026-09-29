@echo off
REM DeepCortex Finans projesinin yedegini alir.
REM Bu dosyaya CIFT TIKLAYIN.
REM
REM Proje git kullanmadigi icin kod ve belgelerin TEK kopyasi bu klasorde.
REM Bu dosya onlari tarihli bir klasore kopyalar:
REM     G:\My Drive\DeepCortex-Yedek\2026-09-21_1930\
REM Google Drive yoksa OneDrive'a, o da yoksa bu klasorun bir ustune
REM (DeepCortex-Yedek) yazar.
REM
REM KOPYALANMAYANLAR (bilerek):
REM   data\      ~200 MB veritabani - Dukascopy'den yeniden indirilebilir
REM              (python scripts\backfill.py, ~23 dakika)
REM   araclar\   cloudflared.exe (55 MB) - gerekince kendiliginden iner
REM   __pycache__, ADRES.txt, *.log - gecici dosyalar
REM
REM Geri yuklemek: yedek klasorunun icindekileri proje klasorune kopyalayin.

cd /d "%~dp0"

set HEDEF_KOK=
if exist "G:\My Drive\" set "HEDEF_KOK=G:\My Drive\DeepCortex-Yedek"
if not defined HEDEF_KOK if defined OneDrive if exist "%OneDrive%\" set "HEDEF_KOK=%OneDrive%\DeepCortex-Yedek"
if not defined HEDEF_KOK set "HEDEF_KOK=%~dp0..\DeepCortex-Yedek"

for /f %%t in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set ZAMAN=%%t
set "HEDEF=%HEDEF_KOK%\%ZAMAN%"

echo.
echo   Yedek aliniyor...
echo   Hedef: %HEDEF%
echo.

robocopy "%~dp0." "%HEDEF%" /E /XD data araclar __pycache__ .venv /XF ADRES.txt *.log /NFL /NDL /NJH /NP /R:1 /W:1

REM robocopy: 0-7 basari, 8 ve ustu hata
if errorlevel 8 (
    echo.
    echo   HATA: Yedek tamamlanamadi. Yukaridaki mesaja bakin.
    echo.
    pause
    exit /b 1
)

echo.
echo   Yedek tamam: %HEDEF%
echo.
pause
