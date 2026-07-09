@echo off
setlocal

cd /d D:\A0_Project\PI_SYSTEM\models\bpi_density

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

python build_bpi_density_job.py --once --lookback-min 1440
python build_bpi_same_point_job.py --once --lookback-min 1440
:END
endlocal
