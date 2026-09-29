@echo off
REM Uzaktan erisim adresinin e-postayla gelmesi icin BIR KEZ calistirilir.
REM Bu dosyaya CIFT TIKLAYIN.
REM
REM Soracaklari: gonderen e-posta, UYGULAMA PAROLASI, adresin gelecegi kutu.
REM Uygulama parolasi = saglayicinin programlar icin urettigi ozel parola
REM (Yahoo: Hesap Guvenligi > Uygulama parolasi olustur).
REM Parola bu bilgisayarda Windows sifrelemesiyle saklanir, duz metin yazilmaz.

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

%PY% scripts\eposta_ayarla.py

echo.
pause
