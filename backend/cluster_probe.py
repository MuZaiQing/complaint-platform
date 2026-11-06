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
