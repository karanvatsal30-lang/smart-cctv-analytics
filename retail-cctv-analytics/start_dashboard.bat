@echo off
title Retail CCTV Analytics Server
cd /d "%~dp0"

echo ======================================================================
echo   Starting Software-Only Retail CCTV Analytics Server...
echo ======================================================================
echo.
echo Launching Python backend server...
echo The dashboard will automatically open in your browser at:
echo http://127.0.0.1:5000
echo.
python run.py
pause
