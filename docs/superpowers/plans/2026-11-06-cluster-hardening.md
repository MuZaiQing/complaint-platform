# 集群控制台 · 可靠性与可观测性增强 · 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给集群控制台补上自动探测（Main-Class/输入/输出列/表结构）、过程可视化（阶段轴/环形进度/吞吐曲线）、结果导出 CSV 与运行稳定性（按 PID 停止/失败清理/连接自愈）。

**Architecture:** 新增 `backend/cluster_probe.py` 承载无 SSH、无 DB 的纯函数；`backend/cluster.py` 在既有 run 状态机上增加 `phase/phase_log/rate_series/pid/probe` 并把 preflight、导出、清理、详情串进现有路由；`backend/index.html` 仅改集群页，用内联 SVG 画图，不引图表库。

**Tech Stack:** FastAPI / paramiko / pymysql / Vue3(CDN) / 原生 CSS / 标准库 unittest

**背景文档:** `docs/superpowers/specs/2026-11-06-cluster-hardening-design.md`

**注意:** 项目不是 git 仓库（无 `.git`），因此本计划用「语法检查 + 单测 + 重启验证」代替 commit 步骤；若后续建仓，请每组任务后自行提交。

---

## 文件结构

| 文件 | 职责 | 变更 |
|---|---|---|
| `backend/cluster_probe.py` | MANIFEST、命令拼装、布局探测、列比对、输入检查、PID 解析、CSV 转义 | 新建 |
| `backend/tests/test_probe.py` | 上述纯函数的单测 | 新建 |
| `backend/cluster.py` | 阶段机、preflight、执行、停止、导出、清理、详情、自愈 | 修改 |
| `backend/index.html` | 集群页：可视化、导出、体检、清理、日志过滤、历史统计 | 修改 |
| `backend/tests/test_cluster.py` | 既有 11 项单测保持通过 | 只读验证 |

任务顺序：**1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9**。

---

### Task 1: 纯探测模块 + 单测

**Files:**
- Create: `backend/cluster_probe.py`
- Create: `backend/tests/test_probe.py`

- [ ] **Step 1: 先写失败测试**

`backend/tests/test_probe.py`：

```python
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cluster_probe as p


class TestManifest(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(p.main_class_from_manifest("Manifest-Version: 1.0\nMain-Class: a.B\n"), "a.B")

    def test_continued_line(self):
        text = "Manifest-Version: 1.0\nMain-Class: org.example.very.long.\n package.Main\n"
        self.assertEqual(p.main_class_from_manifest(text), "org.example.very.long.package.Main")

    def test_missing(self):
        self.assertIsNone(p.main_class_from_manifest("Manifest-Version: 1.0\n"))
        self.assertIsNone(p.main_class_from_manifest(""))

    def test_crlf_and_case(self):
        self.assertEqual(p.main_class_from_manifest("main-class: x.Y\r\n"), "x.Y")


class TestCommand(unittest.TestCase):
    def test_with_main_class(self):
        self.assertEqual(
            p.build_jar_command("/home/hadoop/jars/A.jar", "org.example.Main", "/in", "/out"),
            "hadoop jar /home/hadoop/jars/A.jar org.example.Main /in /out")

    def test_without_main_class(self):
        self.assertEqual(
            p.build_jar_command("/home/hadoop/jars/A.jar", None, "/in", "/out"),
            "hadoop jar /home/hadoop/jars/A.jar /in /out")


class TestLayout(unittest.TestCase):
    def test_tsv_ok(self):
        got = p.detect_layout(["CA\t446841\n", "TX\t301119\n"], 2)
        self.assertEqual((got["sep"], got["ncols"], got["mismatch"]), ("tsv", 2, False))
        self.assertEqual(got["sample"][0], "CA\t446841")

    def test_csv(self):
        got = p.detect_layout(['"AK",7508'], 2)
        self.assertEqual((got["sep"], got["ncols"]), ("csv", 2))

    def test_mismatch(self):
        got = p.detect_layout(["only-one-col"], 2)
        self.assertTrue(got["ncols"] == 1 and got["mismatch"])
        self.assertEqual(got["sep"], "csv")

    def test_empty(self):
        got = p.detect_layout([], 2)
        self.assertEqual(got["ncols"], 0)
        self.assertTrue(got["mismatch"])


class TestColumns(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(p.diff_columns(["a", "b"], ["a", "b", "c"])["ok"])

    def test_missing(self):
        got = p.diff_columns(["a", "missing"], ["a", "b"])
        self.assertFalse(got["ok"])
        self.assertEqual(got["missing"], ["missing"])

    def test_extra(self):
        self.assertEqual(p.diff_columns(["a"], ["a", "b"])["extra"], ["b"])


class TestInputCheck(unittest.TestCase):
    def test_cmd(self):
        self.assertEqual(p.input_check_cmd("/data/x.csv"),
                         "hdfs dfs -test -e /data/x.csv && echo OK || echo MISSING")

    def test_parse(self):
        self.assertTrue(p.parse_input_check("OK\n"))
        self.assertFalse(p.parse_input_check("MISSING\n"))
        self.assertFalse(p.parse_input_check(""))


class TestGuessPid(unittest.TestCase):
    def test_pick_latest(self):
        out = ("1111 java RunJar /home/hadoop/jars/A.jar /in /out\n"
               "2222 java RunJar /home/hadoop/jars/A.jar /in2 /out2\n"
               "3333 bash pgrep -af RunJar\n")
        self.assertEqual(p.guess_pid(out, "A.jar"), 2222)

    def test_ignore_other_jar(self):
        out = "1111 java RunJar /home/hadoop/jars/B.jar /in /out\n"
        self.assertIsNone(p.guess_pid(out, "A.jar"))

    def test_empty(self):
        self.assertIsNone(p.guess_pid("", "A.jar"))


class TestCsv(unittest.TestCase):
    def test_plain(self):
        self.assertEqual(p.csv_row(["CA", 446841]), "CA,446841\n")

    def test_escape(self):
        self.assertEqual(p.csv_row(['a,b', 'he said "hi"', "x\ny", None]),
                         '"a,b","he said ""hi""","x\ny",\n')


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 跑测试确认失败**

```
cd d:\fqh\backend
python -m unittest tests.test_probe -v
```

预期：`ModuleNotFoundError: No module named 'cluster_probe'`。

- [ ] **Step 3: 实现 `backend/cluster_probe.py`**

```python
# -*- coding: utf-8 -*-
"""集群任务的纯探测逻辑：不连 SSH、不连 DB，便于单测。"""
import re

_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")


def main_class_from_manifest(text: str):
    """从 MANIFEST.MF 文本取 Main-Class；支持 72 字节续行与 CRLF。"""
    if not text:
        return None
    lines = text.replace("\r\n", "\n").split("\n")
    joined = []
    for line in lines:
        if line.startswith(" ") and joined:   # 续行以单个空格开头
            joined[-1] += line[1:]
        else:
            joined.append(line)
    for line in joined:
        m = _KEY_RE.match(line.strip())
        if m and m.group(1).lower() == "main-class":
            return m.group(2).strip() or None
    return None


def build_jar_command(jar_remote: str, main_class, input_path: str, output_path: str) -> str:
    cls = f" {main_class}" if main_class else ""
    return f"hadoop jar {jar_remote}{cls} {input_path} {output_path}"


def detect_layout(sample_lines, expected_cols: int) -> dict:
    """判断输出分隔符与列数，并给出前 3 行样例。"""
    rows = [l.rstrip("\n") for l in sample_lines if l.strip()]
    if not rows:
        return {"sep": None, "ncols": 0, "mismatch": bool(expected_cols), "sample": []}
    first = rows[0]
    sep = "tsv" if "\t" in first else "csv"
    ncols = len(first.split("\t" if sep == "tsv" else ","))
    return {"sep": sep, "ncols": ncols, "mismatch": ncols != expected_cols,
            "sample": rows[:3]}


def diff_columns(cfg_cols, db_cols) -> dict:
    """配置列与数据库实际列比对；缺列即不可入库。"""
    cfg = list(cfg_cols or [])
    db = list(db_cols or [])
    missing = [c for c in cfg if c not in db]
    extra = [c for c in db if c not in cfg]
    return {"ok": not missing, "missing": missing, "extra": extra}


def input_check_cmd(path: str) -> str:
    return f"hdfs dfs -test -e {path} && echo OK || echo MISSING"


def parse_input_check(text: str) -> bool:
    return "OK" in (text or "").split()


def guess_pid(text: str, jar_name: str):
    """从 pgrep -af 输出里挑出命令行含该 jar 的最新 PID。"""
    best = None
    for line in (text or "").splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        if jar_name and jar_name in parts[1]:
            pid = int(parts[0])
            best = pid if best is None else max(best, pid)
    return best


def csv_row(fields) -> str:
    """按 RFC4180 转义一行 CSV（含结尾换行）。"""
    out = []
    for f in fields:
        s = "" if f is None else str(f)
        if any(ch in s for ch in (",", '"', "\n", "\r")):
            s = '"' + s.replace('"', '""') + '"'
        out.append(s)
    return ",".join(out) + "\n"


def schema_query_sql() -> str:
    return ("SELECT COLUMN_NAME FROM information_schema.columns "
            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s ORDER BY ORDINAL_POSITION")
```

- [ ] **Step 4: 跑测试确认通过**

```
cd d:\fqh\backend
python -m unittest tests.test_probe -v
```

预期：17 项全部 OK。

- [ ] **Step 5: 顺带跑既有单测，确认没影响**

```
cd d:\fqh\backend
python -m unittest tests.test_cluster -v
```

预期：11 项 OK。

---

### Task 2: run 增加阶段机与吞吐序列

**Files:**
- Modify: `backend/cluster.py`（`_new_run`、`_append_line`、`_finish` 附近）

- [ ] **Step 1: 在 `_new_run` 中初始化新字段**

把 `_new_run` 的 `run = {...}` 字典替换为：

```python
    now = datetime.now().isoformat(timespec="seconds")
    run = {
        "run_id": uuid.uuid4().hex[:12],
        "id": job["id"],
        "name": job["name"],
        "state": "queued",
        "phase": "queued",
        "phase_at": now,
        "phase_log": [{"phase": "queued", "at": now}],
        "heartbeat": None,
        "pid": None,
        "probe": {},
        "log_bytes": 0,
        "rate_series": [0] * 60,
        "rate_sec": None,
        "import_state": "pending" if import_flag else "off",
        "progress": None,
        "app_id": None,
        "lines": [],
        "started": now,
        "ended": None,
        "rows_imported": 0,
        "input": input_path,
        "output": output_path,
        "overwrite": overwrite,
        "import_to_mysql": import_flag,
        "error": None,
    }
```

- [ ] **Step 2: 新增 `_set_phase` 与 `_touch_rate`，并改写 `_append_line`**

在 `_new_run` 之后插入：

```python
RATE_BUCKETS = 60


def _set_phase(run: dict, phase: str) -> None:
    with _runs_lock:
        at = datetime.now().isoformat(timespec="seconds")
        run["phase"] = phase
        run["phase_at"] = at
        run["phase_log"].append({"phase": phase, "at": at})
        if len(run["phase_log"]) > 10:
            del run["phase_log"][:len(run["phase_log"]) - 10]


def _touch_rate(run: dict) -> None:
    """按秒分桶，保留最近 60 个桶的日志行数。调用方已持有 _runs_lock。"""
    now = int(time.time())
    last = run.get("rate_sec")
    if last is None:
        run["rate_sec"] = now
        run["rate_series"][-1] += 1
        return
    if now <= last:
        run["rate_series"][-1] += 1
        return
    gap = min(now - last, RATE_BUCKETS)
    run["rate_series"].extend([0] * gap)
    del run["rate_series"][:len(run["rate_series"]) - RATE_BUCKETS]
    run["rate_series"][-1] += 1
    run["rate_sec"] = now
```

把 `_append_line` 改为：

```python
def _append_line(run: dict, text: str) -> None:
    line = clean_ansi(text)
    if not line.strip():
        return
    with _runs_lock:
        run["lines"].append(line)
        if len(run["lines"]) > 5000:
            del run["lines"][:1000]
        run["heartbeat"] = datetime.now().isoformat(timespec="seconds")
        run["log_bytes"] += len(line.encode("utf-8")) + 1
        _touch_rate(run)
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
```

- [ ] **Step 3: `_execute` 各阶段写入 phase**

把 `_execute` 里 `run["state"] = "running"` 一行替换为：

```python
        _set_phase(run, "preflight")
        run["state"] = "running"
```

并在成功后、入库前加：

```python
        _set_phase(run, "finalizing")
        _finish(run, "success")
        _set_phase(run, "done")
```

> 说明：`_finish` 只改 state 和 ended，`phase` 由 `_set_phase` 独立维护；Task 3 会把 preflight 真正插进来。

- [ ] **Step 4: 语法检查**

```
cd d:\fqh\backend
python -m py_compile cluster.py
```

预期：无输出、退出码 0。

---

### Task 3: preflight（Main-Class / 输入 / 输出）

**Files:**
- Modify: `backend/cluster.py`（`_execute` 及新增 `_preflight`、`_resolve_main_class`）

- [ ] **Step 1: 新增 `_resolve_main_class` 与 `_preflight`**

放在 `_ensure_jar` 之后：

```python
def _resolve_main_class(job: dict, jar_remote: str):
    """返回 (main_class, source)；两者都没有时抛错。"""
    if MOCK:
        return (job.get("main_class") or "org.example.Mock"), "config"
    rc, text = run_cmd(f"unzip -p {jar_remote} META-INF/MANIFEST.MF 2>/dev/null")
    if rc == 0:
        mc = main_class_from_manifest(text)
        if mc:
            return mc, "manifest"
    cfg = (job.get("main_class") or "").strip()
    if cfg:
        return cfg, "config"
    raise ValueError(f"jar 未声明 Main-Class，请在 cluster_jobs.json 为 {job['id']} 填写 main_class")


def _hdfs_exists(path: str) -> bool:
    _rc, out = run_cmd(input_check_cmd(path))
    return parse_input_check(out)


def _preflight(run: dict, job: dict) -> str:
    """执行前置检查；返回远端 jar 路径，失败抛 ValueError。"""
    _set_phase(run, "preflight")
    if MOCK:
        run["probe"] = {"main_class": job.get("main_class") or "org.example.Mock",
                        "main_class_source": "config", "input_check": "ok",
                        "output_existed": False, "layout": None, "schema": None,
                        "checked_at": datetime.now().isoformat(timespec="seconds")}
        return f"{JAR_REMOTE_DIR}/{job['jar']}"
    jar_remote = f"{JAR_REMOTE_DIR}/{job['jar']}"
    _rc, _out = run_cmd(f"ls -l {jar_remote}", slot="exec")
    if _rc != 0:
        _set_phase(run, "uploading")
    jar_remote = _ensure_jar(job)

    main_class, source = _resolve_main_class(job, jar_remote)

    if not _hdfs_exists(run["input"]):
        raise ValueError(f"输入路径不存在：{run['input']}")

    out_exists = _hdfs_exists(run["output"])
    run["probe"] = {
        "main_class": main_class, "main_class_source": source,
        "input_check": "ok", "output_existed": out_exists,
        "layout": None, "schema": None,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    if out_exists and not run["overwrite"]:
        raise ValueError("输出目录已存在，请勾选「覆盖输出目录」或先清理输出")
    if out_exists and run["overwrite"]:
        run_cmd(f"hdfs dfs -rm -r -skipTrash {run['output']} 2>/dev/null", slot="exec")
    return jar_remote
```

- [ ] **Step 2: 改写 `_execute` 用 preflight 与 `build_jar_command`**

把当前 `_execute` 的函数体（从 `if run["state"] == "killed"` 到 `_finish(run, "success")` 之前）替换为：

```python
        if run["state"] == "killed":
            return
        run["state"] = "running"
        jar_remote = _preflight(run, job)
        cmd = build_jar_command(jar_remote, run["probe"]["main_class"],
                                run["input"], run["output"])
        _append_line(run, f"$ {cmd}")
        threading.Thread(target=_capture_pid, args=(run, job), daemon=True).start()
        _set_phase(run, "submitting")
        rc = _stream_run(cmd, run)
        if run["state"] == "killed":
            return
        _set_phase(run, "finalizing")
        if rc != 0:
            _clean_failed_output(run)
            _finish(run, "failed", f"MR 退出码 {rc}")
            return
        _probe_layout(run, job)
```

> `_capture_pid`、`_clean_failed_output`、`_probe_layout` 在 Task 4/5 实现；本步先把 `_execute` 结构改好，运行会因缺函数报 NameError，Task 5 结束后再整体启动。

- [ ] **Step 3: 语法检查（允许此时函数未定义，py_compile 只查语法）**

```
cd d:\fqh\backend
python -m py_compile cluster.py
```

预期：退出码 0。

---

### Task 4: 输出布局探测 + 入库列校对 + 失败清理

**Files:**
- Modify: `backend/cluster.py`（新增 `_probe_layout`、`_clean_failed_output`；改 `import_output`）

- [ ] **Step 1: 新增布局探测与失败清理**

```python
def _probe_layout(run: dict, job: dict) -> None:
    run["probe"] = run.get("probe") or {}
    try:
        _rc, text = run_cmd(f"hdfs dfs -cat {run['output']}/part-r-* 2>/dev/null | head -5")
        run["probe"]["layout"] = detect_layout(text.splitlines(), len(job["columns"]))
        if run["probe"]["layout"].get("mismatch"):
            _append_line(run, f"# 输出列数与配置不符：实际 {run['probe']['layout']['ncols']} 列，"
                              f"配置 {len(job['columns'])} 列，本次不自动入库")
    except Exception as e:
        _append_line(run, f"# 输出布局探测失败：{e}")


def _clean_failed_output(run: dict) -> None:
    """只清理本次 run 新建的输出目录；原本已存在的不碰。"""
    probe = run.get("probe") or {}
    if probe.get("output_existed"):
        return
    out = run.get("output")
    if not out:
        return
    rc, text = run_cmd(f"hdfs dfs -rm -r -skipTrash {out} 2>/dev/null")
    if rc == 0:
        _append_line(run, f"# 失败清理输出目录：{out}")
```

- [ ] **Step 2: `import_output` 增加表结构校对**

在 `import_output` 取到 `cols` 之后插入：

```python
    if (run.get("probe") or {}).get("layout", {}).get("mismatch"):
        raise ValueError("输出列数与配置不符，拒绝入库")
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cur:
            cur.execute(schema_query_sql(), (DB_CONFIG["db"], table))
            db_cols = [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
    diff = diff_columns(cols, db_cols)
    if not diff["ok"]:
        raise ValueError(f"目标表 {table} 缺列：{diff['missing']}")
```

> 注意：学会新增一次连接查列，随后原有 `conn = pymysql.connect(**DB_CONFIG)` 保持不变，两段代码紧邻即可。

- [ ] **Step 3: 语法检查**

```
cd d:\fqh\backend
python -m py_compile cluster.py
```

预期：退出码 0。

---

### Task 5: 按 PID 停止 + 连接自愈

**Files:**
- Modify: `backend/cluster.py`（`_capture_pid`、`kill_job`、`run_cmd`、`status_snapshot`）

- [ ] **Step 1: 新增 `_capture_pid`**

```python
def _capture_pid(run: dict, job: dict) -> None:
    """任务启动后约 1 秒内抓 RunJar 进程号，取不到不影响运行。"""
    for _ in range(4):
        time.sleep(0.5)
        if run["state"] != "running" or run.get("pid"):
            return
        _rc, out = run_cmd("pgrep -af RunJar", slot="monitor")
        pid = guess_pid(out, job["jar"])
        if pid:
            run["pid"] = pid
            _append_line(run, f"# 已记录 PID {pid}")
            return
```

- [ ] **Step 2: `kill_job` 优先按 PID**

在 `if run.get("app_id"):` 分支之后、`# 本地模式` 注释之前插入：

```python
    jar = (load_job_configs().get(job_id) or {}).get("jar", "")
    pid = run.get("pid")
    if pid and jar:
        rc, args = run_cmd(f"ps -p {pid} -o args=")
        if rc == 0 and jar in args:
            run_cmd(f"kill {pid}")
            time.sleep(1)
            rc2, _ = run_cmd(f"ps -p {pid} -o pid=")
            if rc2 == 0:
                run_cmd(f"kill -9 {pid}")
            _append_line(run, f"# 已停止 PID {pid}")
            _finish(run, "killed")
            return {"ok": True, "pid": pid}
    if jar:
```

并把原有的 `jar = ...` 与 `if jar:` 两行删掉，避免重复定义；保留原有的 `[R]unJar` 兜底块。

- [ ] **Step 3: `run_cmd` 断连时丢弃 slot**

把 `except Exception as e:` 分支改为：

```python
    except Exception as e:
        with _client_lock:
            _clients.pop(slot, None)
        return 255, f"SSH_ERROR: {e}"
```

- [ ] **Step 4: `/status` 只在成功时缓存**

`status_snapshot` 里把：

```python
        data = _parse_status()
        _status_cache["at"] = time.time()
        _status_cache["data"] = data
        return data
```

改为：

```python
        data = _parse_status()
        if data.get("connected"):
            _status_cache["at"] = time.time()
            _status_cache["data"] = data
        return data
```

- [ ] **Step 5: 导入新模块并跑单测**

在 `cluster.py` 顶部 import 区加：

```python
from cluster_probe import (main_class_from_manifest, build_jar_command, detect_layout,
                           diff_columns, input_check_cmd, parse_input_check, guess_pid,
                           csv_row, schema_query_sql)
```

```
cd d:\fqh\backend
python -m py_compile cluster.py && python -m unittest tests.test_cluster tests.test_probe -v
```

预期：28 项 OK。

---

### Task 6: 新接口（detail / export / cleanup / log download）

**Files:**
- Modify: `backend/cluster.py`（路由区）

- [ ] **Step 1: 顶部补 import**

```python
from fastapi.responses import StreamingResponse, FileResponse
```

- [ ] **Step 2: 新增辅助函数**

放在 `_current_run` 附近：

```python
def _run_any(run_id: str):
    return RUNS.get(run_id) or next(
        (h for h in _history if h.get("run_id") == run_id), None)


def _successful_run(job_id: str, run_id=None):
    if run_id:
        r = _run_any(run_id)
        return r if r and r.get("state") == "success" else None
    for h in reversed(_history):
        if h["id"] == job_id and h["state"] == "success":
            if h["run_id"] in RUNS:
                return RUNS[h["run_id"]]
            if h.get("output"):
                return h       # 后端重启后仍可用历史记录里的输出路径导出
    return None


def _elapsed_sec(run: dict) -> int:
    try:
        start = datetime.fromisoformat(run["started"])
        end = datetime.fromisoformat(run["ended"]) if run.get("ended") else datetime.now()
        return max(0, int((end - start).total_seconds()))
    except Exception:
        return 0
```

- [ ] **Step 3: 新增四个路由**

```python
@router.post("/jobs/{job_id}/preflight")
def preflight_job(job_id: str):
    """单任务体检：不跑任务，只查 Main-Class、输入、输出、表结构。"""
    job = load_job_configs().get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    if MOCK:
        return {"ok": True, "main_class": job.get("main_class") or "org.example.Mock",
                "main_class_source": "config", "input_check": "ok",
                "output_existed": False, "layout": None, "schema": None}
    jar_remote = f"{JAR_REMOTE_DIR}/{job['jar']}"
    try:
        main_class, source = _resolve_main_class(job, jar_remote)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    in_ok = _hdfs_exists(job["default_input"])
    out_existed = _hdfs_exists(job["default_output"])
    schema = None
    try:
        conn = pymysql.connect(**DB_CONFIG)
        try:
            with conn.cursor() as cur:
                cur.execute(schema_query_sql(), (DB_CONFIG["db"], job["target_table"]))
                schema = diff_columns(job["columns"], [r[0] for r in cur.fetchall()])
        finally:
            conn.close()
    except Exception as e:
        schema = {"ok": False, "missing": [], "extra": [], "error": str(e)}
    return {"ok": True, "main_class": main_class, "main_class_source": source,
            "input_check": "ok" if in_ok else "missing",
            "output_existed": out_existed, "layout": None, "schema": schema,
            "checked_at": datetime.now().isoformat(timespec="seconds")}


@router.get("/runs/{run_id}/detail")
def run_detail(run_id: str, lines: int = 200):
    run = _run_any(run_id)
    if not run:
        raise HTTPException(404, "run 不存在")
    view = {k: v for k, v in run.items() if k != "lines"}
    series = (run.get("rate_series") or [0] * 60)[-10:]
    view["elapsed_sec"] = _elapsed_sec(run)
    view["log_rate"] = round(sum(series) / max(1, len(series)), 2)
    n = max(1, min(int(lines), 2000))
    return {"ok": True, "run": view, "lines": (run.get("lines") or [])[-n:]}


@router.get("/jobs/{job_id}/export")
def export_output(job_id: str, run_id: Optional[str] = None):
    job = load_job_configs().get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    run = _successful_run(job_id, run_id)
    if not run:
        raise HTTPException(409, "没有可导出的成功结果")
    out = validate_path(run["output"])
    _rc, _text = run_cmd(f"hdfs dfs -test -e {out}")
    if not MOCK and _rc != 0:
        raise HTTPException(404, "输出目录不存在")

    sep = "\t" if job.get("parser", "tsv") == "tsv" else ","
    filename = f"{job_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"

    def gen():
        yield "\ufeff" + csv_row(job["columns"])
        if MOCK:
            for line in ["CA\t446841", "TX\t301119"]:
                yield csv_row(line.split("\t"))
            return
        for line in _hdfs_lines(out):
            line = clean_ansi(line).rstrip("\n")
            if line.strip():
                yield csv_row(line.split(sep))

    return StreamingResponse(gen(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/jobs/{job_id}/cleanup")
def cleanup_output(job_id: str, path: Optional[str] = None):
    job = load_job_configs().get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    try:
        p = validate_path(path or job["default_output"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not p.startswith("/data/output/"):
        raise HTTPException(400, "只允许清理 /data/output 下的目录")
    if MOCK:
        return {"ok": True, "path": p}
    rc, out = run_cmd(f"hdfs dfs -rm -r -skipTrash {p}")
    if rc != 0:
        raise HTTPException(400, f"清理失败：{out.strip()}")
    return {"ok": True, "path": p}


@router.get("/runs/{run_id}/log/download")
def download_log(run_id: str):
    run = _run_any(run_id)
    path = (run or {}).get("log_file") or str(LOG_DIR / f"{run_id}.log")
    if not os.path.exists(path):
        raise HTTPException(404, "日志文件不存在")
    return FileResponse(path, media_type="text/plain; charset=utf-8",
                        filename=f"cluster_{run_id}.log")
```

- [ ] **Step 4: `/history` 与 `/log` 增加字段**

`history` 返回前为每条补：

```python
def _history_view(h: dict) -> dict:
    h = dict(h)
    h["phase"] = h.get("phase")
    h["duration_sec"] = _elapsed_sec(h) if h.get("ended") else None
    h["main_class"] = (h.get("probe") or {}).get("main_class")
    return h
```

把 `return {"ok": True, "runs": _history[-limit:][::-1]}` 改为：

```python
    return {"ok": True, "runs": [_history_view(h) for h in _history[-limit:][::-1]]}
```

`job_log` 的返回字典追加：

```python
            "phase": run["phase"], "phase_at": run["phase_at"],
            "heartbeat": run["heartbeat"], "pid": run["pid"], "probe": run.get("probe"),
```

`_finish` 写历史时保留 `probe` 与 `phase`，把字典推导改为：

```python
        _history.append({k: run[k] for k in
                         ("run_id", "id", "name", "state", "phase", "started", "ended",
                          "import_state", "rows_imported", "probe", "output")})
```

- [ ] **Step 5: 语法检查 + 单测**

```
cd d:\fqh\backend
python -m py_compile cluster.py && python -m unittest tests.test_cluster tests.test_probe -v
```

预期：28 项 OK。

---

### Task 7: 前端可视化（模板 + 样式）

**Files:**
- Modify: `backend/index.html:2237-2272`（任务行展开区与日志卡片）
- Modify: `backend/index.html`（CSS 追加区块）

- [ ] **Step 1: 在 `.cj-body` 内 `cj-last` 之前插入可视化块**

```html
                  <div class="cj-viz" v-if="cluster.detail[j.id]">
                    <div class="viz-phases">
                      <span v-for="ph in VIZ_PHASES" :key="ph.key"
                        class="viz-phase" :class="phaseCls(j.id, ph.key)">
                        {{ ph.label }}<i v-if="phaseAt(j.id, ph.key)">{{ phaseAt(j.id, ph.key) }}</i>
                      </span>
                    </div>
                    <div class="viz-body">
                      <div class="viz-ring">
                        <svg viewBox="0 0 44 44" width="44" height="44">
                          <circle cx="22" cy="22" r="18" class="ring-bg"></circle>
                          <circle cx="22" cy="22" r="18" class="ring-fg"
                            :stroke-dasharray="ringDash(j.id)" transform="rotate(-90 22 22)"></circle>
                        </svg>
                        <b class="mono">{{ ringPct(j.id) }}%</b>
                      </div>
                      <div class="viz-spark">
                        <svg viewBox="0 0 120 32" preserveAspectRatio="none">
                          <polyline :points="sparkPoints(j.id)" class="spark-line"></polyline>
                        </svg>
                        <span class="viz-spark-label mono">日志行/秒 · 近 60s</span>
                      </div>
                    </div>
                  </div>
```

- [ ] **Step 2: 在 `.cj-actions` 里补三个按钮**

在「恢复默认」按钮之后加：

```html
                    <el-button size="small" @click="clusterPreflight(j)">体检</el-button>
                    <el-button size="small" :disabled="!hasSuccess(j.id)"
                      @click="clusterExport(j)">导出</el-button>
                    <el-button size="small" @click="clusterCleanup(j)">清理输出</el-button>
```

- [ ] **Step 3: 日志卡片改造成可过滤/下载**

把日志卡片的 `<div class="cluster-log" ...>` 与标题替换为：

```html
            <div class="card-title">运行日志
              <span class="hint-tag mono">{{ cluster.logJob || '—' }}</span>
              <span class="cj-growth"></span>
              <input class="log-filter mono" v-model="cluster.logFilter" placeholder="过滤关键词" />
              <label class="cj-check"><input type="checkbox" v-model="cluster.logAuto" /> 自动滚动</label>
              <a class="log-dl" :class="{ 'is-off': !cluster.logRunId }"
                 :href="cluster.logRunId ? '/api/cluster/runs/' + cluster.logRunId + '/log/download' : 'javascript:void(0)'"
                 download>下载日志</a>
            </div>
            <div class="cluster-log" ref="clusterLogRef">
              <div v-if="!filteredLogs.length" class="cluster-log-empty">选择任务并运行后可查看日志</div>
              <div v-for="(l, i) in filteredLogs" :key="i" class="cluster-log-line mono" :class="logCls(l)">{{ l }}</div>
            </div>
```

- [ ] **Step 4: 历史卡片加统计与趋势**

在 `<div class="card-title">运行记录...</div>` 之后加：

```html
          <div class="hist-stats mono">
            成功率 {{ histStats.rate }}% · 平均耗时 {{ histStats.avg }} · 成功 {{ histStats.ok }} / 失败 {{ histStats.bad }}
            <svg class="hist-trend" viewBox="0 0 120 24" preserveAspectRatio="none">
              <polyline :points="histTrend" class="spark-line"></polyline>
            </svg>
          </div>
```

> 体检弹层紧跟历史卡片之后：

```html
        <el-dialog v-model="cluster.preflightOpen" title="任务体检" width="520px">
          <div v-if="cluster.preflight" class="preflight-body mono">
            <div>任务：{{ cluster.preflight.job.name }}</div>
            <div>Main-Class：{{ cluster.preflight.data.main_class || '—' }}
              （{{ cluster.preflight.data.main_class_source || '—' }}）</div>
            <div>输入：{{ cluster.preflight.data.input_check }}</div>
            <div>输出已存在：{{ cluster.preflight.data.output_existed ? '是' : '否' }}</div>
            <div>表结构：{{ cluster.preflight.data.schema && cluster.preflight.data.schema.ok ? '匹配' :
              '缺列 ' + ((cluster.preflight.data.schema && cluster.preflight.data.schema.missing) || []).join(', ') }}</div>
          </div>
        </el-dialog>
```

- [ ] **Step 5: 追加 CSS**

在 `/* ===== 集群控制台 ===== */` 区块末尾追加：

```css
/* ===== 集群控制台 · 增强 ===== */
.cj-growth { flex: 1; }
.cj-viz { border-top: 1px dashed var(--line); padding-top: 10px; margin-top: 10px; }
.viz-phases { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }
.viz-phase { font-size: 11px; color: var(--fg-3); padding: 2px 6px; border-radius: 4px; background: rgba(255,255,255,.04); }
.viz-phase i { font-style: normal; margin-left: 4px; opacity: .6; font-size: 10px; }
.viz-phase.is-past { color: var(--accent-cyan); background: rgba(0,220,255,.12); }
.viz-phase.is-now { color: #fff; background: var(--accent-cyan); animation: vizPulse 1.4s infinite; }
.viz-phase.is-bad { color: #ff6b6b; background: rgba(255,107,107,.14); }
@keyframes vizPulse { 0%,100% { opacity: 1; } 50% { opacity: .6; } }
.viz-body { display: flex; align-items: center; gap: 16px; }
.viz-ring { position: relative; width: 44px; height: 44px; }
.viz-ring svg { display: block; }
.ring-bg { fill: none; stroke: rgba(255,255,255,.12); stroke-width: 4; }
.ring-fg { fill: none; stroke: var(--accent-cyan); stroke-width: 4; stroke-linecap: round; transition: stroke-dasharray .4s; }
.viz-ring b { position: absolute; inset: 0; display: grid; place-items: center; font-size: 10px; }
.viz-spark { flex: 1; }
.viz-spark svg { width: 100%; height: 32px; display: block; }
.spark-line { fill: none; stroke: var(--accent-green); stroke-width: 1.4; }
.viz-spark-label { font-size: 10px; color: var(--fg-3); }
.log-filter { width: 120px; font-size: 11px; background: transparent; border: 1px solid var(--line); border-radius: 4px; padding: 2px 6px; color: var(--fg-1); }
.log-dl { font-size: 11px; color: var(--accent-cyan); margin-left: 8px; }
.log-dl.is-off { color: var(--fg-3); pointer-events: none; }
.cluster-log-line.is-error { color: #ff6b6b; }
.cluster-log-line.is-warn { color: #ffb454; }
.cluster-log-line.is-info { color: var(--fg-2); }
.hist-stats { display: flex; align-items: center; gap: 12px; font-size: 11px; color: var(--fg-3); margin-bottom: 8px; }
.hist-trend { width: 120px; height: 24px; }
.preflight-body { font-size: 12px; line-height: 1.9; }
html[data-theme="light"] .viz-phase { background: rgba(0,0,0,.05); }
html[data-theme="light"] .cluster-log-line.is-info { color: #555; }
@media (max-width: 900px) { .viz-body { flex-wrap: wrap; } .hist-trend { display: none; } }
```

- [ ] **Step 6: 结构检查**

打开页面确认模板能渲染：`cluster.detail` 为空时可视化块应隐藏。此时 `filteredLogs`/`histStats`/`hasSuccess` 等函数尚未定义，控制台会报 `not defined`，属预期，Task 8 补上后消失。

---

### Task 8: 前端交互逻辑

**Files:**
- Modify: `backend/index.html:4987-5146`（`cluster` reactive 与函数区）
- Modify: `backend/index.html:6643`（`return` 暴露）

- [ ] **Step 1: `cluster` reactive 增字段**

```js
    const cluster = reactive({
      connected: false, host: '', user: '', error: '',
      hdfs: { used: '—', total: '—', pct: 0 },
      nodes: { total: 0, active: 0 }, apps: { running: 0 }, success24: 0,
      jobs: [], history: [],
      open: {}, inputs: {}, outputs: {}, imports: {}, overwrites: {},
      detail: {}, logJob: '', logRunId: '', logLines: [], logOffset: 0,
      logFilter: '', logAuto: true, preflight: null, preflightOpen: false,
    });
    const VIZ_PHASES = [
      { key: 'preflight', label: '准备', weight: 5 },
      { key: 'uploading', label: '上传', weight: 10 },
      { key: 'submitting', label: '提交', weight: 5 },
      { key: 'running', label: '运行', weight: 70 },
      { key: 'finalizing', label: '收尾', weight: 10 },
      { key: 'done', label: '完成', weight: 0 },
    ];
```

- [ ] **Step 2: 新增可视化辅助函数**

在 `duration` 之后插入：

```js
    function runOf(id) { return cluster.detail[id] && cluster.detail[id].run; }
    function phaseCls(id, key) {
      const r = runOf(id); if (!r) return '';
      if (r.state === 'failed' && key === 'finalizing') return 'is-bad';
      if (r.state === 'killed' && key === 'running') return 'is-bad';
      const idx = VIZ_PHASES.findIndex(p => p.key === key);
      const cur = VIZ_PHASES.findIndex(p => p.key === (r.phase || 'queued'));
      if (idx === cur) return 'is-now';
      if (idx < cur) return 'is-past';
      return '';
    }
    function phaseAt(id, key) {
      const r = runOf(id); if (!r || !r.phase_log) return '';
      const hit = r.phase_log.find(p => p.phase === key);
      return hit ? hit.at.slice(11, 19) : '';
    }
    function ringPct(id) {
      const r = runOf(id); if (!r) return 0;
      if (r.state === 'success' || r.phase === 'done') return 100;
      if (r.progress) return Math.min(99, Math.round(r.progress.map * 0.6 + r.progress.reduce * 0.4));
      const cur = VIZ_PHASES.findIndex(p => p.key === (r.phase || 'queued'));
      return Math.min(99, VIZ_PHASES.slice(0, Math.max(cur, 0)).reduce((a, p) => a + p.weight, 0));
    }
    function ringDash(id) {
      const c = 2 * Math.PI * 18;
      return (c * ringPct(id) / 100).toFixed(1) + ' ' + c.toFixed(1);
    }
    function sparkPoints(id) {
      const s = (runOf(id) || {}).rate_series || [];
      if (!s.length) return '';
      const max = Math.max(1, ...s);
      return s.map((v, i) => `${(i / Math.max(1, s.length - 1)) * 120},${30 - (v / max) * 28}`).join(' ');
    }
```

- [ ] **Step 3: 新增详情轮询、导出、体检、清理与日志过滤**

```js
    async function clusterPollDetail() {
      if (!cluster.logJob || !cluster.logRunId) return;
      try {
        const d = await apiGet(`/api/cluster/runs/${cluster.logRunId}/detail`);
        if (!d.ok || !d.run) return;
        cluster.detail[cluster.logJob] = d.run;
        cluster.logLines = d.lines || [];
        const job = cluster.jobs.find(j => j.id === cluster.logJob);
        if (job) { job.state = d.run.state; job.progress = d.run.progress; }
        const el = clusterLogRef.value;
        if (el && cluster.logAuto && el.scrollTop + el.clientHeight >= el.scrollHeight - 40)
          el.scrollTop = el.scrollHeight;
      } catch (e) {}
    }
    async function clusterExport(j) {
      if (!hasSuccess(j.id)) return ElementPlus.ElMessage.warning('该任务还没有成功结果');
      window.open(API + `/api/cluster/jobs/${j.id}/export`, '_blank');
    }
    async function clusterPreflight(j) {
      try {
        const r = await fetch(API + `/api/cluster/jobs/${j.id}/preflight`, { method: 'POST' });
        const d = await r.json();
        cluster.preflight = { job: j, data: d };
        cluster.preflightOpen = true;
        ElementPlus.ElMessage[d.ok ? 'success' : 'error'](
          d.ok ? `体检通过：${d.main_class || '—'}（${d.main_class_source || '?'}）`
               : (d.error || d.detail || '体检失败'));
      } catch (e) { ElementPlus.ElMessage.error('体检失败：' + e.message); }
    }
    async function clusterCleanup(j) {
      if (!confirm(`确认清理输出目录？\n${cluster.outputs[j.id] || j.default_output}`)) return;
      try {
        const r = await fetch(API + `/api/cluster/jobs/${j.id}/cleanup`, { method: 'POST' });
        const d = await r.json();
        if (!r.ok || !d.ok) return ElementPlus.ElMessage.error(d.error || d.detail || '清理失败');
        ElementPlus.ElMessage.success('已清理 ' + d.path);
      } catch (e) { ElementPlus.ElMessage.error('清理失败：' + e.message); }
    }
    function logCls(l) {
      if (/\bERROR\b|Exception|FAILED/.test(l)) return 'is-error';
      if (/\bWARN\b/.test(l)) return 'is-warn';
      if (/\bINFO\b/.test(l)) return 'is-info';
      return '';
    }
    function hasSuccess(id) {
      return cluster.history.some(r => r.id === id && r.state === 'success');
    }
```

- [ ] **Step 4: 日志过滤与历史统计 computed**

在 `duration` 附近加：

```js
    const filteredLogs = computed(() => {
      const kw = (cluster.logFilter || '').trim().toLowerCase();
      return kw ? cluster.logLines.filter(l => l.toLowerCase().includes(kw)) : cluster.logLines;
    });
    const histStats = computed(() => {
      const rs = cluster.history;
      const ok = rs.filter(r => r.state === 'success').length;
      const bad = rs.filter(r => r.state === 'failed').length;
      const durs = rs.map(r => r.duration_sec).filter(v => typeof v === 'number');
      return { ok, bad, rate: rs.length ? Math.round(ok * 100 / rs.length) : 0,
               avg: durs.length ? Math.round(durs.reduce((a, b) => a + b, 0) / durs.length) + 's' : '—' };
    });
    const histTrend = computed(() => {
      const d = cluster.history.slice().reverse().map(r => r.duration_sec || 0);
      if (!d.length) return '';
      const max = Math.max(1, ...d);
      return d.map((v, i) => `${(i / Math.max(1, d.length - 1)) * 120},${22 - (v / max) * 20}`).join(' ');
    });
```

- [ ] **Step 5: 改造 `clusterOpenLog` / `clusterRun` / `startClusterPoll`**

```js
    async function clusterOpenLog(j) {
      if (!j || !j.id) return;
      cluster.logJob = j.id;
      const job = cluster.jobs.find(x => x.id === j.id);
      cluster.logRunId = (job && job.run_id) || '';
      cluster.logLines = []; cluster.logFilter = '';
      await clusterPollDetail();
    }
```

`clusterRun` 末尾追加 `cluster.logRunId = d.run_id;`，并把原来的 `await clusterPollLog(j.id)` 换成 `await clusterPollDetail()`。

`startClusterPoll` 的定时器体内把 `if (cluster.logJob) clusterPollLog();` 改为 `if (cluster.logJob && cluster.logRunId) clusterPollDetail();`。

- [ ] **Step 6: 去掉旧的 offset 轮询**

删除 `clusterPollLog` 函数（已被 detail 轮询替代），`cluster.logOffset` 字段可留但不再使用。

- [ ] **Step 7: 暴露给模板**

第 6643 行附近追加：

```js
      VIZ_PHASES, filteredLogs, histStats, histTrend,
      phaseCls, phaseAt, ringPct, ringDash, sparkPoints,
      clusterExport, clusterPreflight, clusterCleanup, logCls, hasSuccess,
```

- [ ] **Step 8: 页面回归**

刷新 `http://127.0.0.1:8000/?page=cluster`，检查：
- 展开任务不报 `xxx is not a function`；
- 运行 `timely_response` 时阶段轴、环形、曲线都会动；
- 日志过滤框输入 `INFO` 只剩 INFO 行；下载链接可用。

---

### Task 9: 全量回归与真实验收

**Files:** 无代码改动，只验证。

- [ ] **Step 1: 单测与语法**

```
cd d:\fqh\backend
python -m py_compile cluster.py cluster_probe.py && python -m unittest tests.test_cluster tests.test_probe -v
```

预期：28 项 OK。

- [ ] **Step 2: 重启后端（8000 端口旧进程不会自动加载新代码）**

```
$pid = (Get-NetTCPConnection -LocalPort 8000 -State Listen).OwningProcess
Stop-Process -Id $pid -Force
cd d:\fqh\backend
python main.py
```

预期：`Uvicorn running on http://127.0.0.1:8000`。

- [ ] **Step 3: 接口冒烟**

```
curl http://127.0.0.1:8000/api/cluster/jobs/timely_response/export -o D:\fqh\_tmp_timely.csv
curl -X POST http://127.0.0.1:8000/api/cluster/jobs/company_count/preflight
curl http://127.0.0.1:8000/api/cluster/jobs/timely_response/export
```

预期：CSV 首行为 `stat_month,complaint_count` 之外的表头（按该任务配置），第二行起有数据；preflight 返回 Main-Class 与 `input_check: ok`。

- [ ] **Step 4: 失败清理验证**

用不存在的输入提交 `state_count`（输入改 `/data/nonexistent.csv`）：应在数秒内 `failed`，错误含「输入路径不存在」，且不产生 `/data/output/state_count`。

- [ ] **Step 5: 页面验收**

按 spec §10 手动验收 1–9 逐条走一遍，记录结果；把测试产生的输出目录用页面「清理输出」删掉。

---

## 自检清单（写完计划后已逐项核对）

- spec §3.1 的 8 个函数 → Task 1 全部实现并单测。
- spec §4 字段（phase/phase_at/heartbeat/pid/log_bytes/phase_log/rate_series/probe）→ Task 2、Task 3。
- spec §5 六阶段与失败清理 → Task 2、Task 3、Task 4。
- spec §6 PID 停止与自愈 → Task 5。
- spec §7 四个新接口 → Task 6。
- spec §8 前端 10 项 → Task 7、Task 8。
- spec §9 边界与 §10 测试 → Task 9 覆盖。
