@echo off
setlocal

cd /d D:\A0_Project\PI_SYSTEM\models\defect_map_overlay

call ..\..\..\.venv\Scripts\activate

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
    goto :END
)

REM ===== 執行 Python jobs =====
::python build_api_summary_from_cim_defect_aoi12_job.py --once --lookback-min 1440
python build_api_summary_from_cim_defect_aoi12_job.py --once --lookback-min 1440
if errorlevel 1 goto :JOBERR

::python rtms_aoi300_raw_job.py --once --lookback-min 1440 --source-dir %SHARE%
::if errorlevel 1 goto :JOBERR

::python build_rtms_aoi300_glass_job.py --once --lookback-min 1440
if errorlevel 1 goto :JOBERR

python build_api_summary_from_rtms_aoi300_job.py --once --lookback-min 1440
if errorlevel 1 goto :JOBERR

echo [INFO] all jobs done.
goto :CLEAN

:JOBERR
echo [ERROR] 某支 Python job 執行失敗

:CLEAN
net use %SHARE% /delete /y >nul 2>&1

:END
endlocal

::pause
