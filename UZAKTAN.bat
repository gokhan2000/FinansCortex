@echo off
REM DeepCortex Finans'i INTERNETTEN erisilebilir hale getirir.
REM Bu dosyaya CIFT TIKLAYIN. Python yorumlayicisina (>>>) yazmayin.
REM
REM Kod ve veritabani BU BILGISAYARDA kalir; disariya yalnizca calisan
REM arayuzun ekrani acilir ve onunde parola vardir.
REM Ilk calistirmada: parola sorulur + tunel araci indirilir (~50 MB).
REM Veri guncellemesini atlamak icin:  UZAKTAN.bat /hizli

cd /d "%~dp0"

set PY=
where python >nul 2>nul && set PY=python
if not defined PY where py >nul 2>nul && set PY=py

if not defined PY (
    echo.
    echo   HATA: Bu bilgisayarda Python bulunamadi.
    echo   Once Python 3.12 kurulmali, sonra bu klasorde:
    echo       pip install -r requirements.txt
    echo   calistirilmalidir.
    echo.
    pause
    exit /b 1
)

if /i "%~1"=="/hizli" goto uzaktan

echo.
echo   Veriler guncelleniyor... (atlamak icin: UZAKTAN.bat /hizli)
echo.
%PY% scripts\backfill.py --sure 150

:uzaktan
%PY% scripts\uzaktan.py

echo.
pause
