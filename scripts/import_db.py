#!/usr/bin/env python3
"""投诉分析平台数据库一键入库（Windows/Linux 通用，Python 3.8+ 标准库）。

用法:
  python import_db.py [--file db/complaint_analysis.sql]
                      [--host 127.0.0.1] [--port 3306] [--user root]
                      [--password xxx] [--db complaint_analysis]
缺省值依次取: 命令行 > 环境变量(DB_HOST 等) > 内置默认。
未指定 --file 时依次查找 db/*.sql、dist/db/*.sql（取最新）。
dump 中的 CREATE DATABASE / USE 会被忽略，因此 --db 可指定任意目标库。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CANDIDATES = [
    r"C:\Program Files\MySQL\MySQL Server 8.0\bin\mysql.exe",
    r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe",
    r"C:\Program Files\MySQL\MySQL Server 8.1\bin\mysql.exe",
    r"C:\Program Files\MySQL\MySQL Server 5.7\bin\mysql.exe",
    "/usr/bin/mysql", "/usr/local/mysql/bin/mysql", "/usr/local/bin/mysql",
]

# SQL dump 自带的建库/切库语句会被剔除，保证 --db 指定的库真正生效
SKIP_SQL = re.compile(r"^(CREATE DATABASE|USE )", re.IGNORECASE)


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
        sql = None
        for d in (root / "db", root / "dist" / "db"):
            files = sorted(d.glob("*.sql"), key=os.path.getmtime)
            if files:
                sql = files[-1]
                break
        if sql is None:
            sys.exit("[失败] 未找到 .sql（已查找 db/ 与 dist/db/）")
    if not sql.exists():
        sys.exit(f"[失败] 文件不存在: {sql}")

    if not re.fullmatch(r"[A-Za-z0-9_]+", a.db):
        sys.exit(f"[失败] 库名只能包含字母、数字和下划线: {a.db}")

    mysql = find_mysql()
    env = dict(os.environ, MYSQL_PWD=a.password)
    base = [mysql, "-h", a.host, "-P", str(a.port), "-u", a.user,
            "--default-character-set=utf8mb4"]

    print(f"[信息] 建库 {a.db} @ {a.host}:{a.port}")
    try:
        subprocess.run(base + ["-e",
            f"CREATE DATABASE IF NOT EXISTS `{a.db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"],
            env=env, check=True)
    except subprocess.CalledProcessError:
        sys.exit(f"[失败] 建库失败，请确认账号 {a.user} 有 CREATE 权限")

    print(f"[信息] 导入 {sql} ...")
    # 逐行过滤 dump 里的 CREATE DATABASE / USE，避免数据被切回 dump 的原库名
    proc = subprocess.Popen(base + [a.db], stdin=subprocess.PIPE, env=env)
    try:
        with open(sql, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                if SKIP_SQL.match(line):
                    continue
                proc.stdin.write(line.encode("utf-8"))
        proc.stdin.close()
    except BrokenPipeError:
        pass  # mysql 已退出（如认证失败），错误信息由其自身打印
    if proc.wait() != 0:
        sys.exit("[失败] 导入失败，请检查上方 mysql 报错")

    out = subprocess.run(base + ["-N", "-e",
        "SELECT COUNT(*), COALESCE(SUM(table_rows),0) FROM information_schema.tables "
        f"WHERE table_schema='{a.db}'"], env=env, check=True, capture_output=True, text=True)
    tables, rows = out.stdout.split()
    print(f"[成功] 入库完成: {a.db} 共 {tables} 张表、约 {rows} 行")
    if int(tables) == 0:
        sys.exit("[失败] 库中没有任何表，SQL 文件可能不完整")


if __name__ == "__main__":
    main()
