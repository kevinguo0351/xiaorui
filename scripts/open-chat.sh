#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"
mkdir -p .local-data
ready() {
  curl --silent --fail --max-time 2 http://127.0.0.1:8000/api/health |
    python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("ok") and not d.get("read_only") else 1)' 2>/dev/null
}
if ! ready; then
  if curl --silent --fail --max-time 2 http://127.0.0.1:8000/api/health >/dev/null; then
    printf '%s\n' '8000 端口已有只读预览或其他服务。请先关闭它，再打开小瑞原版。' >&2
    exit 1
  fi
  if [[ ! -f frontend/dist/index.html ]]; then
    npm --prefix frontend ci
    npm --prefix frontend run build
  fi
  # Desktop shells may inherit preview flags; this entry always starts chat mode.
  nohup env XIAORUI_READ_ONLY=0 uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 \
    > .local-data/chat-preview.log 2>&1 < /dev/null &
  for ((attempt=0; attempt<60; attempt++)); do
    if ready; then break; fi
    sleep 1
  done
fi
if ! ready; then
  printf '%s\n' '小瑞尚未启动；请查看 .local-data/chat-preview.log。' >&2
  exit 1
fi
printf '%s\n' '正在打开小瑞原版：http://127.0.0.1:8000/'
exec xdg-open http://127.0.0.1:8000/
