@echo off
setlocal

cd /d D:\A0_Project\PI_SYSTEM\models\common\common_code

REM  指向真正含有 oci.dll 的資料夾
set "ORACLE_IC=D:\A0_Project\oracle\product\11.2.0\client_1\_instantclient-basic-windows.x64-11.2.0.4.0\instantclient_11_2"
set "PATH=%ORACLE_IC%;%PATH%"

REM  啟用 venv
call "D:\A0_Project\.venv\Scripts\activate"

REM  驗證：排程環境是否找得到 oci.dll + Oracle client version
where python
where oci.dll
python -c "import cx_Oracle as o; import sys; print('exe=',sys.executable); print('cx_Oracle=',o.__version__); print('client=',o.clientversion())"

REM 0) 執行一次
python RUN_CIM_PULL_10MIN.py --once --lookback-min 1440

endlocal

::pause