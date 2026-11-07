@echo off
chcp 65001 >nul
set PY=
if exist "D:\ruan_jain_an_zhuang\python-3.13.7\python.exe" set "PY=D:\ruan_jain_an_zhuang\python-3.13.7\python.exe"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( echo [ ß∞‹] Œ¥’“µΩ Python & exit /b 1 )
"%PY%" "%~dp0import_db.py" %*
