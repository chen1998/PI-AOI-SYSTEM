@echo off
setlocal

cd /d D:\A0_Project\PI_SYSTEM\models\common\common_code

call "D:\A0_Project\.venv\Scripts\activate"

if not exist logs mkdir logs
python mail_alert.py --combined-mail >> logs\mail_alert_task.log 2>&1

::exit /b %ERRORLEVEL%
pause