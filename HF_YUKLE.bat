@echo off
REM Programi ve veriyi Hugging Face'e (ozel Space) yukler. CIFT TIKLAYIN.
REM Once uygulamayi (BASLAT) KAPATIN: veri dosyasi yazilirken kopyalanmasin.
REM Yalniz kodu yenilemek icin:  HF_YUKLE.bat kod
cd /d "%~dp0"
title DeepCortex - Hugging Face yukleme
python -m pip install -q huggingface_hub
python scripts\hf_yukle.py %1
echo.
pause
