"""
SatQuery AI — Server Entry Point
Run: python run_server.py
Then open: http://127.0.0.1:8000
"""
import sys
import os
import webbrowser
import threading
import time

# Ensure we're running from the backend directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

HOST = "127.0.0.1"
PORT = 8000

def open_browser():
    time.sleep(2.5)
    webbrowser.open(f"http://{HOST}:{PORT}")

print("\n" + "=" * 56)
print("  SatQuery AI  —  SIH26167")
print(f"  App  : http://{HOST}:{PORT}")
print(f"  Docs : http://{HOST}:{PORT}/docs")
print("  Press Ctrl+C to stop.")
print("=" * 56 + "\n")

threading.Thread(target=open_browser, daemon=True).start()

uvicorn.run(
    "app.api.main:app",
    host=HOST,
    port=PORT,
    log_level="info",
    reload=False,
)
