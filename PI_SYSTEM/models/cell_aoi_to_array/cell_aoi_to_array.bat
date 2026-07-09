@echo off
setlocal

REM  指向真正含有 oci.dll 的資料夾
set "ORACLE_IC=D:\A0_Project\oracle\product\11.2.0\client_1\_instantclient-basic-windows.x64-11.2.0.4.0\instantclient_11_2"
set "PATH=%ORACLE_IC%;%PATH%"

REM  啟用 venv
call "D:\A0_Project\.venv\Scripts\activate"

REM  驗證：排程環境是否找得到 oci.dll + Oracle client version
where python
where oci.dll
python -c "import cx_Oracle as o; import sys; print('exe=',sys.executable); print('cx_Oracle=',o.__version__); print('client=',o.clientversion())"


REM =========================================================
REM 6. build_bpi_density_phase2 --bpi density
REM =========================================================
cd /d D:\A0_Project\PI_SYSTEM\models\cell_aoi_to_array\aoi

python RUN_CELL_INCOMING_GOVERNANCE_V5.py --once --lookback-hour 4

cd /d D:\A0_Project\PI_SYSTEM\models\cell_aoi_to_array\inspec
python RUN_CELL_INSPECTION_INCOMING_GOVERNANCE.py --once --lookback-hour 4



endlocal

pause