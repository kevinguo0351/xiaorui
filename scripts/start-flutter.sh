#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export XIAORUI_READ_ONLY=1
if ! command -v flutter >/dev/null 2>&1 && [[ -x "$HOME/develop/flutter/bin/flutter" ]]; then
  export PATH="$HOME/develop/flutter/bin:$PATH"
fi
if [[ "${1:-}" == "--build" ]] || [[ ! -f mobile/build/web/index.html ]]; then
  (cd mobile && flutter pub get && flutter build web --base-href /flutter/ --no-web-resources-cdn)
fi
printf '%s\n' '小瑞只读预览：http://127.0.0.1:8000/flutter/ （原 React 首页保留）'
exec uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
