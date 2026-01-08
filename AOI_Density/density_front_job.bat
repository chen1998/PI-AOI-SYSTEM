@echo off
cd /d D:\A0_Project\AOI_Density\
call ..\.venv\Scripts\activate
python -m http.server 8201
pause