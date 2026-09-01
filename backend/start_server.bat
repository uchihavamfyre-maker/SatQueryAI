@echo off
cd /d %~dp0
echo Starting SatQuery AI backend...
echo API will be available at http://localhost:8000
echo Docs at http://localhost:8000/docs
echo Press Ctrl+C to stop.
echo.
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --log-level info
pause
