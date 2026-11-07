@echo off
chcp 65001 >nul
setlocal
REM 一键入库（Windows）：把 db\*.sql 导入 MySQL
REM 用法: scripts\import_db.bat [--file db\complaint_analysis.sql] [--password xxx]

set "PYEXE="
set "PYARGS="
if exist "D:\ruan_jain_an_zhuang\python-3.13.7\python.exe" set "PYEXE=D:\ruan_jain_an_zhuang\python-3.13.7\python.exe"
if not defined PYEXE (
  where py >nul 2>&1 && set "PYEXE=py"
)
if defined PYEXE if "%PYEXE%"=="py" set "PYARGS=-3"
if not defined PYEXE (
  where python >nul 2>&1 && set "PYEXE=python"
)
if not defined PYEXE (
  echo [失败] 未找到 Python，请安装 Python 3.8+ 并加入 PATH
  exit /b 1
)

"%PYEXE%" %PYARGS% "%~dp0import_db.py" %*
exit /b %errorlevel%
