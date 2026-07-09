@echo off
setlocal

REM  啟用 venv
call "D:\A0_Project\.venv\Scripts\activate"

REM =========================================================
REM 1). defect_map_phase1-rtms
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



endlocal

::pause