@echo off
title Veri-Byte Forensic Document Inspector (SIH26188)
echo =====================================================================
echo   VERI-BYTE FORENSIC DOCUMENT INSPECTOR
echo   AI-Based Fake Identity & Document Screening System
echo   FastAPI + React Architecture
echo =====================================================================

set "PATH=C:\Users\ASHMIT\nodejs;%PATH%"

echo [1/3] Checking Python Virtual Environment...
if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo [2/3] Checking Frontend Production Build...
if not exist "%~dp0frontend\dist\index.html" (
    echo Frontend build not found. Compiling React bundle...
    pushd "%~dp0frontend"
    call npm run build
    popd
)

echo [3/3] Starting Veri-Byte Server on http://127.0.0.1:8000 ...
echo - Frontend UI: http://127.0.0.1:8000
echo - API Documentation: http://127.0.0.1:8000/docs
echo.
cd /d "%~dp0backend"
"%PYTHON_EXE%" server.py
pause
