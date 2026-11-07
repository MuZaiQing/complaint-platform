@echo off
chcp 65001 >nul
setlocal DisableDelayedExpansion
REM ============================================================
REM 投诉分析平台 - 裸机安装 MySQL 8（Windows）
REM
REM 用法（必须以管理员身份运行）:
REM   scripts\install_mysql.bat [密码] [库名]
REM   scripts\install_mysql.bat                     使用默认 Fqh112233! / complaint_analysis
REM
REM 做的事: 检测/安装 MySQL 8 -> 启动服务 -> 设置 root 密码 -> 建库
REM 完成后执行: scripts\import_db.bat
REM ============================================================

set "DBPASS=%~1"
if not defined DBPASS set "DBPASS=Fqh112233!"
set "DBNAME=%~2"
if not defined DBNAME set "DBNAME=complaint_analysis"

net session >nul 2>&1
if errorlevel 1 (
  echo [失败] 需要管理员权限，请右键本文件选择“以管理员身份运行”
  exit /b 1
)

REM 密码会拼进 SQL 单引号字符串，禁止破坏语法的字符
set "CHK=%DBPASS:'=%"
if not "%CHK%"=="%DBPASS%" (
  echo [失败] 密码不能包含单引号
  exit /b 1
)
set "CHK=%DBPASS:\=%"
if not "%CHK%"=="%DBPASS%" (
  echo [失败] 密码不能包含反斜杠
  exit /b 1
)

echo [信息] 目标库: %DBNAME%

REM ---------- 1. 定位 mysql 与服务 ----------
set "MYSQL="
where mysql >nul 2>&1 && set "MYSQL=mysql"
if not defined MYSQL (
  for %%D in ("C:\Program Files\MySQL\MySQL Server 8.0" "C:\Program Files\MySQL\MySQL Server 8.4" "C:\Program Files\MySQL\MySQL Server 8.1") do (
    if exist "%%~D\bin\mysql.exe" set "MYSQL=%%~D\bin\mysql.exe"
  )
)

set "SVC="
sc query MySQL80 >nul 2>&1 && set "SVC=MySQL80"
if not defined SVC (
  sc query MySQL84 >nul 2>&1 && set "SVC=MySQL84"
)
if not defined SVC (
  sc query MySQL81 >nul 2>&1 && set "SVC=MySQL81"
)

if not defined MYSQL (
  if not defined SVC (
    echo [信息] 未检测到 MySQL，尝试用 winget 安装 Oracle.MySQL
    where winget >nul 2>&1
    if errorlevel 1 (
      echo [失败] 系统无 winget，无法自动安装
      echo        请手动安装 MySQL 8.0: https://dev.mysql.com/downloads/installer/
      echo        安装后重新运行本脚本即可完成建库与密码配置
      exit /b 1
    )
    winget install --id Oracle.MySQL -e --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
      echo [失败] winget 安装失败，请手动安装 MySQL 8.0 后重跑
      exit /b 1
    )
    echo [信息] 等待安装完成并注册服务...
    for /l %%i in (1,1,60) do (
      if not defined MYSQL (
        where mysql >nul 2>&1 && set "MYSQL=mysql"
      )
      if not defined SVC (
        sc query MySQL80 >nul 2>&1 && set "SVC=MySQL80"
      )
      if not defined MYSQL (
        for %%D in ("C:\Program Files\MySQL\MySQL Server 8.0" "C:\Program Files\MySQL\MySQL Server 8.4") do (
          if exist "%%~D\bin\mysql.exe" set "MYSQL=%%~D\bin\mysql.exe"
        )
      )
      if not defined MYSQL timeout /t 2 >nul
    )
  )
)

if not defined MYSQL (
  echo [失败] 找不到 mysql.exe，请确认安装路径或把 bin 目录加入 PATH
  exit /b 1
)

REM ---------- 2. 启动服务 ----------
if defined SVC (
  sc query "%SVC%" | findstr /i "RUNNING" >nul 2>&1
  if errorlevel 1 (
    echo [信息] 启动服务 %SVC%
    net start "%SVC%" >nul 2>&1
  )
)

echo [信息] 等待 MySQL 就绪...
set "READY="
for /l %%i in (1,1,30) do (
  if not defined READY (
    "%MYSQL%" -uroot --connect-timeout=3 -e "SELECT 1" >nul 2>&1 && set "READY=1"
    if not defined READY timeout /t 2 >nul
  )
)

REM ---------- 3. 登录并配置 ----------
set "AUTH=-uroot"
"%MYSQL%" %AUTH% --connect-timeout=5 -e "SELECT 1" >nul 2>&1
if not errorlevel 1 goto haveauth

echo [信息] root 空密码不可用，需要现有密码
set /p "EXISTPASS=请输入当前 root 密码（回车=空）: "
if defined EXISTPASS set "AUTH=-uroot -p"%EXISTPASS%""
"%MYSQL%" %AUTH% --connect-timeout=5 -e "SELECT 1" >nul 2>&1
if errorlevel 1 (
  echo [失败] 无法登录 root，请先手动确认密码或重置
  exit /b 1
)
:haveauth

"%MYSQL%" %AUTH% -N -B -e "SELECT VERSION()" 2>nul
if errorlevel 1 (
  echo [失败] 读取 MySQL 版本失败
  exit /b 1
)

set "SQLFILE=%TEMP%\fqh_mysql_init.sql"
> "%SQLFILE%" (
  echo ALTER USER 'root'@'localhost' IDENTIFIED WITH caching_sha2_password BY '%DBPASS%';
  echo CREATE DATABASE IF NOT EXISTS `%DBNAME%` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
)
"%MYSQL%" %AUTH% --connect-timeout=5 < "%SQLFILE%"
if errorlevel 1 (
  del "%SQLFILE%" >nul 2>&1
  echo [失败] 设置密码或建库失败
  exit /b 1
)
del "%SQLFILE%" >nul 2>&1

REM ---------- 4. 验证 ----------
"%MYSQL%" -uroot -p"%DBPASS%" --connect-timeout=5 -e "SHOW DATABASES LIKE '%DBNAME%';" >nul 2>&1
if errorlevel 1 (
  echo [失败] 新密码验证失败
  exit /b 1
)

echo [成功] MySQL 已安装并配置完成（root 密码与 backend\.env 中的 DB_PASSWORD 保持一致）
echo [信息] 下一步: scripts\import_db.bat
exit /b 0
