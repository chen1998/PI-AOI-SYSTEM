@echo off
cd /d "%~dp0"
call ..\.venv\Scripts\activate
python -m http.server 8204
pause
