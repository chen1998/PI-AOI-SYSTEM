@echo off
setlocal

cd /d "%~dp0"

if not exist api_log mkdir api_log

echo ============================================================ >> api_log\api_job.bat.log
echo [%date% %time%] api_job.bat started >> api_log\api_job.bat.log
echo WorkingDir=%cd% >> api_log\api_job.bat.log

call ..\.venv\Scripts\activate

echo [%date% %time%] venv activated >> api_log\api_job.bat.log

REM ============================================================
REM FastAPI 後端啟動
REM workers=4 代表啟動 4 個後端 process 處理多人請求
REM ============================================================
python -m uvicorn main:app --host 0.0.0.0 --port 8104 --workers 2 --no-access-log

echo [%date% %time%] uvicorn exited with ERRORLEVEL=%ERRORLEVEL% >> api_log\api_job.bat.log
echo ============================================================ >> api_log\api_job.bat.log

pause
endlocal

