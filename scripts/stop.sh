#!/usr/bin/env bash
# 投诉分析平台停止（Linux）
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
  if [ -n "$PIDS" ]; then
    kill $PIDS 2>/dev/null && echo "[成功] 已按端口停止 $PIDS"
    stopped=1
  fi
fi
[ "$stopped" = "0" ] && echo "[信息] 8000 无运行中的服务"
exit 0
