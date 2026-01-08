@echo off
cd /d D:\A0_Project\\AOI_Inspection\models\mysql_migration

:: 建立鎖定檔
set LOCK_FILE=inspection_datamall.lock
echo running > %LOCK_FILE%

call ..\..\..\.venv\Scripts\activate
python inspection_datamall.py

:: 移除鎖定檔
del %LOCK_FILE%