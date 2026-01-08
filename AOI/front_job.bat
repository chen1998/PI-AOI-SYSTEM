@echo off
cd /d D:\A0_Project\AOI\
call ..\.venv\Scripts\activate
python -m http.server 8203
pause