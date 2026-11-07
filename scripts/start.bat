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

cd /d "%BACKEND%"
echo [信息] 启动中，日志: %LOGDIR%\app.log
start "" /b "%PY%" -m uvicorn main:app --host 0.0.0.0 --port 8000 >>"%LOGDIR%\app.log" 2>&1

set N=0
:wait
curl -fsS -m 2 http://127.0.0.1:8000/docs >nul 2>&1 && goto ready
set /a N+=1
if %N% GEQ 30 ( echo [失败] 30 秒未就绪，查看 %LOGDIR%\app.log & exit /b 1 )
timeout /t 1 /nobreak >nul
goto wait
:ready
for /f %%p in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess | Select-Object -First 1"') do echo %%p>"%PIDFILE%"
echo [成功] 平台已启动: http://127.0.0.1:8000 （PID 已记录到 %PIDFILE%）
endlocal
