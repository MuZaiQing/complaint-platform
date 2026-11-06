# 项目整理归类与一键交付实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 目录归类（data/、mr/、archive/）+ 路径同步 + 数据库一键导出入库 + 双平台启停脚本 + git 快照，backend 逻辑零改动。

**Architecture:** 同盘 Move-Item 秒级迁移 16GB 数据；仅改路径常量默认值；脚本全部放 scripts/；库仅 2MB，导出为纯 .sql。

**Tech Stack:** PowerShell(Move-Item)、Python 3.13（`D:\ruan_jain_an_zhuang\python-3.13.7\python.exe`）、bat/bash、mysqldump/mysql 客户端、git。

**关键事实：**
- DB 配置在 `backend/db_meta.py`：env 优先，默认 `127.0.0.1:3306 root / Fqh112233! / complaint_analysis`，库总大小仅约 2MB，10 张表
- `main.py:28` `DATA_ROOT = os.getenv("DATA_ROOT", r"D:\fqh")`
- `main.py:637` glob `DATA_ROOT/CCDB_Export_*.csv`（缺 CCDB 子目录，现为死分支因 pkl 存在；本次顺手修正为 `CCDB/CCDB_Export_*.csv`）
- `cluster.py:29` `JAR_LOCAL_DIR = Path(os.getenv("JAR_DIR", r"D:\fqh\jar包"))`
- `train_cfpb_text_model.py:18` `DATA_DIR = r'D:\fqh\CCDB'`
- `backend/.env:7` `JAR_DIR=D:\fqh\jar包`（.env 无 DATA_ROOT 行）
- 当前 8000 端口服务运行中，Task 3 完成后需重启
- 执行顺序必须按 Task 编号；Task 2 迁移前 8000 服务无需停（懒加载尚未触发或已缓存内存，迁移后重启才读新路径）。**保险起见 Task 2 前先停 8000 服务，Task 4 再启动**

---

### Task 1: git init + .gitignore + 整理前基线 commit

**Files:**
- Create: `d:\fqh\.gitignore`

- [ ] **Step 1: 写 .gitignore**

```
# 数据与交付物（不进版本库）
data/
dist/
archive/
CCDB/
mr_result/
*.csv
*.pkl
.screenshots/

# 敏感与运行产物
backend/.env
backend/logs/
backend/.cluster_logs/
__pycache__/
*.log
```

注意 `backend/*.csv` 也会被 `*.csv` 排除——backend 下无 csv 业务文件（验证过：`clean_validation_report.csv` 在根目录），安全。

- [ ] **Step 2: git init + 基线 commit**

```powershell
cd D:\fqh
git init
git add -A
git commit -m "chore: 目录整理前基线快照"
```

预期：commit 含 backend/、example/、jar包/（jar 较小约 0.4MB，可入库）、Dockerfile、docker-compose.yml、docs/ 等；不含大 csv/pkl。

- [ ] **Step 3: 验证**

Run: `git log --oneline` 与 `git status`
Expected: 1 个 commit；status 干净（未跟踪的只剩被 ignore 的）

---

### Task 2: 停服务 + 目录迁移

**Files:**
- Create: `d:\fqh\data\`、`d:\fqh\mr\`、`d:\fqh\archive\`（脚本自动建）

- [ ] **Step 1: 停 8000 服务**

```powershell
Get-NetTCPConnection -LocalPort 8000 -State Listen | Select-Object -Expand OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
```

验证：`Get-NetTCPConnection -LocalPort 8000 -State Listen` 无输出。

- [ ] **Step 2: 迁移（单条 PowerShell，全部 Move-Item，同盘秒级）**

```powershell
cd D:\fqh
New-Item -ItemType Directory -Force data, mr, archive | Out-Null
# 大数据 → data/
Move-Item complaints_clean.csv, complaints_clean.pkl, ccdb_text.pkl, fcc_consumer_complaints_clean.csv, fcc_consumer_complaints_clean.pkl -Destination data\
Move-Item CCDB -Destination data\CCDB
Move-Item mr_result -Destination data\mr_result
# MR → mr/
Move-Item jar包 -Destination mr\jar包
Move-Item example -Destination mr\src
# 杂项 → archive/
Move-Item debug.log, ai.txt, clean_validation_report.csv, 项目描述.txt -Destination archive\
Move-Item .screenshots -Destination archive\screenshots
```

- [ ] **Step 3: 验证迁移结果**

```powershell
Get-ChildItem D:\fqh -Force | Select-Object Name
Get-ChildItem D:\fqh\data, D:\fqh\mr\jar包, D:\fqh\mr\src, D:\fqh\archive | Select-Object Name
```

预期：根目录只剩 backend/data/mr/archive/dist/docs/scripts(未建)/.superpowers/.git + Docker 三文件 + .gitignore；data/ 含 5 大文件 + CCDB/ + mr_result/；mr/jar包 10 个 jar；mr/src 10 个 java；archive/ 4 文件 + screenshots/。

抽查：`Get-ChildItem D:\fqh\data\CCDB | Measure-Object | Select Count` = 17；`Test-Path D:\fqh\data\mr_result\fcc_wordfreq_top100.txt` = True。

---

### Task 3: 路径引用同步（仅常量默认值）

**Files:**
- Modify: `d:\fqh\backend\main.py:28, 637`
- Modify: `d:\fqh\backend\cluster.py:29`
- Modify: `d:\fqh\backend\train_cfpb_text_model.py:18`
- Modify: `d:\fqh\backend\.env:7`
- Modify: `d:\fqh\backend\.env.example:9`
- Modify: `d:\fqh\docker-compose.yml`（volumes）
- Modify: `d:\fqh\.dockerignore`
- Modify: `d:\fqh\Dockerfile`（注释）

- [ ] **Step 1: backend 代码 3 处**

`main.py:28`：
```python
DATA_ROOT = os.getenv("DATA_ROOT", r"D:\fqh\data")
```

`main.py:637`：
```python
for fp in sorted(glob.glob(os.path.join(DATA_ROOT, "CCDB", "CCDB_Export_*.csv"))):
```

`cluster.py:29`：
```python
JAR_LOCAL_DIR = Path(os.getenv("JAR_DIR", r"D:\fqh\mr\jar包"))
```

`train_cfpb_text_model.py:18`：
```python
DATA_DIR = r'D:\fqh\data\CCDB'
```

- [ ] **Step 2: 配置文件 4 处**

`backend/.env:7` 与 `backend/.env.example:9`：
```
JAR_DIR=D:\fqh\mr\jar包
```

`.env.example` 增补一行 DATA_ROOT 说明（在 JAR_DIR 行上方）：
```
# 大数据目录（ complaints_clean/CCDB/mr_result 所在目录 ）
DATA_ROOT=D:\fqh\data
```

`docker-compose.yml` volumes：
```yaml
    volumes:
      # 大数据集（CSV/PKL/mr_result）不进镜像，运行时只读挂载
      - ./data:/data:ro
      # 集群任务 jar 包，运行/体检时需要本地副本
      - ./mr/jar包:/jars:ro
```

`.dockerignore`：
```
data/
archive/
*.csv
*.pkl
mr_result/
.screenshots/
.superpowers/
__pycache__/
*.log
dist/
```

`Dockerfile` 注释行 `-v "$PWD:/data:ro"` 改为 `-v "$PWD/data:/data:ro"`（仅注释，无行为变化）。

- [ ] **Step 3: 残留扫描**

Run: `Grep "D:\\fqh\\(jar包|CCDB|example)"` 于 backend/ 与根目录配置
Expected: 无命中（train 脚本注释里的描述可顺手同步，非必须）

- [ ] **Step 4: commit**

```powershell
cd D:\fqh; git add -A; git commit -m "refactor: 目录整理 data/mr/archive 并同步路径引用"
```

---

### Task 4: 重启 + 全量回归

**Files:** 无新增

- [ ] **Step 1: 单测**

Run: `D:\ruan_jain_an_zhuang\python-3.13.7\python.exe -m pytest D:\fqh\backend\tests -q`
Expected: 31+20 全 OK

- [ ] **Step 2: 启动 8000**

```powershell
cd D:\fqh\backend
Start-Process -WindowStyle Hidden -FilePath "D:\ruan_jain_an_zhuang\python-3.13.7\python.exe" -ArgumentList "-m","uvicorn","main:app","--host","0.0.0.0","--port","8000" -WorkingDirectory "D:\fqh\backend"
```

等 8 秒后：`curl http://127.0.0.1:8000/docs -UseBasicParsing | Select StatusCode` = 200。

- [ ] **Step 3: 接口冒烟**

```powershell
curl "http://127.0.0.1:8000/api/wordcloud/fcc" -UseBasicParsing   # 验证 data/mr_result 读取
curl "http://127.0.0.1:8000/api/query/status" -UseBasicParsing     # 懒加载状态接口（如存在）
curl "http://127.0.0.1:8000/api/cluster/jobs" -UseBasicParsing     # 集群任务列表
```

（接口路径以 main.py 实际路由为准，执行时先 grep `@app.get` 取 3 个代表性接口：大屏统计、词云 fcc 文件、集群任务）

- [ ] **Step 4: 集群 preflight 抽查 2 个任务**

```powershell
curl -X POST http://127.0.0.1:8000/api/cluster/jobs/timely_response/preflight -UseBasicParsing
curl -X POST http://127.0.0.1:8000/api/cluster/jobs/company_count/preflight -UseBasicParsing
```

预期：ok=true，main_class 来自 manifest（验证 mr/jar包 新路径生效）。

- [ ] **Step 5: 浏览器回归大屏各 tab**（browser 子代理：6 个页面 tab + 集群控制台三按钮/可视化）

---

### Task 5: 启停脚本（4 个）

**Files:**
- Create: `d:\fqh\scripts\start.bat`
- Create: `d:\fqh\scripts\stop.bat`
- Create: `d:\fqh\scripts\start.sh`
- Create: `d:\fqh\scripts\stop.sh`

- [ ] **Step 1: start.bat**

```bat
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
if not defined PY ( echo [失败] 未找到 Python，请安装或设置 PY 环境变量 & exit /b 1 )

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
echo [成功] 平台已启动: http://127.0.0.1:8000  PID=%PIDFILE% 已记录
endlocal
```

- [ ] **Step 2: stop.bat**

```bat
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
```

- [ ] **Step 3: start.sh**

```bash
#!/usr/bin/env bash
# 投诉分析平台启动（Linux）
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
LOGDIR="$BACKEND/logs"
PIDFILE="$LOGDIR/app.pid"
mkdir -p "$LOGDIR"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "[失败] 未找到 python3，可设 PYTHON 环境变量"; exit 1; }
"$PY" -c "import fastapi,pymysql,uvicorn" 2>/dev/null || { echo "[失败] 依赖缺失: $PY -m pip install -r $BACKEND/requirements.txt"; exit 1; }
curl -fsS -m 2 http://127.0.0.1:8000/docs >/dev/null 2>&1 && { echo "[失败] 8000 已在运行"; exit 1; }

cd "$BACKEND" || exit 1
echo "[信息] 启动中，日志: $LOGDIR/app.log"
nohup "$PY" -m uvicorn main:app --host 0.0.0.0 --port 8000 >>"$LOGDIR/app.log" 2>&1 &
echo $! >"$PIDFILE"

for i in $(seq 1 30); do
  curl -fsS -m 2 http://127.0.0.1:8000/docs >/dev/null 2>&1 && { echo "[成功] 平台已启动: http://127.0.0.1:8000 PID=$(cat "$PIDFILE")"; exit 0; }
  sleep 1
done
echo "[失败] 30 秒未就绪，查看 $LOGDIR/app.log"; exit 1
```

- [ ] **Step 4: stop.sh**

```bash
#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIDFILE="$ROOT/backend/logs/app.pid"
stopped=0
if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  kill "$PID" 2>/dev/null && { echo "[成功] 已停止 PID=$PID"; stopped=1; }
  rm -f "$PIDFILE"
fi
if [ "$stopped" = "0" ]; then
  PIDS="$(lsof -ti:8000 2>/dev/null || true)"
  [ -n "$PIDS" ] && { kill $PIDS 2>/dev/null && echo "[成功] 已按端口停止 $PIDS"; stopped=1; }
fi
[ "$stopped" = "0" ] && echo "[信息] 8000 无运行中的服务"
exit 0
```

- [ ] **Step 5: 本机实测一轮**

先停当前 8000（Task 4 启动的），然后：
```powershell
D:\fqh\scripts\start.bat    # 预期 [成功]
D:\fqh\scripts\stop.bat     # 预期 [完成] 服务已停止
D:\fqh\scripts\start.bat    # 再启动供后续任务使用
```
`start.sh/stop.sh` 做人工语法核对（本机无 bash 环境可 `bash -n` 的话则跑）。

- [ ] **Step 6: commit** `git add scripts; git commit -m "feat: 双平台启停脚本"`

---

### Task 6: 数据库导出/入库脚本 + 实测

**Files:**
- Create: `d:\fqh\scripts\export_db.bat`
- Create: `d:\fqh\scripts\export_db.sh`
- Create: `d:\fqh\scripts\import_db.py`
- Create: `d:\fqh\scripts\import_db.bat`
- Create: `d:\fqh\scripts\import_db.sh`

- [ ] **Step 1: export_db.bat**

```bat
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
where mysqldump >nul 2>nul || set "DUMP=C:\Program Files\MySQL\MySQL Server 8.0\bin\mysqldump.exe"
if not exist "%DUMP%" ( where mysqldump >nul 2>nul || ( echo [失败] 未找到 mysqldump，请安装 MySQL 客户端或加入 PATH & exit /b 1 ) )

for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set TODAY=%%d
set OUT=%OUTDIR%\%DB%_%TODAY%.sql
echo [信息] 导出 %DB% → %OUT%
"%DUMP%" -h %HOST% -P %PORT% -u %USER% -p%PASS% --single-transaction --routines --triggers --default-character-set=utf8mb4 --databases %DB% > "%OUT%" 2>"%OUTDIR%\export.err"
if errorlevel 1 ( type "%OUTDIR%\export.err" & echo [失败] 导出失败 & exit /b 1 )
echo [成功] 导出完成: %OUT%
endlocal
```

- [ ] **Step 2: export_db.sh**

```bash
#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUTDIR="$ROOT/dist/db"
mkdir -p "$OUTDIR"
HOST="${DB_HOST:-127.0.0.1}"; PORT="${DB_PORT:-3306}"; USER="${DB_USER:-root}"
PASS="${DB_PASSWORD:-Fqh112233!}"; DB="${DB_NAME:-complaint_analysis}"
command -v mysqldump >/dev/null 2>&1 || { echo "[失败] 未找到 mysqldump"; exit 1; }
OUT="$OUTDIR/${DB}_$(date +%Y%m%d).sql"
echo "[信息] 导出 $DB → $OUT"
MYSQL_PWD="$PASS" mysqldump -h "$HOST" -P "$PORT" -u "$USER" \
  --single-transaction --routines --triggers --default-character-set=utf8mb4 \
  --databases "$DB" > "$OUT" || { echo "[失败] 导出失败"; exit 1; }
echo "[成功] 导出完成: $OUT"
```

- [ ] **Step 3: import_db.py（跨平台核心）**

```python
#!/usr/bin/env python3
"""投诉分析平台数据库一键入库（Windows/Linux 通用，Python 3.8+ 标准库）。

用法:
  python import_db.py [--file dist/db/complaint_analysis_20261107.sql]
                      [--host 127.0.0.1] [--port 3306] [--user root]
                      [--password xxx] [--db complaint_analysis]
缺省值依次取: 命令行 > 环境变量(DB_HOST 等) > 内置默认。
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
    r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
    "/usr/bin/mysql", "/usr/local/mysql/bin/mysql", "/usr/local/bin/mysql",
]


def find_mysql() -> str:
    m = shutil.which("mysql")
    if m:
        return m
    for c in CANDIDATES:
        if Path(c).exists():
            return c
    sys.exit("[失败] 未找到 mysql 客户端，请安装 MySQL Client 或加入 PATH")


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description="一键入库 complaint_analysis")
    ap.add_argument("--file", help="SQL 文件路径，缺省取 dist/db 下最新 .sql")
    ap.add_argument("--host", default=os.getenv("DB_HOST", "127.0.0.1"))
    ap.add_argument("--port", default=os.getenv("DB_PORT", "3306"))
    ap.add_argument("--user", default=os.getenv("DB_USER", "root"))
    ap.add_argument("--password", default=os.getenv("DB_PASSWORD", "Fqh112233!"))
    ap.add_argument("--db", default=os.getenv("DB_NAME", "complaint_analysis"))
    a = ap.parse_args()

    if a.file:
        sql = Path(a.file)
    else:
        files = sorted((root / "dist" / "db").glob("*.sql"), key=os.path.getmtime)
        if not files:
            sys.exit("[失败] dist/db 下没有 .sql 文件")
        sql = files[-1]
    if not sql.exists():
        sys.exit(f"[失败] 文件不存在: {sql}")

    mysql = find_mysql()
    env = dict(os.environ, MYSQL_PWD=a.password)
    base = [mysql, "-h", a.host, "-P", str(a.port), "-u", a.user,
            "--default-character-set=utf8mb4"]

    print(f"[信息] 建库 {a.db} @ {a.host}:{a.port}")
    subprocess.run(base + ["-e",
        f"CREATE DATABASE IF NOT EXISTS `{a.db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"],
        env=env, check=True)

    print(f"[信息] 导入 {sql} ...")
    with open(sql, "rb") as f:
        subprocess.run(base + [a.db], stdin=f, env=env, check=True)

    out = subprocess.run(base + ["-N", "-e",
        "SELECT table_name, table_rows FROM information_schema.tables "
        f"WHERE table_schema='{a.db}'"], env=env, check=True, capture_output=True, text=True)
    print("[成功] 入库完成，表行数：")
    print(out.stdout.strip() or "(无表)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 包装脚本**

`import_db.bat`：
```bat
@echo off
chcp 65001 >nul
set PY=
if exist "D:\ruan_jain_an_zhuang\python-3.13.7\python.exe" set "PY=D:\ruan_jain_an_zhuang\python-3.13.7\python.exe"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY ( echo [失败] 未找到 Python & exit /b 1 )
"%PY%" "%~dp0import_db.py" %*
```

`import_db.sh`：
```bash
#!/usr/bin/env bash
PY="${PYTHON:-python3}"
exec "$PY" "$(dirname "$0")/import_db.py" "$@"
```

- [ ] **Step 5: 实测导出**

Run: `D:\fqh\scripts\export_db.bat`
Expected: `dist/db/complaint_analysis_<date>.sql` 生成，含 `CREATE DATABASE` 与 10 张表

- [ ] **Step 6: 实测导入（导入到临时库验证，不覆盖现库）**

```powershell
D:\fqh\scripts\import_db.bat --db complaint_analysis_rehearsal
```

Expected: `[成功]` 且表行数与源库一致（fin_company 8069 等）。验证后：
```powershell
& D:\ruan_jain_an_zhuang\python-3.13.7\python.exe -c "import pymysql; c=pymysql.connect(host='127.0.0.1',user='root',password='Fqh112233!'); c.cursor().execute('DROP DATABASE complaint_analysis_rehearsal'); c.close()"
```

- [ ] **Step 7: commit** `git add scripts; git commit -m "feat: 数据库一键导出/入库脚本"`

---

### Task 7: 收尾 — 交付物重打包 + 最终验证

**Files:**
- Create: `d:\fqh\.env.example`（根级）
- Modify: `d:\fqh\dist\complaint-platform-src.zip`（重新生成）

- [ ] **Step 1: 根级 .env.example**（拷贝 backend/.env.example 内容，头部加一行注释 `# 复制为 backend/.env 并按需修改`）

- [ ] **Step 2: 重新打包源码 zip**

```powershell
cd D:\fqh
Compress-Archive -Path backend, mr, scripts, Dockerfile, docker-compose.yml, .dockerignore, .env.example, docs -DestinationPath dist\complaint-platform-src.zip -Force
```

排除 backend/.env、backend/logs、__pycache__：先临时用 robocopy 镜像到 %TEMP% 再压缩，或用 7z 排除；执行时选最简单可靠方式（推荐 robocopy 镜像法）。

- [ ] **Step 3: docker compose 校验（如有 Docker）**

`docker compose config` 语法通过即可，不强求 build。

- [ ] **Step 4: 最终回归清单**

- 单测 31+20 OK
- 8000 服务运行中（start.bat 启动），大屏 6 个 tab 正常，集群控制台 preflight ok
- dist/db 有当日 dump；import 演练已通过
- `git log --oneline` 4 个 commit
- 根目录结构 = spec 目标结构

- [ ] **Step 5: 最终 commit**

`git add -A; git commit -m "chore: 交付物重打包与根级 .env.example"`

---

## Self-Review

- Spec 覆盖：目录迁移(T2)、路径同步(T3)、回归(T4)、启停(T5)、数据库(T6)、git 快照(T1/T7)、dist 重打包(T7) ✅；调试残留归档在 T2 ✅；不做代码精简（spec 约定）✅
- 占位符：无 TBD；所有脚本完整给出 ✅
- 一致性：`DATA_ROOT` 默认值 `D:\fqh\data` 在 main.py/.env.example/compose 注释三处一致；`JAR_DIR` 默认值 `D:\fqh\mr\jar包` 在 cluster.py/.env/.env.example 三处一致；PID 文件路径 `backend/logs/app.pid` 四个脚本一致 ✅
- 风险：Task 2 前必须停 8000（已写入 T2 Step 1）；gzip 不需要（库 2MB）✅
