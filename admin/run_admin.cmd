@echo off
REM BilibiliDownloader Release Download Stats - Admin Backend Launcher
REM Double-click to start, then open http://127.0.0.1:8765/ in your browser.
REM Press Ctrl+C in this window to stop.

cd /d "%~dp0.."
python admin\server.py --port 8765 --interval 60
pause
