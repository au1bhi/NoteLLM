#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

db_binding="$(docker compose port db 5432)"
db_host_port="${db_binding##*:}"
if [[ ! "$db_host_port" =~ ^[0-9]+$ ]] || ((db_host_port < 1 || db_host_port > 65535)); then
  echo "无法从 Compose 解析 PostgreSQL 宿主机端口：$db_binding" >&2
  exit 1
fi

cd backend
export POSTGRES_SERVER=127.0.0.1
export POSTGRES_PORT="$db_host_port"

# The wrapper applies the advisory-locked migration gate before FastAPI starts.
exec uv run bash scripts/start-service.sh fastapi dev app/main.py
