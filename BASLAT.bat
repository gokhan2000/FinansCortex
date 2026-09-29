@echo off
REM DeepCortex Finans arayuzunu baslatir.
REM Bu dosyaya CIFT TIKLAYIN. Python yorumlayicisina (>>>) yazmayin.
REM Hangi bilgisayarda calistirilirsa calistirilsin, Python'u PATH
REM uzerinden kendiliginden bulur - sabit bir klasor yolu ARAMAZ.
REM
REM Arayuz acilmadan ONCE veriler guncellenir; yoksa ekranda eski
REM fiyatlar gorunur (veritabanini kimse kendiliginden tazelemez).
REM Guncellemeyi atlamak icin:  BASLAT.bat /hizli
REM /uygulama: masaustu ikonu / Chrome yer imi (scripts\ac.py) boyle cagirir;
REM Streamlit ayrica tarayici sekmesi ACMAZ, pencereyi ac.py acar.

cd /d "%~dp0"

set HIZLI=
set EKSTRA=
if /i "%~1"=="/hizli" set HIZLI=1
if /i "%~2"=="/hizli" set HIZLI=1
if /i "%~1"=="/uygulama" set EKSTRA=--server.headless true
if /i "%~2"=="/uygulama" set EKSTRA=--server.headless true
title DeepCortex

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

REM Program zaten aciksa ikinci kopyayi ACMA. Windows ayni porta iki kopyanin
REM oturmasina izin verebiliyor; tarayici eski kopyaya baglanir ve eski kod
REM calisir (21.09.2026'da tam olarak bu oldu: "no attribute global_css").
netstat -ano | findstr /r /c:":8503 .*LISTENING" >nul
if not errorlevel 1 (
    echo.
    echo   Program ZATEN ACIK ^(8503^).
    echo   Once acik olan programin penceresini kapatin,
    echo   sonra BASLAT.bat'a yeniden cift tiklayin.
    echo   ^(Tarayicida zaten aciksa: http://localhost:8503^)
    echo.
    pause
    exit /b 1
)

if defined HIZLI goto arayuz

echo.
echo   Veriler guncelleniyor... (ilk seferde uzun surebilir)
echo   Atlamak icin bu pencerede Ctrl+C yapin.
echo.
%PY% scripts\backfill.py --sure 150

:arayuz
echo.
echo   DeepCortex Finans baslatiliyor...
echo   Tarayici birazdan kendiliginden acilacak.
echo   Kapatmak icin bu pencerede Ctrl+C yapin ya da pencereyi kapatin.
echo.
%PY% -m streamlit run app.py --server.port 8503 --browser.gatherUsageStats false %EKSTRA%

echo.
echo   Arayuz kapandi.
pause
