@echo off
setlocal EnableDelayedExpansion

REM =========================================================
REM Oracle Instant Client
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\common

set "ORACLE_IC=D:\A0_Project\oracle\product\11.2.0\client_1\_instantclient-basic-windows.x64-11.2.0.4.0\instantclient_11_2"
set "PATH=%ORACLE_IC%;%PATH%"

REM =========================================================
REM 啟用 Python venv
REM =========================================================
call "D:\A0_Project\.venv\Scripts\activate"

REM =========================================================
REM 驗證 Oracle client
REM =========================================================
where python
where oci.dll

python -c "import cx_Oracle as o; import sys; print('exe=',sys.executable); print('cx_Oracle=',o.__version__); print('client=',o.clientversion())"

REM =========================================================
REM 動態日期計算
REM 若今天是 2026-05-07
REM START_DATE = 2026-04-30
REM END_DATE   = 2026-05-07
REM =========================================================

for /f %%i in ('powershell -NoProfile -Command "(Get-Date).AddDays(-7).ToString('yyyy-MM-dd')"') do set START_DATE=%%i
for /f %%i in ('powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd')"') do set END_DATE=%%i

REM BPI Density 時間格式
set START_DATETIME=%START_DATE% 07:30:00
set END_DATETIME=%END_DATE% 08:00:00

echo.
echo =========================================================
echo START_DATE = %START_DATE%
echo END_DATE   = %END_DATE%
echo =========================================================
echo.

REM =========================================================
REM 1. repair_cim_pi_glass_trans_job
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\common\common_code

python repair_cim_pi_glass_trans_job.py --once --recent-days 7 --dry-run

if errorlevel 1 (
    echo [ERROR] repair_cim_pi_glass_trans_job failed
    pause
    exit /b 1
)

REM =========================================================
REM 2. build_capa_glass_table_job
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\piaoi\capa

python build_capa_glass_table_job.py ^
    --mode range ^
    --start %START_DATE% ^
    --end %END_DATE%

if errorlevel 1 (
    echo [ERROR] build_capa_glass_table_job failed
    pause
    exit /b 1
)

REM =========================================================
REM 3. build_capa_hourly_summary_job
REM =========================================================
python build_capa_hourly_summary_job.py ^
    --mode range ^
    --start %START_DATE% ^
    --end %END_DATE%

if errorlevel 1 (
    echo [ERROR] build_capa_hourly_summary_job failed
    pause
    exit /b 1
)


REM =========================================================
REM 4. aoi-density cim_density_job
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\piaoi\density

python cim_density_job.py --mode days  --days 7 --write_out


if errorlevel 1 (
    echo [ERROR] build_cim_density_job.py
    pause
    exit /b 1
)


echo.
echo =========================================================
echo ALL JOBS COMPLETED SUCCESSFULLY
echo =========================================================

endlocal
::pause