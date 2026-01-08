@echo off
cd /d D:\A0_Project\AOI_Capa\models\mysql_migration
set INTERVAL=600
set LOCK_FILE=aoi300_crawler_capa_job.lock

echo Loop update service started...

:LOOP
echo [%DATE% %TIME%] Checking update status...

:: 若 aoi300_crawler_capa_job.bat 正在執行，等待
if exist %LOCK_FILE% (
    echo aoi300_crawler_capa_job.bat is running, waiting...
    timeout /t 30 >nul
    goto LOOP
)

:: 執行 aoi300_crawler_capa_job.bat（同步執行，會等它跑完）
echo Starting aoi300_crawler_capa_job.bat...
call aoi300_crawler_capa_job.bat

echo aoi300_crawler_capa_job.bat finished.
echo Waiting %INTERVAL% seconds...
timeout /t %INTERVAL% >nul
goto LOOP
