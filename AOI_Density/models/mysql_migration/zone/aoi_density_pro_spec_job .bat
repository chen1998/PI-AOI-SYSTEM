@echo off
cd /d D:\A0_Project\AOI_Density\models\mysql_migration
call ..\..\..\.venv\Scripts\activate
python aoi_density_pro_spec_update.py
pause