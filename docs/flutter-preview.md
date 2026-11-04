# Flutter 陪伴式首版

首版新增 `mobile/`，复用 FastAPI / nanobot；React 首页与原分支保留。电脑 Web 预览先行，Android / iOS 尚未生成或验收。真实支付、下单、取消订单、叫车、买药、买菜、后台监听与提醒不在本轮范围。

## 启动

```bash
uv sync --locked
./scripts/install-desktop.sh  # 可选：应用菜单和桌面入口
./scripts/start-flutter.sh --build
```

打开 http://127.0.0.1:8000/flutter/ 。本机已安装应用菜单“小瑞”和桌面 `小瑞.desktop`，调用 `scripts/open-flutter.sh`；已有非只读服务占用 8000 时会拒绝复用，先关闭该服务再打开。首次构建需要 Flutter stable；本机 SDK 安装于 `~/develop/flutter`，用户 `~/.profile` 已添加 PATH，新登录 shell 生效。已有构建时直接 `./scripts/start-flutter.sh`。

启动脚本强制 `XIAORUI_READ_ONLY=1`，同时作用于 React 与 Flutter 的共享后端。关闭该进程后原启动方式保留。必须从同一来源访问，不用独立 Flutter 开发端口调用后端；麦克风需要 localhost 或安全来源。本机只监听 127.0.0.1，不开放通配跨域。

## 配置与边界

本机 `.env` 配置 `ARK_API_KEY` / `ARK_BASE_URL` / `ARK_MODEL`、`DOUBAO_SPEECH_API_KEY` 和 `MCD_MCP_TOKEN`，字段详见根 README。配置存在只表示凭据已填写，不证明服务权限或连接可用。凭据不进入 Flutter 包，也不写入日志。

只读启动采用明确工具白名单和宿主执行限制；即使原有交易开关为 true、访问旧页面或发送确认口令，也不能发起交易。模型仅开放麦当劳查询和任务记录查询。支付设置只展示“尚未开通”，不保存支付资料。

## 复现检查

```bash
cd mobile
flutter analyze
flutter test
flutter build web --base-href /flutter/ --no-web-resources-cdn
cd ..
uv run python -m unittest discover -s tests -q
```

音频使用 record 的 PCM16 流，单声道 16 kHz；Web 插件的 AudioWorklet 执行重采样并输出小端 PCM16。麦克风采集、ASR WebSocket 和 TTS 播放单独适配，客户端不发送 WebM 压缩数据。播报速度由播放器调速，沿用现有服务端参数；未把新的供应商语速参数声称为远端验证通过。

## 本轮实测

验证结果及未完成项目见 [验收记录](acceptance/flutter-preview.md)。缺少凭据时，真人语音、真实查询、远端超时和断网恢复不能算作通过；离线测试不代替这些验收。

SDK 安装依据：[Flutter 官方安装](https://docs.flutter.dev/install/manual)；录音实现依据：[record 包](https://pub.dev/packages/record)。客户端锁定依赖见 `mobile/pubspec.lock`，中文字体与 Apache 2.0 许可随包提供。
