#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .local-data
ready() {
  curl --silent --fail --max-time 2 http://127.0.0.1:8000/api/health |
    python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("read_only") is True else 1)' 2>/dev/null
}
if ! ready; then
  if curl --silent --fail --max-time 2 http://127.0.0.1:8000/api/health >/dev/null; then
    printf '%s\n' '8000 端口已有非只读服务。请先关闭，再打开小瑞。' >&2
    exit 1
  fi
  nohup ./scripts/start-flutter.sh > .local-data/flutter-preview.log 2>&1 < /dev/null &
  for ((attempt=0; attempt<60; attempt++)); do
    if ready; then break; fi
    sleep 1
  done
fi
if ! ready; then
  printf '%s\n' '小瑞尚未启动；请查看 .local-data/flutter-preview.log。首次请先运行 ./scripts/start-flutter.sh --build。' >&2
  exit 1
fi
exec xdg-open http://127.0.0.1:8000/flutter/
