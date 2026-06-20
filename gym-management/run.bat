@echo off
cd /d "%~dp0"
start http://localhost:1926
python app.py
pause
