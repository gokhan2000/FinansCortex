@echo off
REM Veritabanini bulut icin kucuk dosyalara (bulut_veri\) cevirir. CIFT TIKLAYIN.
REM Uygulamayi kapatin. Sonra Claude'a "GitHub'a gonder" deyin.
cd /d "%~dp0"
python scripts\bulut_veri_yaz.py
echo.
pause
