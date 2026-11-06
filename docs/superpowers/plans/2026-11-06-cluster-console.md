# 集群控制台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在大屏新增「集群控制」页，通过 SSH 驱动 Hadoop 集群（10.15.7.101 / hadoop）运行 `D:\fqh\jar包` 下 10 个 MapReduce 任务，查看状态与日志，并可选将 HDFS 结果写回本地 MySQL。

**Architecture:** 后端新增 `cluster.py`（APIRouter + paramiko SSH + ThreadPoolExecutor 任务队列 + 入库器），配置放 `cluster_jobs.json`，凭据放 `.env`；前端在既有单文件 SPA 的 `pages` 数组与页面条件块里追加一个 `cluster` 页，2s 轮询任务状态与日志。

**Tech Stack:** FastAPI / paramiko / pymysql / Vue3(CDN) / 原生 CSS

**背景文档:** `docs/superpowers/specs/2026-11-06-cluster-console-design.md`

**注意:** 项目当前不是 git 仓库（无 `.git`），因此本计划用「语法检查 / 单测 / 页面回归」代替 commit 步骤；若你后续建仓，请在每组任务后自行提交。

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `backend/db_meta.py`（新建） | 共享 `DB_CONFIG` 与 `STATS_TABLES`，避免 main.py 与 cluster.py 循环依赖 |
| `backend/cluster_jobs.json`（新建） | 10 个任务的元数据（jar、路径、目标表、列映射） |
| `backend/cluster.py`（新建） | 全部集群能力：SSH、任务队列、日志、入库、路由 |
| `backend/.env` / `.env.example`（新建） | 集群与数据库凭据 |
| `backend/tests/test_cluster.py`（新建） | 纯函数层单测（路径校验、日志解析、行解析、历史持久化） |
| `backend/requirements.txt`（修改） | 追加 paramiko、python-dotenv |
| `backend/main.py`（修改） | `load_dotenv()`、`include_router(cluster.router)`、改为从 `db_meta` 引入常量 |
| `backend/index.html`（修改） | 导航、页面模板、样式、交互逻辑 |

任务顺序：**1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9**，每步都可独立验证。

---

### Task 1: 共享元数据模块 + 依赖 + 环境变量

**Files:**
- Create: `backend/db_meta.py`
- Create: `backend/.env.example`
- Create: `backend/.env`
- Modify: `backend/main.py:20-28`、`backend/main.py:75-86`
- Modify: `backend/requirements.txt`

- [ ] **Step 1: 新建 `backend/db_meta.py`，把 main.py 里的两个常量原样搬过来**

```python
import os

# 部署时全部走环境变量，本地默认值保持开箱即用
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "Fqh112233!"),
    "db": os.getenv("DB_NAME", "complaint_analysis"),
    "charset": "utf8mb4",
}

# 大屏统计表元数据：列顺序即入库列顺序的来源
STATS_TABLES = {
    "fin_monthly":         {"label": "金融月度投诉",       "cols": ["stat_month", "complaint_count"], "sort_col": "stat_month"},
    "fin_product":         {"label": "金融产品投诉",       "cols": ["product_name", "complaint_count"], "sort_col": "complaint_count desc"},
    "fin_state":           {"label": "金融州级投诉",       "cols": ["state_code", "complaint_count"], "sort_col": "complaint_count desc"},
    "fin_timely_response": {"label": "金融及时回复",       "cols": ["response_flag", "complaint_count"]},
    "fin_company":         {"label": "金融企业投诉",       "cols": ["company_name", "complaint_count"], "sort_col": "complaint_count desc"},
    "fin_product_timely":  {"label": "金融分产品及时回复", "cols": ["stat_key", "complaint_count"]},
    "fin_word_freq":       {"label": "高频词",             "cols": ["word", "freq"], "sort_col": "freq desc"},
    "fcc_monthly":         {"label": "电信月度投诉",       "cols": ["stat_month", "complaint_count"], "sort_col": "stat_month"},
    "fcc_issue":           {"label": "电信投诉类型",       "cols": ["issue_name", "complaint_count"], "sort_col": "complaint_count desc"},
    "fcc_state":           {"label": "电信州级投诉",       "cols": ["state_code", "complaint_count"], "sort_col": "complaint_count desc"},
}
```

> 抄写时以 main.py 现有内容为准；若 main.py 里还有第 11 个表，一并搬入。

- [ ] **Step 2: 改 `backend/main.py`**

删除原 `DB_CONFIG = {...}`（第 21–28 行）与 `STATS_TABLES = {...}`（第 75–86 行），在文件顶部 import 区加：

```python
from db_meta import DB_CONFIG, STATS_TABLES
```

并保留 `BASE_DIR`、`DATA_ROOT` 定义（它们仍属于 main.py）。

- [ ] **Step 3: 在 `backend/main.py` 顶部加载 .env 并挂载路由**

在 `import` 区最上面加：

```python
from dotenv import load_dotenv
load_dotenv()
```

在 `app = FastAPI(...)` 与中间件之后、静态挂载附近加：

```python
from cluster import router as cluster_router
app.include_router(cluster_router)
```

> 此处先不要运行 —— Task 4 之前 `cluster.py` 还不存在，会 ImportError。本步只把改动写好，Task 5 结束时再整体启动。

- [ ] **Step 4: 新建 `backend/.env.example`**

```dotenv
# Hadoop 集群（SSH）
CLUSTER_HOST=10.15.7.101
CLUSTER_PORT=22
CLUSTER_USER=hadoop
CLUSTER_PASSWORD=dsj123
CLUSTER_JAR_DIR=/home/hadoop/jars

# 本地 jar 目录
JAR_DIR=D:\fqh\jar包

# 1=不连集群，用内置假数据跑通页面（联调用）
CLUSTER_MOCK=0
```

- [ ] **Step 5: 复制为 `backend/.env`（值同上，`CLUSTER_MOCK=0`）**

- [ ] **Step 6: 更新 `backend/requirements.txt`**

在文件末尾追加两行：

```
paramiko>=3.4,<4.0
python-dotenv>=1.0,<2.0
```

- [ ] **Step 7: 安装依赖并验证 main.py 仍可导入**

Run:
```
py -3.13 -m pip install "paramiko>=3.4,<4.0" "python-dotenv>=1.0,<2.0"
```
Expected: `Successfully installed ...`

Run:
```
py -3.13 -c "import sys; sys.path.insert(0,'d:/fqh/backend'); import main; print('main ok', len(main.STATS_TABLES))"
```
Expected: `main ok 10`（表数量以实际为准）

---

### Task 2: 任务配置 `cluster_jobs.json`

**Files:**
- Create: `backend/cluster_jobs.json`

- [ ] **Step 1: 写入完整配置**

```json
{
  "jobs": [
    {"id": "company_count", "name": "金融 · 企业投诉量", "jar": "CompanyCount.jar", "main_class": null,
     "default_input": "/data/cfpb_struct/input/complaints_clean.csv", "default_output": "/data/output/company_count",
     "target_table": "fin_company", "columns": ["company_name", "complaint_count"], "parser": "tsv",
     "import_enabled": false, "description": "按企业聚合 CFPB 投诉"},

    {"id": "product_count", "name": "金融 · 产品投诉量", "jar": "ProductCount.jar", "main_class": null,
     "default_input": "/data/cfpb_struct/input/complaints_clean.csv", "default_output": "/data/output/product_count",
     "target_table": "fin_product", "columns": ["product_name", "complaint_count"], "parser": "tsv",
     "import_enabled": false, "description": "按产品聚合 CFPB 投诉"},

    {"id": "state_count", "name": "金融 · 州级投诉量", "jar": "state_count.jar", "main_class": null,
     "default_input": "/data/cfpb_struct/input/complaints_clean.csv", "default_output": "/data/output/state_count",
     "target_table": "fin_state", "columns": ["state_code", "complaint_count"], "parser": "tsv",
     "import_enabled": false, "description": "按州聚合 CFPB 投诉"},

    {"id": "timely_response", "name": "金融 · 及时回复率", "jar": "TimelyResponseCount.jar", "main_class": null,
     "default_input": "/data/cfpb_struct/input/complaints_clean.csv", "default_output": "/data/output/timely_response",
     "target_table": "fin_timely_response", "columns": ["response_flag", "complaint_count"], "parser": "tsv",
     "import_enabled": false, "description": "按及时回复标记统计"},

    {"id": "product_timely", "name": "金融 · 分产品及时回复", "jar": "ProductTimelyCount.jar", "main_class": null,
     "default_input": "/data/cfpb_struct/input/complaints_clean.csv", "default_output": "/data/output/product_timely",
     "target_table": "fin_product_timely", "columns": ["stat_key", "complaint_count"], "parser": "tsv",
     "import_enabled": false, "description": "产品 × 及时回复组合统计"},

    {"id": "word_count", "name": "文本 · 高频词", "jar": "NarrativeWordCount.jar", "main_class": "org.example.Main",
     "default_input": "/data/cfpb_text/input/", "default_output": "/data/output/word_count",
     "target_table": "fin_word_freq", "columns": ["word", "freq"], "parser": "tsv",
     "import_enabled": false, "description": "投诉叙述分词词频"},

    {"id": "word_count2", "name": "文本 · 高频词（第二版）", "jar": "NarrativeWordCount2.jar", "main_class": "org.example.Main",
     "default_input": "/data/cfpb_text/input/", "default_output": "/data/output/word_count2",
     "target_table": "fin_word_freq", "columns": ["word", "freq"], "parser": "tsv",
     "import_enabled": false, "description": "备用分词口径，默认不入库（会覆盖 fin_word_freq）"},

    {"id": "fcc_state", "name": "电信 · 州级投诉量", "jar": "FccStateCount.jar", "main_class": null,
     "default_input": "/data/fcc/input/fcc_consumer_complaints_clean.csv", "default_output": "/data/output/fcc_state",
     "target_table": "fcc_state", "columns": ["state_code", "complaint_count"], "parser": "tsv",
     "import_enabled": false, "description": "按州聚合 FCC 投诉"},

    {"id": "fcc_monthly", "name": "电信 · 月度投诉量", "jar": "FccMonthlyCount.jar", "main_class": null,
     "default_input": "/data/fcc/input/fcc_consumer_complaints_clean.csv", "default_output": "/data/output/fcc_monthly",
     "target_table": "fcc_monthly", "columns": ["stat_month", "complaint_count"], "parser": "tsv",
     "import_enabled": false, "description": "按月聚合 FCC 投诉"},

    {"id": "fcc_issue", "name": "电信 · 投诉类型", "jar": "FccIssueCount.jar", "main_class": null,
     "default_input": "/data/fcc/input/fcc_consumer_complaints_clean.csv", "default_output": "/data/output/fcc_issue",
     "target_table": "fcc_issue", "columns": ["issue_name", "complaint_count"], "parser": "tsv",
     "import_enabled": false, "description": "按投诉类型聚合 FCC 投诉"}
  ]
}
```

> `main_class`：`NarrativeWordCount`/`NarrativeWordCount2` 的清单 Main-Class 与包内类名不一致的风险最高，
> 预设为 `org.example.Main`；其余先用 jar 清单。若运行报 `ClassNotFoundException`，把该项改成
> `org.example.Main`（这些 jar 的包内均带 `org/example/Main.class`）。

- [ ] **Step 2: 校验 JSON 可解析**

Run: `py -3.13 -c "import json;d=json.load(open(r'd:\fqh\backend\cluster_jobs.json',encoding='utf-8'));print(len(d['jobs']),'jobs')"`
Expected: `10 jobs`

---

### Task 3: cluster.py 纯函数层 + 单测

**Files:**
- Create: `backend/cluster.py`（本任务只写无网络依赖的部分 + 空 router）
- Create: `backend/tests/test_cluster.py`

- [ ] **Step 1: 先写失败单测 `backend/tests/test_cluster.py`**

```python
import json, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cluster


class TestValidatePath(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(cluster.validate_path("/data/cfpb_struct/input/complaints_clean.csv"),
                         "/data/cfpb_struct/input/complaints_clean.csv")
        self.assertEqual(cluster.validate_path("/data/output/"), "/data/output")

    def test_reject(self):
        for bad in ["data/out", "", None, "/data/../etc", "/data/out;rm -rf /", "/data/out x", "C:\\data"]:
            with self.assertRaises(ValueError):
                cluster.validate_path(bad)


class TestParse(unittest.TestCase):
    def test_progress(self):
        self.assertEqual(cluster.parse_progress("2026-11-06 10:00:01,234 INFO map 40% reduce 0%"),
                         {"map": 40, "reduce": 0})
        self.assertIsNone(cluster.parse_progress("job is running"))

    def test_app_id(self):
        self.assertEqual(cluster.find_app_id("Submitting tokens ... application_1762300000000_0042"),
                         "application_1762300000000_0042")
        self.assertIsNone(cluster.find_app_id("no app here"))

    def test_clean_ansi(self):
        self.assertEqual(cluster.clean_ansi("\x1b[1;32mINFO\x1b[0m ok"), "INFO ok")

    def test_parse_rows(self):
        rows = list(cluster.parse_rows(["CA\t120\n", "TX\t98\n", "\n"], "tsv", 2))
        self.assertEqual(rows, [("CA", 120), ("TX", 98)])
        with self.assertRaises(ValueError):
            list(cluster.parse_rows(["CA\t120\textra\n"], "tsv", 2))

    def test_numeric_coerce(self):
        self.assertEqual(cluster.coerce("120"), 120)
        self.assertEqual(cluster.coerce("CA"), "CA")


class TestHistory(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "h.json"
            cluster.save_history([{"run_id": "r1", "state": "success"}], p)
            self.assertEqual(cluster.load_history(p)[0]["run_id"], "r1")
            p.write_text("{broken", encoding="utf-8")
            self.assertEqual(cluster.load_history(p), [])


class TestConfig(unittest.TestCase):
    def test_load_jobs(self):
        jobs = cluster.load_job_configs()
        self.assertEqual(len(jobs), 10)
        self.assertIn("fcc_state", jobs)
        self.assertEqual(jobs["fcc_state"]["columns"], ["state_code", "complaint_count"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `py -3.13 -m unittest backend.tests.test_cluster -v`（在 `d:\fqh` 下）
Expected: `ModuleNotFoundError: No module named 'cluster'` 或 `AttributeError: module 'cluster' has no attribute 'validate_path'`

- [ ] **Step 3: 写 `backend/cluster.py` 纯函数部分**

```python
# -*- coding: utf-8 -*-
"""Hadoop 集群控制：SSH 驱动 MapReduce 任务，可选写回本地 MySQL。"""
import json
import os
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

import pymysql
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db_meta import DB_CONFIG, STATS_TABLES

BASE_DIR = Path(__file__).resolve().parent
JOBS_PATH = BASE_DIR / "cluster_jobs.json"
HISTORY_PATH = BASE_DIR / "cluster_history.json"
LOG_DIR = BASE_DIR / ".cluster_logs"
JAR_LOCAL_DIR = Path(os.getenv("JAR_DIR", r"D:\fqh\jar包"))
JAR_REMOTE_DIR = os.getenv("CLUSTER_JAR_DIR", "/home/hadoop/jars")
MOCK = os.getenv("CLUSTER_MOCK", "0") == "1"

PATH_RE = re.compile(r"^/[A-Za-z0-9._/-]+$")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
APP_ID_RE = re.compile(r"(application_\d+_\d+)")
PROGRESS_RE = re.compile(r"map\s+(\d+)%\s+reduce\s+(\d+)%", re.I)

router = APIRouter(prefix="/api/cluster", tags=["cluster"])


# ---------------- 纯函数 ----------------
def validate_path(p: str) -> str:
    """只允许绝对 HDFS 路径，禁止 ..、空格、shell 元字符。"""
    if not isinstance(p, str) or not PATH_RE.match(p):
        raise ValueError(f"非法 HDFS 路径：{p!r}")
    if ".." in p.split("/"):
        raise ValueError(f"非法 HDFS 路径：{p!r}")
    return p.rstrip("/") or "/"


def clean_ansi(s: str) -> str:
    return ANSI_RE.sub("", s).replace("\r", "")


def parse_progress(line: str) -> Optional[dict]:
    m = PROGRESS_RE.search(line)
    return {"map": int(m.group(1)), "reduce": int(m.group(2))} if m else None


def find_app_id(line: str) -> Optional[str]:
    m = APP_ID_RE.search(line)
    return m.group(1) if m else None


def coerce(v: str):
    s = v.strip()
    if re.fullmatch(r"-?\d+", s):
        return int(s)
    return s


def parse_rows(lines, parser: str = "tsv", ncols: int = 2) -> Generator[tuple, None, None]:
    sep = "\t" if parser == "tsv" else ","
    for raw in lines:
        line = clean_ansi(raw).rstrip("\n")
        if not line.strip():
            continue
        parts = line.split(sep)
        if len(parts) != ncols:
            raise ValueError(f"输出列数与配置不符（期望 {ncols} 列）：{line[:120]}")
        yield tuple(coerce(p) for p in parts)


def load_job_configs() -> dict:
    with open(JOBS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {j["id"]: j for j in data["jobs"]}


def load_history(path: Path = HISTORY_PATH) -> list:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(runs: list, path: Path = HISTORY_PATH) -> None:
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(runs[-200:], f, ensure_ascii=False, indent=1)
    tmp.replace(path)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `py -3.13 -m unittest backend.tests.test_cluster -v`
Expected: `Ran 11 tests ... OK`

---

### Task 4: SSH 层 + 状态接口

**Files:**
- Modify: `backend/cluster.py`（追加 SSH 与 `/status`、`/test`）

- [ ] **Step 1: 追加 SSH 单例与命令执行**

```python
# ---------------- SSH ----------------
CLUSTER_HOST = os.getenv("CLUSTER_HOST", "10.15.7.101")
CLUSTER_PORT = int(os.getenv("CLUSTER_PORT", "22"))
CLUSTER_USER = os.getenv("CLUSTER_USER", "hadoop")
CLUSTER_PASSWORD = os.getenv("CLUSTER_PASSWORD", "")

_clients = {}
_client_lock = threading.Lock()


def get_client(slot: str = "main"):
    """exec（长任务）与 monitor（状态查询）使用独立连接，互不阻塞。"""
    if MOCK:
        return None
    import paramiko
    with _client_lock:
        c = _clients.get(slot)
        if c is not None and c.get_transport() and c.get_transport().is_active():
            return c
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(CLUSTER_HOST, CLUSTER_PORT, CLUSTER_USER, CLUSTER_PASSWORD,
                  timeout=15, banner_timeout=20, auth_timeout=20)
        _clients[slot] = c
        return c


def run_cmd(cmd: str, timeout: int = 60, slot: str = "monitor"):
    """执行短命令，返回 (退出码, 合并输出)。"""
    if MOCK:
        return 0, _mock_cmd(cmd)
    try:
        c = get_client(slot)
        _in, out, err = c.exec_command(cmd, timeout=timeout)
        text = out.read().decode("utf-8", "ignore") + err.read().decode("utf-8", "ignore")
        return out.channel.recv_exit_status(), clean_ansi(text)
    except Exception as e:
        return 255, f"SSH_ERROR: {e}"
```

- [ ] **Step 2: 追加 mock 输出与连接测试、状态解析**

```python
def _mock_cmd(cmd: str) -> str:
    if "hostname" in cmd:
        return "worker1\n"
    if "hadoop version" in cmd:
        return "Hadoop 3.3.6\n"
    if "dfs -df" in cmd:
        return ("Filesystem  Size  Used  Available  Use%  Mounted on\n"
                "hdfs://ns  120 G  86.4 G  33.6 G  72%  /\n")
    if "node -list" in cmd:
        return "Total Nodes:3\n  Node-Id  Node-State  ...\nworker1 RUNNING\nworker2 RUNNING\nworker3 RUNNING\n"
    if "application -list" in cmd:
        return "Total number of applications (application-types: [] and states: [SUBMITTED, ACCEPTED, RUNNING]):1\n"
    return ""


def _parse_status() -> dict:
    rc_df, df = run_cmd("hdfs dfs -df -h")
    rc_node, nodes = run_cmd("yarn node -list")
    rc_app, apps = run_cmd("yarn application -list")

    hdfs = {"used": "—", "total": "—", "pct": 0}
    for line in df.splitlines():
        if line.startswith("hdfs://") or line.startswith("Filesystem "):
            if line.startswith("Filesystem "):
                continue
            cols = line.split()
            if len(cols) >= 5:
                hdfs = {"total": cols[1], "used": cols[2], "pct": int(str(cols[4]).rstrip("%") or 0)}

    total = 0
    m = re.search(r"Total Nodes:(\d+)", nodes)
    if m:
        total = int(m.group(1))
    active = len([l for l in nodes.splitlines() if l.split()[-1:] == ["RUNNING"]])

    running = 0
    m = re.search(r"applications.*?:(\d+)", apps)
    if m:
        running = int(m.group(1))

    err = None
    if rc_df != 0:
        err = df.strip().splitlines()[-1] if df.strip() else "HDFS 状态获取失败"

    return {
        "connected": err is None,
        "host": CLUSTER_HOST,
        "user": CLUSTER_USER,
        "hdfs": hdfs,
        "nodes": {"total": total, "active": active},
        "apps": {"running": running},
        "error": err,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
```

- [ ] **Step 3: 追加两个路由**

```python
@router.get("/status")
def cluster_status():
    return {"ok": True, **_parse_status()}


@router.post("/test")
def cluster_test():
    t0 = time.time()
    rc, out = run_cmd("hostname")
    if rc != 0:
        return {"ok": False, "error": "SSH 连接失败", "detail": out}
    rc2, ver = run_cmd("hadoop version | head -1")
    return {
        "ok": True,
        "hostname": out.strip(),
        "hadoop_version": ver.strip(),
        "latency_ms": int((time.time() - t0) * 1000),
    }
```

- [ ] **Step 4: 临时注册路由验证接口**

确保 `main.py` 已在 Task 1 完成 `include_router`，然后启动并测试：

Run:
```
py -3.13 -m uvicorn main:app --host 127.0.0.1 --port 8000
```
（cwd 设为 `d:\fqh\backend`；`CLUSTER_MOCK=1` 可先不连集群）

Run（另开终端）: `curl http://127.0.0.1:8000/api/cluster/test`
Expected（MOCK=1）: `{"ok":true,"hostname":"worker1","hadoop_version":"Hadoop 3.3.6","latency_ms":...}`

Run: `curl http://127.0.0.1:8000/api/cluster/status`
Expected: `{"ok":true,"connected":true,...}`，`hdfs.pct=72`，`nodes.total=3`

- [ ] **Step 5: 关闭 mock（`CLUSTER_MOCK=0`）时，若 SSH 不通应看到 `connected:false` 且 `error` 有原文**

Run: `curl http://127.0.0.1:8000/api/cluster/status`
Expected: 未配置可达集群时 `"connected":false`，不抛 500

---

### Task 5: 任务调度 + 日志 + 入库 + 全部路由

**Files:**
- Modify: `backend/cluster.py`（追加 RUNS/执行器/入库/路由）
- Test: `backend/tests/test_cluster.py`（追加入库解析测试）

- [ ] **Step 1: 追加运行态管理与执行器**

```python
# ---------------- 运行态 ----------------
executor = ThreadPoolExecutor(max_workers=2)
RUNS = {}           # run_id -> dict
ACTIVE = {}         # job_id -> run_id
_runs_lock = threading.Lock()
_history = load_history()
```

```python
def _new_run(job: dict, input_path: str, output_path: str, import_flag: bool) -> dict:
    run = {
        "run_id": uuid.uuid4().hex[:12],
        "id": job["id"],
        "name": job["name"],
        "state": "queued",
        "import_state": "off" if not import_flag else "pending",
        "progress": None,
        "app_id": None,
        "lines": [],
        "started": datetime.now().isoformat(timespec="seconds"),
        "ended": None,
        "rows_imported": 0,
        "input": input_path,
        "output": output_path,
        "import_to_mysql": import_flag,
        "error": None,
    }
    LOG_DIR.mkdir(exist_ok=True)
    run["log_file"] = str(LOG_DIR / f"{run['run_id']}.log")
    with _runs_lock:
        RUNS[run["run_id"]] = run
        ACTIVE[job["id"]] = run["run_id"]
    return run


def _append_line(run: dict, text: str) -> None:
    line = clean_ansi(text)
    if not line.strip():
        return
    with _runs_lock:
        run["lines"].append(line)
        if len(run["lines"]) > 5000:
            del run["lines"][:1000]
        p = parse_progress(line)
        if p:
            run["progress"] = p
        if not run["app_id"]:
            run["app_id"] = find_app_id(line)
    try:
        with open(run["log_file"], "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _finish(run: dict, state: str, error: Optional[str] = None) -> None:
    with _runs_lock:
        run["state"] = state
        run["ended"] = datetime.now().isoformat(timespec="seconds")
        if error:
            run["error"] = error[-800:]
        ACTIVE.pop(run["id"], None)
        _history.append({k: run[k] for k in
                         ("run_id", "id", "name", "state", "started", "ended",
                          "import_state", "rows_imported")})
        save_history(_history)
```

- [ ] **Step 2: 追加执行流程**

```python
def _ensure_jar(job: dict) -> str:
    remote = f"{JAR_REMOTE_DIR}/{job['jar']}"
    if MOCK:
        return remote
    rc, _ = run_cmd(f"ls -l {remote}")
    if rc == 0:
        return remote
    local = JAR_LOCAL_DIR / job["jar"]
    if not local.exists():
        raise FileNotFoundError(f"本地缺少 jar：{local}")
    run_cmd(f"mkdir -p {JAR_REMOTE_DIR}")
    sftp = get_client().open_sftp()
    try:
        sftp.put(str(local), remote)
    finally:
        sftp.close()
    return remote


def _hdfs_lines(output_path: str) -> Generator[str, None, None]:
    if MOCK:
        for line in ["CA\t120\n", "TX\t98\n", "FL\t77\n"]:
            yield line
        return
    chan = get_client("monitor").get_transport().open_session()
    chan.exec_command(f"hdfs dfs -cat {output_path}/part-r-*")
    buf = b""
    while True:
        data = chan.recv(4096)
        if not data:
            if chan.exit_status_ready():
                break
            time.sleep(0.1)
            continue
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            yield line.decode("utf-8", "ignore") + "\n"


def import_output(run: dict, job: dict) -> int:
    table = job["target_table"]
    if table not in STATS_TABLES:
        raise ValueError(f"目标表不在白名单：{table}")
    cols = job["columns"]
    rows = list(parse_rows(_hdfs_lines(run["output"]), job.get("parser", "tsv"), len(cols)))
    if not rows:
        raise ValueError("输出为空，未写入 MySQL")
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            conn.begin()
            cur.execute(f"DELETE FROM `{table}`")
            cur.executemany(
                f"INSERT INTO `{table}` (`{cols[0]}`, `{cols[1]}`) VALUES (%s, %s)", rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return len(rows)


def _stream_run(cmd: str, run: dict) -> int:
    if MOCK:
        for pct in (0, 20, 40, 60, 80, 100):
            _append_line(run, f"2026-11-06 10:00:00,000 INFO map {pct}% reduce {max(0, pct - 20)}%")
            time.sleep(0.4)
        _append_line(run, "2026-11-06 10:00:05,000 INFO application_1762300000000_0042 completed successfully")
        return 0
    chan = get_client("exec").get_transport().open_session()
    chan.exec_command(cmd)
    buf = b""
    while True:
        data = chan.recv(4096)
        if not data:
            if chan.exit_status_ready():
                break
            time.sleep(0.1)
            continue
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            _append_line(run, line.decode("utf-8", "ignore"))
    if buf:
        _append_line(run, buf.decode("utf-8", "ignore"))
    return chan.recv_exit_status()


def _execute(run: dict, job: dict) -> None:
    try:
        _append_line(run, f"$ hadoop jar {job['jar']} {run['input']} -> {run['output']}")
        if run["output"]:
            run_cmd(f"hdfs dfs -rm -r -skipTrash {run['output']} 2>/dev/null")
        jar = _ensure_jar(job)
        cls = f" {job['main_class']}" if job.get("main_class") else ""
        cmd = f"hadoop jar {jar}{cls} {run['input']} {run['output']}"
        rc = _stream_run(cmd, run)
        if rc != 0:
            _finish(run, "failed", f"MR 退出码 {rc}")
            return
        _finish(run, "success")
        if run["import_to_mysql"]:
            run["import_state"] = "running"
            try:
                n = import_output(run, job)
                run["rows_imported"] = n
                run["import_state"] = "success"
                _append_line(run, f"已写入 MySQL：{job['target_table']} {n} 行")
            except Exception as e:
                run["import_state"] = "failed"
                _append_line(run, f"入库失败：{e}")
    except Exception as e:
        _finish(run, "failed", f"{type(e).__name__}: {e}")
    finally:
        save_history(_history)
```

- [ ] **Step 3: 追加路由**

```python
class RunReq(BaseModel):
    input: str
    output: str
    overwrite: bool = False
    import_to_mysql: bool = False


def _job_view(job: dict) -> dict:
    run_id = ACTIVE.get(job["id"])
    run = RUNS.get(run_id) if run_id else None
    last = next((h for h in reversed(_history) if h["id"] == job["id"]), None)
    return {
        "id": job["id"], "name": job["name"], "jar": job["jar"], "description": job["description"],
        "input": (run or {}).get("input", job["default_input"]),
        "output": (run or {}).get("output", job["default_output"]),
        "import_to_mysql": (run or {}).get("import_to_mysql", job.get("import_enabled", False)),
        "state": (run or {}).get("state", "idle"),
        "import_state": (run or {}).get("import_state", "off"),
        "progress": (run or {}).get("progress"),
        "run_id": run_id,
        "last_run": last,
    }


@router.get("/jobs")
def list_jobs():
    try:
        jobs = load_job_configs()
    except Exception as e:
        return {"ok": False, "error": "任务配置读取失败", "detail": str(e)}
    return {"ok": True, "jobs": [_job_view(j) for j in jobs.values()]}


@router.post("/jobs/{job_id}/run")
def run_job(job_id: str, req: RunReq):
    jobs = load_job_configs()
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    try:
        inp = validate_path(req.input)
        out = validate_path(req.output)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if ACTIVE.get(job_id):
        return {"ok": False, "error": "该任务正在运行"}
    run = _new_run(job, inp, out, req.import_to_mysql)
    executor.submit(_execute, run, job)
    return {"ok": True, "run_id": run["run_id"], "state": run["state"]}


@router.post("/jobs/{job_id}/kill")
def kill_job(job_id: str):
    run_id = ACTIVE.get(job_id)
    if not run_id:
        return {"ok": False, "error": "该任务没有运行中的实例"}
    run = RUNS[run_id]
    if run.get("app_id"):
        rc, out = run_cmd(f"yarn application -kill {run['app_id']}")
        _finish(run, "killed", out if rc else None)
        return {"ok": rc == 0, "app_id": run["app_id"]}
    _finish(run, "killed")
    return {"ok": True, "app_id": None}


@router.get("/jobs/{job_id}/log")
def job_log(job_id: str, offset: int = 0):
    run_id = ACTIVE.get(job_id)
    if not run_id:
        return {"ok": True, "lines": [], "state": "idle", "offset": offset}
    run = RUNS[run_id]
    lines = run["lines"][offset:]
    return {"ok": True, "lines": lines, "offset": offset + len(lines),
            "state": run["state"], "progress": run["progress"], "app_id": run["app_id"],
            "import_state": run["import_state"]}


@router.get("/jobs/{job_id}/preview")
def preview_output(job_id: str):
    job = load_job_configs().get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    out = validate_path(job["default_output"])
    rc, text = run_cmd(f"hdfs dfs -cat {out}/part-r-* 2>/dev/null | head -20")
    return {"ok": rc == 0, "lines": text.splitlines(), "error": None if rc == 0 else text}


@router.post("/jobs/{job_id}/import")
def manual_import(job_id: str):
    job = load_job_configs().get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    run_id = ACTIVE.get(job_id)
    run = RUNS.get(run_id) if run_id else {
        "output": job["default_output"], "import_state": "pending", "rows_imported": 0}
    try:
        n = import_output(run, job)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    run["import_state"] = "success"
    run["rows_imported"] = n
    return {"ok": True, "rows": n, "table": job["target_table"]}


@router.get("/history")
def history(limit: int = 20):
    return {"ok": True, "runs": _history[-limit:][::-1]}
```

- [ ] **Step 4: 追加单测（解析与入库前置校验）**

在 `test_cluster.py` 的 `TestParse` 类里加：

```python
    def test_parse_rows_csv(self):
        self.assertEqual(list(cluster.parse_rows(["CA,120\n"], "csv", 2)), [("CA", 120)])

    def test_target_table_whitelist(self):
        jobs = cluster.load_job_configs()
        for j in jobs.values():
            self.assertIn(j["target_table"], cluster.STATS_TABLES)
```

- [ ] **Step 5: 跑全部单测**

Run: `py -3.13 -m unittest backend.tests.test_cluster -v`
Expected: `Ran 13 tests ... OK`

- [ ] **Step 6: 起服务（MOCK=1）跑通 4 个接口**

Run（cwd=`d:\fqh\backend`）:
```
$env:CLUSTER_MOCK="1"; py -3.13 -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Run（另开终端）:
```
curl http://127.0.0.1:8000/api/cluster/jobs
curl -X POST http://127.0.0.1:8000/api/cluster/jobs/fcc_state/run -H "Content-Type: application/json" -d '{"input":"/data/fcc/input/fcc_consumer_complaints_clean.csv","output":"/data/output/fcc_state","overwrite":true,"import_to_mysql":false}'
curl "http://127.0.0.1:8000/api/cluster/jobs/fcc_state/log?offset=0"
curl http://127.0.0.1:8000/api/cluster/history
```
Expected: run 返回 `run_id`；2 秒后 log 出现 `map 100% reduce 80%` 且 `state=success`；history 有 1 条。若本机 MySQL 不可用，`import_to_mysql=false` 不受影响。

- [ ] **Step 7: 验证非法路径被拒**

```
curl -X POST http://127.0.0.1:8000/api/cluster/jobs/fcc_state/run -H "Content-Type: application/json" -d '{"input":"../../etc/passwd","output":"/data/output/x"}'
```
Expected: HTTP 400，`非法 HDFS 路径`

---

### Task 6: 前端页面骨架（导航 + 模板 + 样式）

**Files:**
- Modify: `backend/index.html`（`ICONS`、`pages`、页面条件块、`<style>`）

- [ ] **Step 1: 给 `ICONS` 加一个服务器图标（约 2524 行，`moon` 之后）**

```js
  cluster:_svg('<rect x="3.5" y="4" width="17" height="6" rx="2"/><rect x="3.5" y="14" width="17" height="6" rx="2"/><circle cx="7" cy="7" r="1" fill="currentColor" stroke="none"/><circle cx="7" cy="17" r="1" fill="currentColor" stroke="none"/>'),
```

- [ ] **Step 2: `pages` 数组追加一项（`alert` 之后、`query` 之前）**

```js
      { key:'cluster',   title:'集群控制台', icon: ICONS.cluster, tag:'HADOOP' },
```

- [ ] **Step 3: 在 `activePage === 'alert'` 区块之后插入页面模板**

插入到 `<div v-else-if="activePage === 'query'" ...>` 之前：

```html
      <div v-else-if="activePage === 'cluster'" class="page-enter">
        <!-- 指标卡 -->
        <div class="grid-4 mb-16">
          <div class="metric-card">
            <div class="label">HDFS 已用 / 总容量</div>
            <div class="value cluster-num">{{ cluster.hdfs.used }} <span class="cluster-sub">/ {{ cluster.hdfs.total }}</span></div>
            <div class="cluster-bar"><i :style="{ width: (cluster.hdfs.pct || 0) + '%' }"></i></div>
          </div>
          <div class="metric-card">
            <div class="label">YARN 节点</div>
            <div class="value cluster-num">{{ cluster.nodes.active }} <span class="cluster-sub">/ {{ cluster.nodes.total }}</span></div>
            <div class="cluster-note">活跃 / 总数</div>
          </div>
          <div class="metric-card">
            <div class="label">运行中任务</div>
            <div class="value cluster-num">{{ cluster.apps.running }}</div>
            <div class="cluster-note">YARN applications</div>
          </div>
          <div class="metric-card">
            <div class="label">近 24h 成功</div>
            <div class="value cluster-num">{{ cluster.success24 }}</div>
            <div class="cluster-note">本页提交记录</div>
          </div>
        </div>

        <!-- 连接条 -->
        <div class="cluster-conn mb-16" :class="cluster.connected ? 'is-on' : 'is-off'">
          <span class="dot"></span>
          <span class="mono">{{ cluster.host }} · {{ cluster.user }}</span>
          <span class="cluster-conn-state">{{ cluster.connected ? '已连接' : '未连接' }}</span>
          <span v-if="cluster.error" class="cluster-conn-err mono">{{ cluster.error }}</span>
          <button class="btn-ghost" @click="clusterTest">测试连接</button>
        </div>

        <div class="grid-2 cluster-grid">
          <!-- 任务列表 -->
          <div class="card">
            <div class="card-hd">
              <h3>MapReduce 任务</h3>
              <span class="card-tag">{{ cluster.jobs.length }} JOBS</span>
            </div>
            <div class="cluster-jobs">
              <div v-for="j in cluster.jobs" :key="j.id" class="cj" :class="'is-' + j.state">
                <div class="cj-top" @click="clusterToggle(j.id)">
                  <span class="cj-caret">{{ cluster.open[j.id] ? '▾' : '▸' }}</span>
                  <span class="cj-name">{{ j.name }}</span>
                  <span class="cj-jar mono">{{ j.jar }}</span>
                  <span class="cj-badge">{{ stateLabel(j.state) }}</span>
                  <span v-if="j.state === 'running' && j.progress" class="cj-pct mono">
                    map {{ j.progress.map }}% · reduce {{ j.progress.reduce }}%
                  </span>
                </div>
                <div v-show="cluster.open[j.id]" class="cj-body">
                  <label class="cj-row"><span>输入</span>
                    <input class="mono" v-model="cluster.inputs[j.id]" /></label>
                  <label class="cj-row"><span>输出</span>
                    <input class="mono" v-model="cluster.outputs[j.id]" /></label>
                  <div class="cj-actions">
                    <label class="cj-check"><input type="checkbox" v-model="cluster.imports[j.id]" /> 完成后写入 MySQL</label>
                    <label class="cj-check"><input type="checkbox" v-model="cluster.overwrites[j.id]" /> 覆盖输出目录</label>
                    <span class="cj-growth"></span>
                    <button class="btn-ghost" @click="clusterResetPaths(j)">恢复默认</button>
                    <button class="btn-ghost" @click="clusterPreview(j)">预览输出</button>
                    <button class="btn-primary" :disabled="!cluster.connected || j.state === 'running' || j.state === 'queued'"
                            @click="clusterRun(j)">运行</button>
                    <button class="btn-ghost danger" :disabled="j.state !== 'running' && j.state !== 'queued'"
                            @click="clusterKill(j)">停止</button>
                    <button class="btn-ghost" @click="clusterOpenLog(j)">日志</button>
                  </div>
                  <div v-if="j.last_run" class="cj-last mono">
                    上次：{{ j.last_run.state }} · {{ j.last_run.ended || '—' }} · 入库 {{ j.last_run.rows_imported || 0 }} 行
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 日志 -->
          <div class="card">
            <div class="card-hd">
              <h3>运行日志</h3>
              <span class="card-tag mono">{{ cluster.logJob || '—' }}</span>
            </div>
            <div class="cluster-log" ref="clusterLogRef">
              <div v-if="!cluster.logLines.length" class="cluster-log-empty">选择任务并运行后可查看日志</div>
              <div v-for="(l, i) in cluster.logLines" :key="i" class="cluster-log-line mono">{{ l }}</div>
            </div>
          </div>
        </div>

        <!-- 运行记录 -->
        <div class="card mt-16">
          <div class="card-hd"><h3>运行记录</h3><span class="card-tag">最近 20 条</span></div>
          <table class="cluster-table">
            <thead><tr><th>开始</th><th>任务</th><th>状态</th><th>耗时</th><th>入库行数</th></tr></thead>
            <tbody>
              <tr v-for="r in cluster.history" :key="r.run_id">
                <td class="mono">{{ r.started }}</td>
                <td>{{ r.name }}</td>
                <td><span class="cj-badge" :class="'is-' + r.state">{{ stateLabel(r.state) }}</span></td>
                <td class="mono">{{ duration(r) }}</td>
                <td class="mono">{{ r.rows_imported || 0 }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
```

- [ ] **Step 4: 追加样式（在 `</style>` 前，紧跟现有卡片样式之后）**

```css
  /* ===== 集群控制台 ===== */
  .cluster-num { font-variant-numeric: tabular-nums; }
  .cluster-sub { font-size: 12px; color: var(--fg-2); font-weight: 400; }
  .cluster-note { font-size: 11px; color: var(--fg-2); margin-top: 4px; }
  .cluster-bar { height: 3px; border-radius: 2px; background: var(--border); margin-top: 10px; overflow: hidden; }
  .cluster-bar i { display: block; height: 100%; background: var(--fin-top1); transition: width .4s var(--ease-out); }

  .cluster-conn { display: flex; align-items: center; gap: 10px; padding: 10px 14px;
    border: 1px solid var(--border); border-radius: var(--radius-md); background: var(--card-face);
    font-size: 12px; color: var(--fg-1); }
  .cluster-conn .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--fg-3); }
  .cluster-conn.is-on .dot { background: var(--green); }
  .cluster-conn.is-off .dot { background: var(--red); }
  .cluster-conn-state { color: var(--fg-0); font-weight: 600; }
  .cluster-conn-err { color: var(--red); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 48%; }
  .cluster-conn .btn-ghost { margin-left: auto; }

  .cluster-grid { grid-template-columns: 1.15fr 1fr; }
  .cluster-jobs { max-height: 460px; overflow: auto; }
  .cj { border-bottom: 1px solid var(--border); }
  .cj:last-child { border-bottom: 0; }
  .cj-top { display: flex; align-items: center; gap: 10px; padding: 11px 4px; cursor: pointer; }
  .cj-caret { color: var(--fg-2); width: 12px; }
  .cj-name { font-size: 13px; color: var(--fg-0); }
  .cj-jar { font-size: 11px; color: var(--fg-2); }
  .cj-badge { margin-left: auto; font-size: 11px; padding: 2px 8px; border-radius: 999px;
    border: 1px solid var(--border); color: var(--fg-1); }
  .cj.is-running .cj-badge { color: var(--cyan); border-color: var(--cyan-dim); }
  .cj.is-success .cj-badge { color: var(--green); border-color: var(--green-dim); }
  .cj.is-failed .cj-badge { color: var(--red); border-color: var(--red-dim); }
  .cj.is-killed .cj-badge, .cj.is-idle .cj-badge { color: var(--fg-2); }
  .cj-pct { font-size: 11px; color: var(--fg-1); }
  .cj-body { padding: 4px 4px 12px 22px; display: grid; gap: 8px; }
  .cj-row { display: grid; grid-template-columns: 34px 1fr; align-items: center; gap: 8px; font-size: 12px; color: var(--fg-2); }
  .cj-row input { background: var(--bg-3); border: 1px solid var(--border); border-radius: var(--radius-sm);
    color: var(--fg-0); padding: 6px 8px; font-size: 12px; width: 100%; }
  .cj-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .cj-check { font-size: 12px; color: var(--fg-1); display: flex; align-items: center; gap: 6px; }
  .cj-growth { flex: 1 1 0; }
  .cj-last { font-size: 11px; color: var(--fg-2); }
  .btn-ghost.danger { color: var(--red); border-color: var(--red-dim); }
  .btn-ghost:disabled, .btn-primary:disabled { opacity: .45; cursor: not-allowed; }

  .cluster-log { height: 460px; overflow: auto; background: var(--bg-3); border-radius: var(--radius-sm);
    padding: 10px; font-size: 11.5px; line-height: 1.65; color: var(--fg-1); }
  .cluster-log-line { white-space: pre-wrap; word-break: break-all; }
  .cluster-log-empty { color: var(--fg-3); font-size: 12px; }

  .cluster-table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .cluster-table th, .cluster-table td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--border); }
  .cluster-table th { color: var(--fg-2); font-weight: 500; }
  .cluster-table td { color: var(--fg-1); }

  html[data-theme="light"] .cluster-log { background: #f4f0e8; }
  html[data-theme="light"] .cj-row input { background: #fbf8f2; }
  @media (max-width: 900px) {
    .cluster-grid { grid-template-columns: 1fr; }
    .cluster-log { height: 260px; }
  }
```

- [ ] **Step 5: 语法与渲染自检（此时逻辑未接，页面应能空态渲染）**

Run: 打开 `http://127.0.0.1:8000/?page=cluster`
Expected: 页面出现，无 console error；指标卡显示占位（0 / —），任务列表为空

---

### Task 7: 前端交互逻辑

**Files:**
- Modify: `backend/index.html`（`setup()` 内追加 `cluster` 状态与方法；`onMounted` 启动）

- [ ] **Step 1: 在 `setup()` 里、现有 `apiGet` 附近追加状态与常量**

```js
    // ========= 集群控制台 =========
    const cluster = reactive({
      connected: false, host: '', user: '', error: '',
      hdfs: { used: '—', total: '—', pct: 0 },
      nodes: { total: 0, active: 0 }, apps: { running: 0 }, success24: 0,
      jobs: [], history: [],
      open: {}, inputs: {}, outputs: {}, imports: {}, overwrites: {},
      logJob: '', logLines: [], logOffset: 0, selRunId: '',
    });
    const clusterLogRef = ref(null);
    let clusterTimer = null, clusterLogTimer = null;

    function stateLabel(s) {
      return ({ idle:'待运行', queued:'排队中', running:'运行中', success:'成功',
                failed:'失败', killed:'已停止', interrupted:'已中断' })[s] || s;
    }
    function duration(r) {
      if (!r.started || !r.ended) return '—';
      const ms = new Date(r.ended) - new Date(r.started);
      return ms < 1000 ? '<1s' : Math.round(ms / 1000) + 's';
    }
```

- [ ] **Step 2: 追加轮询与操作函数**

```js
    async function clusterLoadStatus() {
      try {
        const d = await apiGet('/api/cluster/status');
        cluster.connected = !!d.connected;
        cluster.host = d.host || '';
        cluster.user = d.user || '';
        cluster.error = d.error || '';
        cluster.hdfs = d.hdfs || cluster.hdfs;
        cluster.nodes = d.nodes || cluster.nodes;
        cluster.apps = d.apps || cluster.apps;
      } catch (e) {
        cluster.connected = false; cluster.error = String(e.message || e);
      }
    }

    async function clusterLoadJobs() {
      try {
        const d = await apiGet('/api/cluster/jobs');
        if (!d.ok) return;
        cluster.jobs = d.jobs;
        d.jobs.forEach(j => {
          if (!cluster.open[j.id]) cluster.open[j.id] = false;
          if (cluster.inputs[j.id] === undefined) cluster.inputs[j.id] = j.input;
          if (cluster.outputs[j.id] === undefined) cluster.outputs[j.id] = j.output;
          if (cluster.imports[j.id] === undefined) cluster.imports[j.id] = j.import_to_mysql;
          if (cluster.overwrites[j.id] === undefined) cluster.overwrites[j.id] = false;
        });
      } catch (e) { /* 保留上一帧 */ }
    }

    async function clusterLoadHistory() {
      try {
        const d = await apiGet('/api/cluster/history?limit=20');
        if (d.ok) {
          cluster.history = d.runs;
          const dayAgo = Date.now() - 864e5;
          cluster.success24 = d.runs.filter(r =>
            r.state === 'success' && new Date(r.ended || r.started).getTime() > dayAgo).length;
        }
      } catch (e) {}
    }

    async function clusterPollLog() {
      if (!cluster.logJob) return;
      try {
        const d = await apiGet(`/api/cluster/jobs/${cluster.logJob}/log?offset=${cluster.logOffset}`);
        if (!d.ok) return;
        if (d.lines?.length) {
          cluster.logLines.push(...d.lines);
          cluster.logOffset = d.offset;
          if (cluster.logLines.length > 2000) cluster.logLines.splice(0, cluster.logLines.length - 2000);
          const el = clusterLogRef.value;
          if (el && el.scrollTop + el.clientHeight >= el.scrollHeight - 40) el.scrollTop = el.scrollHeight;
        }
        const job = cluster.jobs.find(j => j.id === cluster.logJob);
        if (job) { job.state = d.state; job.progress = d.progress; }
      } catch (e) {}
    }

    function clusterToggle(id) {
      cluster.open[id] = !cluster.open[id];
      if (cluster.open[id]) clusterOpenLog({ id });
    }

    async function clusterTest() {
      try {
        const r = await fetch(API + '/api/cluster/test', { method: 'POST' });
        const d = await r.json();
        ElementPlus.ElMessage[d.ok ? 'success' : 'error'](
          d.ok ? `连接成功：${d.hostname}（${d.hadoop_version}，${d.latency_ms}ms）`
               : `${d.error}：${d.detail || ''}`);
        await clusterLoadStatus();
      } catch (e) { ElementPlus.ElMessage.error('连接测试失败：' + e.message); }
    }

    async function clusterRun(j) {
      const r = await fetch(API + `/api/cluster/jobs/${j.id}/run`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input: cluster.inputs[j.id], output: cluster.outputs[j.id],
                               overwrite: !!cluster.overwrites[j.id],
                               import_to_mysql: !!cluster.imports[j.id] }),
      });
      const d = await r.json();
      if (!d.ok) return ElementPlus.ElMessage.error(d.error || '提交失败');
      cluster.logJob = j.id; cluster.logLines = []; cluster.logOffset = 0;
      await clusterLoadJobs(); await clusterPollLog();
    }

    async function clusterKill(j) {
      const r = await fetch(API + `/api/cluster/jobs/${j.id}/kill`, { method: 'POST' });
      const d = await r.json();
      ElementPlus.ElMessage[d.ok ? 'success' : 'warning'](d.ok ? '已提交停止' : d.error);
      await clusterLoadJobs();
    }

    function clusterOpenLog(j) {
      if (!j || !j.id) return;
      cluster.logJob = j.id; cluster.logLines = []; cluster.logOffset = 0;
      clusterPollLog();
    }

    async function clusterPreview(j) {
      const d = await apiGet(`/api/cluster/jobs/${j.id}/preview`);
      if (!d.ok) return ElementPlus.ElMessage.error(d.error || '预览失败');
      cluster.logJob = j.id; cluster.logLines = d.lines;
    }

    function clusterResetPaths(j) {
      cluster.inputs[j.id] = j.default_input || j.input;
      cluster.outputs[j.id] = j.default_output || j.output;
    }

    async function clusterImport(j) {
      const r = await fetch(API + `/api/cluster/jobs/${j.id}/import`, { method: 'POST' });
      const d = await r.json();
      ElementPlus.ElMessage[d.ok ? 'success' : 'error'](
        d.ok ? `已写入 ${d.table}：${d.rows} 行` : d.error);
      await clusterLoadHistory();
    }

    function startClusterPoll() {
      stopClusterPoll();
      clusterLoadStatus(); clusterLoadJobs(); clusterLoadHistory();
      clusterTimer = setInterval(() => {
        if (document.hidden) return;
        clusterLoadJobs(); clusterLoadHistory();
        if (cluster.logJob) clusterPollLog();
      }, 2000);
    }
    function stopClusterPoll() {
      if (clusterTimer) clearInterval(clusterTimer); clusterTimer = null;
    }
```

> `clusterResetPaths` 依赖 `/api/cluster/jobs` 返回了 `default_input/default_output`。当前 `_job_view`
> 只返回 `input/output`。请在 Task 5 的 `_job_view` 里补两个字段：
> `"default_input": job["default_input"], "default_output": job["default_output"]`。

- [ ] **Step 3: 页面切换时启停轮询**

在 `setup()` 里 `activePage` 定义之后加：

```js
    watch(activePage, v => { if (v === 'cluster') startClusterPoll(); else stopClusterPoll(); });
```

并在 `onMounted` 末尾调用一次：

```js
    if (activePage.value === 'cluster') startClusterPoll();
```

- [ ] **Step 4: `return` 中暴露新符号**

在 `setup()` 的 `return { ... }` 里补：

```js
      cluster, clusterLogRef, stateLabel, duration, clusterTest, clusterToggle,
      clusterRun, clusterKill, clusterOpenLog, clusterPreview, clusterResetPaths, clusterImport,
```

- [ ] **Step 5: 语法检查**

Run（提取内联脚本做 `node --check`，沿用你现有的 `C:\Users\lyy\AppData\Local\Temp\syntax.py`，若不存在则用浏览器验证）:
```
py -3.13 "C:\Users\lyy\AppData\Local\Temp\syntax.py"
```
Expected: 全部 `OK`

- [ ] **Step 6: 页面自检（MOCK=1）**

打开 `http://127.0.0.1:8000/?page=cluster`，Expected：
- 指标卡：HDFS `86.4 G / 120 G`、进度 72%、YARN `3 / 3`、运行中 `1`
- 连接条绿色「已连接」
- 10 行任务，展开后路径有默认值
- 点「运行」→ 状态变「运行中」，右侧日志逐行追加，进度到 100% 后变「成功」
- 勾选「完成后写入 MySQL」在 MOCK 下会真实写库（注意：会清空目标表）——**先用 `word_count` 之外的测试库验证**，或保持不勾

---

### Task 8: 离线回归（页面 + 主题 + 移动端）

**Files:** 无代码改动，仅验证

- [ ] **Step 1: 桌面 1440×900 六页遍历**

用现有 Playwright 脚本（`sci_final.py` 一类）打开 `dashboard / finance / textai / telecom / alert / cluster`，逐页记录 `document.documentElement.scrollWidth - clientWidth`。
Expected: 均为 0（无横向溢出）

- [ ] **Step 2: 集群页四态截图**

| 态 | 制造方式 | 预期 |
|---|---|---|
| 未连接 | 停掉 `CLUSTER_MOCK` 且集群不可达 | 红点 + 原文错误 + 运行按钮禁用 |
| 运行中 | MOCK 运行中截屏 | 蓝色徽标 + map/reduce 百分比 + 日志滚动 |
| 成功 | 等 3s | 绿色徽标 + 运行记录 1 行 |
| 失败 | 临时把 `JAR_DIR` 指向空目录再运行 | 红色徽标 + 日志尾部 `FileNotFoundError` |

- [ ] **Step 3: 深浅主题各截一张**

切换主题后检查：日志面板 `#f4f0e8`、输入框 `#fbf8f2`、徽标对比度 ≥ 4.5:1。
Expected: 无深色样式残留（尤其 `.cluster-log` 背景与文字色）

- [ ] **Step 4: 移动端 390×844**

Expected: `cluster-grid` 单列；日志高 260px；表格可横向滚动但不撑破页面；无横向溢出

- [ ] **Step 5: console error 采集**

Expected: 0 error（`favicon` 404 不计）

---

### Task 9: 真实集群联调（需用户明确同意后执行）

**Files:** 无代码改动

- [ ] **Step 1: 在用户确认后，把 `backend/.env` 的 `CLUSTER_MOCK` 改为 `0`，重启服务**

- [ ] **Step 2: 连接测试**

页面点「测试连接」Expected: `worker1` + `Hadoop 3.x.x` + 延迟

- [ ] **Step 3: 跑最小任务 `fcc_state`（不勾入库）**

Expected: 日志出现 `application_...`，结束后 `hdfs dfs -ls /data/output/fcc_state` 有 `part-r-00000`

- [ ] **Step 4: 预览输出，核对列格式**

点「预览输出」Expected: `CA<TAB>120` 形态的两列；若列数不符 → 改 `cluster_jobs.json` 的 `parser/columns`

- [ ] **Step 5: 勾选「完成后写入 MySQL」重跑**

Expected: 成功徽标 + 日志「已写入 MySQL：fcc_state N 行」；大屏「电信投诉分析」州级数字变化

- [ ] **Step 6: 停止能力验证**

启动 `word_count` 后立即点「停止」Expected: 状态「已停止」，`yarn application -list` 不再出现该 `application_`

---

## 自检记录

- **Spec 覆盖**：监控（Task 4/6）、10 jar 全量（Task 2/6）、单跑与可选入库（Task 5/7）、HDFS→MySQL（Task 5）、错误态（Task 8）、安全（Task 3 路径校验 / Task 1 凭据）、测试（Task 3/8/9）。
- **占位符**：无 TBD/TODO；所有代码步骤均给出可直接粘贴的实现。
- **类型一致性**：`run` 字典字段（`state/import_state/progress/app_id/lines/rows_imported`）在 Task 5 定义，Task 7 前端只读同名键；`_job_view` 已明确补 `default_input/default_output` 供 `clusterResetPaths` 使用。
- **已知偏差**：任务配置里 `word_count2` 与 `word_count` 同表，默认不入库，运行时若勾选会覆盖——页面已在该任务描述中写明。
