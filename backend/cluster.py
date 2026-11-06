# -*- coding: utf-8 -*-
"""Hadoop 集群控制：SSH 驱动 MapReduce 任务，可选写回本地 MySQL。"""
import json
import os
import re
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional

import pymysql
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

from db_meta import DB_CONFIG, STATS_TABLES
from cluster_probe import (main_class_from_manifest, build_jar_command, detect_layout,
                           diff_columns, input_check_cmd, parse_input_check, guess_pid,
                           csv_row, schema_query_sql)

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


# ---------------- SSH ----------------
CLUSTER_HOST = os.getenv("CLUSTER_HOST", "10.15.7.101")
CLUSTER_PORT = int(os.getenv("CLUSTER_PORT", "22"))
CLUSTER_USER = os.getenv("CLUSTER_USER", "hadoop")
CLUSTER_PASSWORD = os.getenv("CLUSTER_PASSWORD", "")

_clients = {}
_client_lock = threading.Lock()

# 非登录 shell 不会加载 ~/.bashrc 里的 hadoop 环境变量，显式注入（可用 .env 的 CLUSTER_ENV 覆盖）
DEFAULT_ENV = ("export JAVA_HOME=/home/hadoop/software/jdk-17.0.21+9; "
               "export HADOOP_HOME=/home/hadoop/software/hadoop-3.5.0; "
               "export PATH=$JAVA_HOME/bin:$HADOOP_HOME/bin:$HADOOP_HOME/sbin:$PATH; ")
ENV_PREFIX = os.getenv("CLUSTER_ENV", DEFAULT_ENV)


def _wrap(cmd: str) -> str:
    return ENV_PREFIX + cmd


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
    chan = None
    try:
        c = get_client(slot)
        _in, out, err = c.exec_command(_wrap(cmd), timeout=timeout)
        chan = out.channel
        text = out.read().decode("utf-8", "ignore") + err.read().decode("utf-8", "ignore")
        return chan.recv_exit_status(), clean_ansi(text)
    except Exception as e:
        with _client_lock:
            _clients.pop(slot, None)
        return 255, f"SSH_ERROR: {e}"
    finally:
        if chan is not None:
            try:
                chan.close()      # 及时释放 channel，避免 sshd 连接数打满
            except Exception:
                pass


def _mock_cmd(cmd: str) -> str:
    if "hostname" in cmd:
        return "worker1\n"
    if "hadoop version" in cmd:
        return "Hadoop 3.3.6\n"
    if "dfs -df" in cmd:
        return ("Filesystem  Size  Used  Available  Use%  Mounted on\n"
                "hdfs://ns  120 G  86.4 G  33.6 G  72%  /\n")
    if "node -list" in cmd:
        return ("Total Nodes:3\n"
                "Node-Id  Node-State  Node-Http-Address  Number-of-Running-Containers\n"
                "worker1 RUNNING worker1:8041 1\n"
                "worker2 RUNNING worker2:8041 0\n"
                "worker3 RUNNING worker3:8041 2\n")
    if "application -list" in cmd:
        return ("Total number of applications (application-types: [] and states: "
                "[SUBMITTED, ACCEPTED, RUNNING]):1\n")
    if "hdfs dfs -cat" in cmd:
        return "CA\t120\nTX\t98\nFL\t77\n"
    if "ls -l" in cmd:
        return "-rwxr-xr-x 1 hadoop hadoop 12345 Jan 1 00:00 jar\n"
    return ""


def _parse_status() -> dict:
    rc_df, df = run_cmd("hdfs dfs -df -h")
    rc_node, nodes = run_cmd("yarn node -list")
    rc_app, apps = run_cmd("yarn application -list")

    hdfs = {"used": "—", "total": "—", "pct": 0}
    for line in df.splitlines():
        # 兼容两种尾部：带 Mounted on 列，或仅有 Use%（Hadoop 3.x 默认输出）
        m = re.match(r"\S+\s+(\d+\.?\d*\s*[KMGTP]?)\s+(\d+\.?\d*\s*[KMGTP]?)\s+"
                     r"(\d+\.?\d*\s*[KMGTP]?)\s+(\d+)%(?:\s+\S+)?$", line)
        if m:
            hdfs = {"total": " ".join(m.group(1).split()),
                    "used": " ".join(m.group(2).split()),
                    "pct": int(m.group(4))}
            break

    total = 0
    m = re.search(r"Total Nodes:(\d+)", nodes)
    if m:
        total = int(m.group(1))
    active = len(re.findall(r"\bRUNNING\b", nodes)) - (0 if "Node-State" in nodes else 0)

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


# ---------------- 运行态 ----------------
executor = ThreadPoolExecutor(max_workers=2)
RUNS = {}           # run_id -> dict
ACTIVE = {}         # job_id -> run_id（运行中）
LAST = {}           # job_id -> run_id（最近一次，结束后保留供查看日志）
_runs_lock = threading.Lock()
_history = load_history()


def _new_run(job: dict, input_path: str, output_path: str,
             overwrite: bool, import_flag: bool) -> dict:
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
    LOG_DIR.mkdir(exist_ok=True)
    run["log_file"] = str(LOG_DIR / f"{run['run_id']}.log")
    with _runs_lock:
        RUNS[run["run_id"]] = run
        ACTIVE[job["id"]] = run["run_id"]
        LAST[job["id"]] = run["run_id"]
    return run


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


def _mark_killed(run: dict) -> None:
    """先落 killed 状态，抢占随后到达的退出码。"""
    with _runs_lock:
        run["state"] = "killed"
    _set_phase(run, "killed")


def _finish(run: dict, state: str, error: Optional[str] = None) -> None:
    with _runs_lock:
        if run.get("state") == "killed" and state != "killed":
            return                      # killed 优先级最高，拒绝被退出码覆盖
        run["state"] = state
        if state in ("failed", "killed") and run.get("phase") != state:
            at = datetime.now().isoformat(timespec="seconds")
            run["phase"] = state
            run["phase_at"] = at
            run["phase_log"].append({"phase": state, "at": at})
        run["ended"] = datetime.now().isoformat(timespec="seconds")
        if error:
            run["error"] = error[-800:]
        ACTIVE.pop(run["id"], None)
        _history.append({k: run[k] for k in
                         ("run_id", "id", "name", "state", "phase", "started", "ended",
                          "import_state", "rows_imported", "probe", "output")})
    save_history(_history)


def _ensure_jar(job: dict) -> str:
    remote = f"{JAR_REMOTE_DIR}/{job['jar']}"
    if MOCK:
        return remote
    rc, _ = run_cmd(f"ls -l {remote}", slot="exec")
    if rc == 0:
        return remote
    local = JAR_LOCAL_DIR / job["jar"]
    if not local.exists():
        raise FileNotFoundError(f"本地缺少 jar：{local}")
    run_cmd(f"mkdir -p {JAR_REMOTE_DIR}", slot="exec")
    sftp = get_client("exec").open_sftp()
    try:
        sftp.put(str(local), remote)
    finally:
        sftp.close()
    return remote


def _manifest_from_local_jar(job: dict):
    """本地 jar 的 MANIFEST；远端缺 jar 或没有 unzip 时也能定 Main-Class。"""
    try:
        with zipfile.ZipFile(JAR_LOCAL_DIR / job["jar"]) as z:
            return z.read("META-INF/MANIFEST.MF").decode("utf-8", "ignore")
    except Exception:
        return None


def _resolve_main_class(job: dict, jar_remote: str):
    """返回 (main_class, source)；两者都没有时抛错。"""
    if MOCK:
        return (job.get("main_class") or "org.example.Mock"), "config"
    text = _manifest_from_local_jar(job)
    if text:
        mc = main_class_from_manifest(text)
        if mc:
            return mc, "manifest"
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
    main_class, source = _resolve_main_class(job, jar_remote)
    run["probe"] = {"main_class": main_class, "main_class_source": source,
                    "input_check": "checking", "output_existed": None,
                    "layout": None, "schema": None, "checked_at": None}

    if not _hdfs_exists(run["input"]):
        run["probe"]["input_check"] = "missing"
        raise ValueError(f"输入路径不存在：{run['input']}")
    run["probe"]["input_check"] = "ok"

    out_exists = _hdfs_exists(run["output"])
    run["probe"]["output_existed"] = out_exists
    if out_exists and not run["overwrite"]:
        raise ValueError("输出目录已存在，请勾选「覆盖输出目录」或先清理输出")
    if out_exists and run["overwrite"]:
        run_cmd(f"hdfs dfs -rm -r -skipTrash {run['output']} 2>/dev/null", slot="exec")

    run["probe"]["checked_at"] = datetime.now().isoformat(timespec="seconds")
    _rc, _out = run_cmd(f"ls -l {jar_remote}", slot="exec")
    if _rc != 0:
        _set_phase(run, "uploading")
    return _ensure_jar(job)


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


def _hdfs_lines(output_path: str) -> Generator[str, None, None]:
    if MOCK:
        for line in ["CA\t120\n", "TX\t98\n", "FL\t77\n"]:
            yield line
        return
    chan = get_client("monitor").get_transport().open_session()
    chan.exec_command(_wrap(f"hdfs dfs -cat {output_path}/part-r-*"))
    buf = b""
    try:
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
    finally:
        chan.close()


def import_output(run: dict, job: dict) -> int:
    table = job["target_table"]
    if table not in STATS_TABLES:
        raise ValueError(f"目标表不在白名单：{table}")
    cols = job["columns"]
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
    chan.exec_command(_wrap(cmd) + " 2>&1")   # hadoop 日志走 stderr，合并后前端才能看到
    buf = b""
    try:
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
    finally:
        chan.close()


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


def _execute(run: dict, job: dict) -> None:
    try:
        if run["state"] == "killed":
            return
        run["state"] = "running"
        jar_remote = _preflight(run, job)
        probe = run["probe"]
        # Hadoop 3.5 的 RunJar 在 MANIFEST 已声明 Main-Class 时，会把显式类名当作业务参数；
        # 因此只有 MANIFEST 缺省时才显式传类名，否则交给 hadoop 自己读。
        cls = None if probe.get("main_class_source") == "manifest" else probe.get("main_class")
        cmd = build_jar_command(jar_remote, cls, run["input"], run["output"])
        _append_line(run, f"$ {cmd}")
        threading.Thread(target=_capture_pid, args=(run, job), daemon=True).start()
        _set_phase(run, "submitting")
        rc = _stream_run(cmd, run)
        if run["state"] == "killed":
            return
        if rc != 0:
            _clean_failed_output(run)
            _finish(run, "failed", f"MR 退出码 {rc}")
            return
        _set_phase(run, "finalizing")
        _probe_layout(run, job)
        _finish(run, "success")
        _set_phase(run, "done")
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
        _append_line(run, f"ERROR {type(e).__name__}: {e}")
        _finish(run, "failed", f"{type(e).__name__}: {e}")
    finally:
        save_history(_history)


# ---------------- 路由 ----------------
class RunReq(BaseModel):
    input: str
    output: str
    overwrite: bool = False
    import_to_mysql: bool = False


def _current_run(job_id: str) -> Optional[dict]:
    """优先返回运行中的实例，其次返回最近一次（供查看日志/上次状态）。"""
    run_id = ACTIVE.get(job_id) or LAST.get(job_id)
    return RUNS.get(run_id) if run_id else None


def _run_any(run_id: str):
    return RUNS.get(run_id) or next(
        (h for h in _history if h.get("run_id") == run_id), None)


def _successful_run(job_id: str, run_id=None):
    if run_id:
        r = _run_any(run_id)
        return r if r and r.get("state") == "success" and r.get("output") else None
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


def _job_view(job: dict) -> dict:
    run = _current_run(job["id"])
    last = next((h for h in reversed(_history) if h["id"] == job["id"]), None)
    return {
        "id": job["id"], "name": job["name"], "jar": job["jar"], "description": job["description"],
        "default_input": job["default_input"], "default_output": job["default_output"],
        "input": (run or {}).get("input", job["default_input"]),
        "output": (run or {}).get("output", job["default_output"]),
        "import_to_mysql": (run or {}).get("import_to_mysql", job.get("import_enabled", False)),
        "state": (run or {}).get("state", "idle"),
        "import_state": (run or {}).get("import_state", "off"),
        "progress": (run or {}).get("progress"),
        "run_id": (run or {}).get("run_id"),
        "last_run": last,
    }


_status_cache = {"at": 0.0, "data": None}
_status_lock = threading.Lock()


def status_snapshot(ttl: float = 5.0) -> dict:
    """多标签页同时轮询时复用 5 秒内的结果，避免把 sshd 会话打满。"""
    with _status_lock:
        now = time.time()
        if _status_cache["data"] and now - _status_cache["at"] < ttl:
            return _status_cache["data"]
        data = _parse_status()
        if data.get("connected"):
            _status_cache["at"] = time.time()
            _status_cache["data"] = data
        return data


@router.get("/status")
def cluster_status():
    return {"ok": True, **status_snapshot()}


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
    run = _new_run(job, inp, out, req.overwrite, req.import_to_mysql)
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
    jar = (load_job_configs().get(job_id) or {}).get("jar", "")
    pid = run.get("pid")
    if pid and jar:
        rc, args = run_cmd(f"ps -p {pid} -o args=")
        if rc == 0 and jar in args:
            _mark_killed(run)          # 先置 killed，避免退出码先到被记成 failed
            run_cmd(f"kill {pid}")
            time.sleep(1)
            rc2, _ = run_cmd(f"ps -p {pid} -o pid=")
            if rc2 == 0:
                run_cmd(f"kill -9 {pid}")
            _append_line(run, f"# 已停止 PID {pid}")
            _finish(run, "killed")
            return {"ok": True, "pid": pid}
    if jar:
        # [R]unJar 写法避免 pkill 匹配到自己这条命令
        pattern = f"[R]unJar {JAR_REMOTE_DIR}/{jar}"
        _mark_killed(run)
        rc, out = run_cmd(f"pkill -f '{pattern}' && echo killed || echo not-found")
        _append_line(run, f"# 本地模式停止：{out.strip() or 'no-output'}")
    _finish(run, "killed")
    return {"ok": True, "app_id": None}


@router.get("/jobs/{job_id}/log")
def job_log(job_id: str, offset: int = 0):
    run = _current_run(job_id)
    if not run:
        return {"ok": True, "lines": [], "state": "idle", "offset": offset}
    lines = run["lines"][offset:]
    return {"ok": True, "lines": lines, "offset": offset + len(lines),
            "state": run["state"], "progress": run["progress"], "app_id": run["app_id"],
            "import_state": run["import_state"],
            "phase": run["phase"], "phase_at": run["phase_at"],
            "heartbeat": run["heartbeat"], "pid": run["pid"], "probe": run.get("probe")}


@router.get("/jobs/{job_id}/preview")
def preview_output(job_id: str):
    job = load_job_configs().get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    out = validate_path((_current_run(job_id) or {}).get("output") or job["default_output"])
    rc, text = run_cmd(f"hdfs dfs -cat {out}/part-r-* 2>/dev/null | head -20")
    return {"ok": rc == 0, "lines": text.splitlines(), "error": None if rc == 0 else text}


@router.post("/jobs/{job_id}/import")
def manual_import(job_id: str):
    job = load_job_configs().get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    run = _current_run(job_id) or {
        "output": job["default_output"], "import_state": "pending", "rows_imported": 0}
    try:
        n = import_output(run, job)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    run["import_state"] = "success"
    run["rows_imported"] = n
    return {"ok": True, "rows": n, "table": job["target_table"]}


def _history_view(h: dict) -> dict:
    h = dict(h)
    h["phase"] = h.get("phase")
    h["duration_sec"] = _elapsed_sec(h) if h.get("ended") else None
    h["main_class"] = (h.get("probe") or {}).get("main_class")
    return h


@router.get("/history")
def history(limit: int = 20):
    return {"ok": True, "runs": [_history_view(h) for h in _history[-limit:][::-1]]}


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
