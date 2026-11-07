#!/usr/bin/env bash
# 导出 complaint_analysis 全量 SQL 到 dist/db/
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
