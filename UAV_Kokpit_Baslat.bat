@echo off
title UAV-VRAG Kokpit Baslatici
echo ========================================================
echo UAV-VRAG Kokpit Sistemi Baslatiliyor...
echo Lutfen bekleyin...
echo ========================================================
echo.

echo [1/3] Arka Plan Yapay Zeka (YOLO, VRAG, VLM, LLM) Servisleri Baslatiliyor...
start "UAV-VRAG Yapay Zeka Sunuculari" cmd /c "cd /d %~dp0beratinyo\backend && python main.py"

echo [2/3] Servislerin hazir olmasi bekleniyor (4 Saniye)...
timeout /t 4 /nobreak >nul

echo [3/3] Kokpit Masaustu Uygulamasi Aciliyor...
start "" "%~dp0beratinyo\kokpit\Kokpit\bin\Debug\net10.0-windows\VRAG-Kokpit.exe"

exit
