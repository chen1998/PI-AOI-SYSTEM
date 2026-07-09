@echo off
cd /d D:\A0_Project\PI_SYSTEM\
call ..\.venv\Scripts\activate
python -m http.server 8204
pause