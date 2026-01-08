@echo off
setlocal

REM === 工作目錄 ===
cd /d D:\A0_Project\AOI_Density\models\mysql_migration
call ..\..\..\.venv\Scripts\activate

REM === 日誌資料夾（如無則建立） ===
set LOG_DIR=D:\A0_Project\AOI_Density\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

REM === 參數：即時窗（抓 pi_hour >= 現在 - 60 分鐘） ===
set LIVE_WINDOW_MIN=60

REM === 智慧回補掃描：從彙總已入庫的最大 pi_hour 往前回補 360 分鐘（6 小時）===
REM 若你已把「智慧回補掃描」那段合進腳本，這個參數就會生效；沒合進去也不影響執行。
set CUSHION_MIN=360

REM === 其他（可選） ===
set PYTHONUTF8=1
set SUMMARY_PREFIX=pidenisty_pihour

REM 指定 Python 路徑（請改成你機器上的 Python）
set PYTHON_EXE=C:\Python312\python.exe

REM 讓 Python 腳本也把日誌寫到這個檔名（腳本有讀 LOG_FILE 的邏輯）
set LOG_FILE=%LOG_DIR%\pihour_job.log

REM === 執行 ===
"%PYTHON_EXE%" pidenisty_pihour_job.py  >> "%LOG_DIR%\pihour_job.stdout.log" 2>&1
REM （可選）回傳碼檢查
if errorlevel 1 (
  echo [%date% %time%] Job failed with errorlevel %errorlevel% >> "%LOG_DIR%\pihour_job.runner.log"
) else (
  echo [%date% %time%] Job finished OK >> "%LOG_DIR%\pihour_job.runner.log"
)

endlocal