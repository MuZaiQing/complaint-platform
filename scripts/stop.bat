@echo off
setlocal
chcp 65001 >nul
set ROOT=%~dp0..
set PIDFILE=%ROOT%\backend\logs\app.pid
if exist "%PIDFILE%" (
  set /p PID=<"%PIDFILE%"
  taskkill /PID %PID% /T /F >nul 2>&1 && echo [成功] 已停止 PID=%PID%
  del "%PIDFILE%" >nul 2>&1
) else (
  echo [信息] 无 PID 文件，按端口查找...
)
for /f %%p in ('powershell -NoProfile -Command "(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue).OwningProcess | Select-Object -First 1"') do (
  taskkill /PID %%p /T /F >nul 2>&1 && echo [成功] 已按端口停止 PID=%%p
)
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul && ( echo [失败] 8000 仍在监听 & exit /b 1 ) || echo [完成] 服务已停止
endlocal
