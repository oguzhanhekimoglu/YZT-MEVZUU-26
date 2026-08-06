@echo off
title UAV-VRAG Sistem Baslatici
echo ========================================================
echo UAV-VRAG Sistemi Baslatiliyor...
echo Lutfen bekleyin...
echo ========================================================
echo.

echo [1/2] Arka Plan Yapay Zeka (YOLO, VRAG, VLM, LLM) Servisleri Baslatiliyor...
start "UAV-VRAG Yapay Zeka Sunuculari" cmd /c "cd /d %~dp0entegrasyon\backend && ..\..\LLM\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo [2/2] Servislerin hazir olmasi bekleniyor (10 Saniye)...
timeout /t 10 /nobreak >nul

echo Web arayuzu taraycida aciliyor...
start "" "http://127.0.0.1:8000/goruntule/"

exit
