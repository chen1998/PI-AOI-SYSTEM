@echo off
cd /d D:\A0_Project\AOI_Capa\models\mysql_migration

:: 建立鎖定檔
set LOCK_FILE=aoi300_crawler_capa_job.lock
echo running > %LOCK_FILE%

call ..\..\..\.venv\Scripts\activate
python aoi_summary_aoi300_capa_crawler.py
python aoi_capa.py --mode today 

:: 移除鎖定檔
del %LOCK_FILE%
