@echo off
REM DeepCortex kisayollarini kurar. Bu dosyaya CIFT TIKLAYIN (bir kez yeter).
REM
REM   - Masaustu + Baslat menusu: "DeepCortex" ikonu
REM   - Chrome yer imi icin "deepcortex:" baglanti turu (acilan sayfadaki
REM     dugmeyi yer imleri cubuguna surukleyin)
REM
REM Ikona ya da yer imine basinca: program kapaliysa baslar (veri guncellenir),
REM aciksa ikinci kopya acmadan pencereyi getirir.
REM Kaldirmak icin:  KISAYOL_OLUSTUR.bat /kaldir
REM Baska bir bilgisayara tasidiktan sonra orada bir kez yeniden calistirin.

cd /d "%~dp0"

set PY=
where python >nul 2>nul && set PY=python
if not defined PY where py >nul 2>nul && set PY=py
if not defined PY (
    echo.
    echo   HATA: Bu bilgisayarda Python bulunamadi.
    echo.
    pause
    exit /b 1
)

if /i "%~1"=="/kaldir" (
    %PY% scripts\kisayol.py kaldir
) else (
    %PY% scripts\kisayol.py kur
)
echo.
pause
