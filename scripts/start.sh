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
