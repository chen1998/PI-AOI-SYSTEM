@echo off
cd /d D:\A0_Project\AOI_Density\models\mysql_migration
set INTERVAL=600
set LOCK_FILE=aoi_density_summary_job.lock

echo Loop update service started...

:LOOP
echo [%DATE% %TIME%] Checking update status...

:: 若 aoi_density_summary_job.bat 正在執行，等待
if exist %LOCK_FILE% (
    echo aoi_density_summary_job.bat is running, waiting...
    timeout /t 30 >nul
    goto LOOP
)

:: 執行 aoi_density_summary_job.bat（同步執行，會等它跑完）
echo Starting aoi_density_summary_job.bat...
call aoi_density_summary_job.bat

echo aoi_density_summary_job.bat finished.
echo Waiting %INTERVAL% seconds...
timeout /t %INTERVAL% >nul
goto LOOP
