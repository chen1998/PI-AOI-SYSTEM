@echo off
cd /d D:\A0_Project\PI_SYSTEM\models\inspection_density


call ..\..\..\.venv\Scripts\activate
::python cim_density_job.py --mode days --days 1 --write_out
::python inspection_density_datamall_job.py job
python inspection_density_datamall_job.py pull-landing
python inspection_density_datamall_job.py rebuild-hours --hours 3
