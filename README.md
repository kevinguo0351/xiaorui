# 小瑞 · Mac 本地生活助手

面向老人设计的 Personal Agent 工程项目。当前交付阶段是「真实自取菜单与报价 → 明确确认 → 受控订单执行」的本地网页切片，尚不是完整语音个人助手。

目前已通过麦当劳官方 MCP 的真实门店、菜单、套餐详情和核价联调。实际订单创建尚未验收，默认关闭。网页 Agent 的运行时正在整合固定版本 nanobot，个人工作区、持久会话、权威资料与任务记录的实现和验收见 [底座整合说明](docs/foundation-integration.md)。

## 本地启动

可双击 `启动.command` 启动。需要 macOS、[uv](https://docs.astral.sh/uv/)；源码构建前端还需要 Node.js/npm。首次配置凭证后再启动；下面是手动启动步骤。

```sh
cp .env.example .env
```

已有 `.env` 时直接编辑，不要覆盖现有凭证。填写麦当劳 Token 后：

```sh
uv sync
cd frontend
npm install
npm run build
cd ..
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000>。若下载的交付版本已包含 `frontend/dist`，可跳过 Node.js 安装与前端构建。项目提供启动入口时，以启动脚本提示为准；首次下载依赖需要网络。

开发前端时可以在 `frontend` 中运行 `npm run dev`，其 `/api` 请求代理到本机 8000 端口。

## 配置

凭证仅放本机 `.env`，不提交 GitHub、不粘贴到聊天或日志。

| 变量 | 用途 |
| --- | --- |
| `MCD_MCP_TOKEN` | 麦当劳官方 MCP 的账号凭证，网页真实查询必需 |
| `MCD_ORDER_ENABLED` | 默认 `false`；只有明确要测试真实订单时才开启 |
| `ARK_API_KEY` | 网页对话 Agent 的文本模型凭证 |
| `ARK_BASE_URL` | 火山方舟调用地址，以账号地域为准 |
| `ARK_MODEL` | 已开通模型 ID 或调用示例中的 Endpoint ID |

在 [麦当劳官方 MCP 平台](https://open.mcd.cn/mcp) 登录手机号，进入控制台，按协议激活并复制 Token。服务地址和能力以 [官方指南](https://github.com/M-China/mcd-mcp-server) 及账号实际发现的工具为准。

火山模型在 [火山方舟控制台](https://console.volcengine.com/ark) 开通并创建 API Key。文本模型、语音识别、语音合成的权限和配置需分别核实。高德及苹果提醒事项尚未接入网页，目前无需为此配置额外凭证。

豆包语音开通、配置变量与验收限制见 [语音接入说明](docs/voice-integration.md)。需要独立的 `DOUBAO_SPEECH_API_KEY`，不能以方舟文本 Key 代替。缺少语音 Key 时仍可打字，不会使用假识别结果。

## 当前使用流程

1. 在底部输入框说出或输入“帮我买份麦当劳，35 元以内”；切换语音模式后点击开始，再点一次停止提交。
2. 小瑞通过模型补问城市和附近地点，调用真实门店搜索；这里不是自动定位。
3. 查看至多三张经真实核价的套餐卡片，用自然语言说“选第二份”，或点击卡片。不足三份不会凑数。
4. 选定后重新核价并展示确认方案，核对取餐门店与金额，再按页面进行明确确认。

网页对话由运行时与宿主共同管理：模型会话、展示记录、个人资料及任务状态分层保存。新对话只重置当前线程，个人资料独立管理。具体已通过的恢复与资料操作验收见底座整合说明。详细边界见 [Agent 接入说明](docs/agent-integration.md)。豆包语音真实合成音频经流式识别取得最终转录的闭环已通过；浏览器真人麦克风体验仍待验收。

未开启订单执行时，页面可查询与核价，但不能创建订单，也不会显示虚假的「下单成功」。开启执行后，确认操作可能创建真实待支付订单；创建成功不等于支付成功。

价格和可售状态会变化。提交前重新核价，变化后重新确认。提交超时或重启遇到执行中订单时，按「结果未知」处理，不能盲目重复下单。

## 验证与范围

```sh
uv run python -m unittest discover -s tests -v
```

确认状态机的单元测试使用测试专用适配器验证边界，不访问真实账号、不创建订单。生产页面使用真实官方接口，没有运行时 mock 退路。单元测试通过不能代替真实订单联调。

- [实际麦当劳只读联调](docs/mcd-validation.md)
- [底座整合与能力边界](docs/foundation-integration.md)
- [nanobot 与火山模型历史实验](docs/nanobot-validation.md)
- [Personal Agent 底座调研](docs/personal-agent-research.md)
- [当前范围与后续验收](docs/current-scope.md)
- [架构和确认流程](ARCHITECTURE.md)

免操作连续语音对话、定位／高德、苹果提醒事项、自动长期记忆整理、跨领域任务规划和外送仍属后续阶段。第一条 A1 交易验收要求是：明确确认后创建真实订单，返回订单号与官方支付入口；当前尚未通过。

## 开源来源

本项目使用 FastAPI、React、官方 MCP Python SDK 等开源组件，底座整合采用固定版本 nanobot；产品架构同时参考 Hermes 和 OpenClaw。nanobot 使用 MIT 许可，依赖的各项目保留其原许可证。引用上游代码时应保留对应许可和版权，项目不暗示麦当劳或其他服务的官方背书。
