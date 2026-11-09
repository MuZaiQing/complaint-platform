@echo off
setlocal
chcp 65001 >nul
title 投诉分析平台-启动
set ROOT=%~dp0..
set BACKEND=%ROOT%\backend
set LOGDIR=%BACKEND%\logs
set PIDFILE=%LOGDIR%\app.pid
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

set PY=
if exist "D:\ruan_jain_an_zhuang\python-3.13.7\python.exe" set "PY=D:\ruan_jain_an_zhuang\python-3.13.7\python.exe"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( echo [失败] 未找到 Python，请安装 Python 3.11+ & exit /b 1 )

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul && ( echo [失败] 8000 端口已被占用，请先运行 stop.bat & exit /b 1 )

"%PY%" -c "import fastapi,pymysql,uvicorn" 2>nul || ( echo [失败] 依赖缺失，请执行: "%PY%" -m pip install -r "%BACKEND%\requirements.txt" & exit /b 1 )

REM ---------- MySQL 检查：未运行则尝试启动 MySQL80 ----------
netstat -ano | findstr /R /C:":3306 .*LISTENING" >nul && goto mysql_ok
echo [信息] MySQL 未运行，尝试启动 MySQL80 服务...
sc query MySQL80 >nul 2>&1 || ( echo [失败] 未找到 MySQL80 服务，请先运行 install_mysql.bat & exit /b 1 )
net start MySQL80 >nul 2>&1
netstat -ano | findstr /R /C:":3306 .*LISTENING" >nul && goto mysql_ok
echo [信息] 需要管理员权限，请在弹窗中点「是」授权启动 MySQL80
powershell -NoProfile -Command "Start-Process -FilePath 'net.exe' -ArgumentList 'start','MySQL80' -Verb RunAs -Wait -WindowStyle Hidden" >nul 2>&1
set M=0
:mysql_wait
netstat -ano | findstr /R /C:":3306 .*LISTENING" >nul && goto mysql_ok
set /a M+=1
if %M% GEQ 15 ( echo [失败] MySQL 15 秒未就绪，请手动启动 MySQL80 服务后重试 & exit /b 1 )
ping -n 2 127.0.0.1 >nul
goto mysql_wait
:mysql_ok

cd /d "%BACKEND%"
echo [信息] 启动中，日志: %LOGDIR%\app.log
start "" /b "%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8000 >>"%LOGDIR%\app.log" 2>&1

set N=0
:wait
curl -fsS -m 2 http://127.0.0.1:8000/docs >nul 2>&1 && goto ready
set /a N+=1
if %N% GEQ 30 ( echo [失败] 30 秒未就绪，查看 %LOGDIR%\app.log & exit /b 1 )
ping -n 2 127.0.0.1 >nul
goto wait
:ready
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":8000 .*LISTENING"') do echo %%p>"%PIDFILE%"
echo [成功] 平台已启动: http://127.0.0.1:8000 （PID 已记录到 %PIDFILE%）
endlocal
