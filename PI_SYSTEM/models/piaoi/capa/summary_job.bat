@echo off
cd /d D:\A0_Project\PI_SYSTEM\models\capa


call ..\..\..\.venv\Scripts\activate
::python build_capa_glass_table_job.py --mode lookback --lookback-min 1440
python build_capa_glass_table_job.py --mode lookback --lookback-min 1440
python build_capa_hourly_summary_job.py --mode lookback --lookback-min 1440


