#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")"

host="${AI_FACTOR_LAB_HOST:-127.0.0.1}"
port="${PORT:-8010}"

exec python -m uvicorn server.main:app --host "$host" --port "$port"
