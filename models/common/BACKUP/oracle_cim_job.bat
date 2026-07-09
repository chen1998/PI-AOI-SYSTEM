@echo off
setlocal

cd /d D:\A0_Project\PI_SYSTEM\models\common

REM  指向真正含有 oci.dll 的資料夾
set "ORACLE_IC=D:\A0_Project\oracle\product\11.2.0\client_1\_instantclient-basic-windows.x64-11.2.0.4.0\instantclient_11_2"
set "PATH=%ORACLE_IC%;%PATH%"

REM  啟用 venv
call "D:\A0_Project\.venv\Scripts\activate"

REM  驗證：排程環境是否找得到 oci.dll + Oracle client version
where python
where oci.dll
python -c "import cx_Oracle as o; import sys; print('exe=',sys.executable); print('cx_Oracle=',o.__version__); print('client=',o.clientversion())"

REM 0) 執行一次
python RUN_CIM_PULL_10MIN.py --once --lookback-min 1440

REM =========================================================
REM 1). defect_map_phase1
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\piaoi\defect_map_overlay

REM ===== RTMS 網路分享設定 =====
set SHARE=\\10.97.136.13\rtms
set RTMS_USER=fpd
set RTMS_PWD=fpd

REM ===== 先清掉舊連線，避免憑證衝突 =====
net use %SHARE% /delete /y >nul 2>&1

REM ===== 建立網路連線 =====
net use %SHARE% /user:%RTMS_USER% %RTMS_PWD%
if errorlevel 1 (
    echo [ERROR] net use 失敗，無法連線到 %SHARE%
    goto :CLEAN
)

REM ===== 執行 Python rtms jobs =====
python rtms_aoi300_raw_job.py --once --lookback-min 1440 --source-dir %SHARE%
::if errorlevel 1 goto :JOBERR

python build_rtms_aoi300_glass_job.py --once --lookback-min 1440
if errorlevel 1 goto :JOBERR

REM ===== 執行  API jobs =====
python build_api_summary_from_cim_defect_aoi12_job.py --once --lookback-min 1440
if errorlevel 1 goto :JOBERR

python build_api_summary_from_rtms_aoi300_job.py --once --lookback-min 1440
if errorlevel 1 goto :JOBERR

echo [INFO] all jobs done.
goto :CLEAN

:JOBERR
echo [ERROR] 某支 Python job 執行失敗

:CLEAN
net use %SHARE% /delete /y >nul 2>&1



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

REM =========================================================
REM 4. build_bpi_density_phase2 --bpi
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


endlocal

::pause