#!/usr/bin/env bash
PY="${PYTHON:-python3}"
exec "$PY" "$(dirname "$0")/import_db.py" "$@"
