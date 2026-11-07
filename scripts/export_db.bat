@echo off
setlocal
chcp 65001 >nul
set ROOT=%~dp0..
set OUTDIR=%ROOT%\dist\db
if not exist "%OUTDIR%" mkdir "%OUTDIR%"

set HOST=%DB_HOST%
if "%HOST%"=="" set HOST=127.0.0.1
set PORT=%DB_PORT%
if "%PORT%"=="" set PORT=3306
set USER=%DB_USER%
if "%USER%"=="" set USER=root
set PASS=%DB_PASSWORD%
if "%PASS%"=="" set PASS=Fqh112233!
set DB=%DB_NAME%
if "%DB%"=="" set DB=complaint_analysis

set DUMP=mysqldump
where mysqldump >nul 2>nul
if errorlevel 1 (
  if exist "C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe" (
    set "DUMP=C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"
  ) else (
    echo [失败] 未找到 mysqldump，请安装 MySQL 客户端或加入 PATH
    exit /b 1
  )
)

for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set TODAY=%%d
set OUT=%OUTDIR%\%DB%_%TODAY%.sql
echo [信息] 导出 %DB% -^> %OUT%
"%DUMP%" -h %HOST% -P %PORT% -u %USER% -p%PASS% --single-transaction --routines --triggers --default-character-set=utf8mb4 --databases %DB% > "%OUT%" 2>"%OUTDIR%\export.err"
if errorlevel 1 ( type "%OUTDIR%\export.err" & echo [失败] 导出失败 & exit /b 1 )
echo [成功] 导出完成: %OUT%
endlocal
