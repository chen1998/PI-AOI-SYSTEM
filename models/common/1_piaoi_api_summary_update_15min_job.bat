@echo off
setlocal

REM  啟用 venv
call "D:\A0_Project\.venv\Scripts\activate"


REM =========================================================
REM 1). defect_map_phase1
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\piaoi\defect_map_overlay

REM ===== 執行  API jobs =====
python build_api_summary_from_cim_defect_aoi12_job.py --once --lookback-min 1440
if errorlevel 1 goto :JOBERR

python build_api_summary_from_rtms_aoi300_job.py --once --lookback-min 1440
if errorlevel 1 goto :JOBERR


REM =========================================================
REM 2). aoi-density
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\piaoi\density
python cim_density_job.py --mode days  --days 1 --write_out

REM =========================================================
REM 3. aoi-capa
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\piaoi\capa
python build_capa_glass_table_job.py --mode lookback --lookback-min 1440
python build_capa_hourly_summary_job.py --mode lookback --lookback-min 1440


endlocal

::pause