@echo off
cd /d D:\A0_Project\AOI_Density\models\mysql_migration

:: 建立鎖定檔
set LOCK_FILE=aoi_density_summary_job.lock
echo running > %LOCK_FILE%

call ..\..\..\.venv\Scripts\activate
python aoi_density_summary_job.py
python pidenisty_pihour_job.py

:: 移除鎖定檔
del %LOCK_FILE%
