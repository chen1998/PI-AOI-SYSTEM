@echo off
cd /d D:\A0_Project\\AOI_Inspection\models\mysql_migration
set INTERVAL=600
set LOCK_FILE=inspection_datamall.lock

echo Loop update service started...

:LOOP
echo [%DATE% %TIME%] Checking update status...

:: 若 inspection_datamall.bat 正在執行，等待
if exist %LOCK_FILE% (
    echo inspection_datamall.bat is running, waiting...
    timeout /t 30 >nul
    goto LOOP
)

:: 執行 inspection_datamall.bat（同步執行，會等它跑完）
echo Starting inspection_datamall.bat...
call inspection_datamall.bat

echo inspection_datamall.bat finished.
echo Waiting %INTERVAL% seconds...
timeout /t %INTERVAL% >nul
goto LOOP
