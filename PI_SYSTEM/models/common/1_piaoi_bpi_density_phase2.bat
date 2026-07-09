@echo off
setlocal

REM  啟用 venv
call "D:\A0_Project\.venv\Scripts\activate"


REM =========================================================
REM 4. build_bpi_density_phase2 --bpi density
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\piaoi\bpi_density

python build_bpi_density_job.py  --mode days --days 3 --write-out

if errorlevel 1 (
    echo [ERROR] build_bpi_api_summary_job failed
    ::pause
    exit /b 1
)


REM =========================================================
REM 5). build_bpi_density_phase2  --同點
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\piaoi\bpi_density

python build_bpi_same_point_job.py --mode days --days 3 --write-out

if errorlevel 1 (
    echo [ERROR] build_bpi_same_point_job failed
    ::pause
    exit /b 1
)

REM =========================================================
REM 2). aoi-density
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\piaoi\density

python build_density_recipe_same_point_job.py --mode days --days 1 --write-out


endlocal

::pause