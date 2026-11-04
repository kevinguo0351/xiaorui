#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "$0")/.." && pwd)"
launcher_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$launcher_dir"
cat > "$launcher_dir/xiaorui.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=小瑞
Comment=陪伴式语音秘书 · 只读预览
Exec="$project_dir/scripts/open-flutter.sh"
Icon=$project_dir/mobile/assets/xiaorui.svg
Terminal=false
Categories=Utility;
DESKTOP
chmod +x "$launcher_dir/xiaorui.desktop"
if command -v xdg-user-dir >/dev/null 2>&1; then
  desktop_dir="$(xdg-user-dir DESKTOP)"
  if [[ -d "$desktop_dir" && "$desktop_dir" != "$HOME" ]]; then
    cp "$launcher_dir/xiaorui.desktop" "$desktop_dir/小瑞.desktop"
    chmod +x "$desktop_dir/小瑞.desktop"
    gio set "$desktop_dir/小瑞.desktop" metadata::trusted true 2>/dev/null || true
  fi
fi
printf '%s\n' '已安装“小瑞”应用入口。首次先运行 scripts/start-flutter.sh --build。'
