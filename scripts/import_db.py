#!/usr/bin/env python3
"""投诉分析平台数据库一键入库（Windows/Linux 通用，Python 3.8+ 标准库）。

用法:
  python import_db.py [--file db/complaint_analysis.sql]
                      [--host 127.0.0.1] [--port 3306] [--user root]
                      [--password xxx] [--db complaint_analysis]
缺省值依次取: 命令行 > 环境变量(DB_HOST 等) > 内置默认。
未指定 --file 时依次查找 db/*.sql、dist/db/*.sql（取最新）。
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
