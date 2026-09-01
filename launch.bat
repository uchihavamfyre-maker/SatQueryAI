@echo off
title SatQuery AI
cd /d "%~dp0backend"
echo.
echo  SatQuery AI  --  http://127.0.0.1:8000
echo  Press Ctrl+C to stop.
echo.
python run_server.py
pause
