@echo off
cd /d D:\A0_Project\AOI_Defect_map\
call ..\.venv\Scripts\activate
REM python main.py
python -m http.server 8200
pause