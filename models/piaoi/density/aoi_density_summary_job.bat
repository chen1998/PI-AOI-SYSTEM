@echo off
cd /d D:\A0_Project\PI_SYSTEM\models\density


call ..\..\..\.venv\Scripts\activate
::python cim_density_job.py --mode days --days 1 --write_out
python cim_density_job.py --mode days  --days 1 --write_out


