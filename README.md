# 伴你 · Mac 本地生活助手

面向老人设计的 Personal Agent 工程项目。当前交付阶段是「真实自取菜单与报价 → 明确确认 → 受控订单执行」的本地网页切片，尚不是完整语音个人助手。

目前已通过麦当劳官方 MCP 的真实门店、菜单、套餐详情和核价联调。实际订单创建尚未验收，默认关闭。nanobot 与豆包的工具调用和跨进程记忆另有独立实验，尚未接入产品网页。

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
| `ARK_API_KEY` | 火山方舟文本模型凭证，目前用于独立 Agent 实验 |
| `ARK_BASE_URL` | 火山方舟调用地址，以账号地域为准 |
| `ARK_MODEL` | 已开通模型 ID 或调用示例中的 Endpoint ID |

在 [麦当劳官方 MCP 平台](https://open.mcd.cn/mcp) 登录手机号，进入控制台，按协议激活并复制 Token。服务地址和能力以 [官方指南](https://github.com/M-China/mcd-mcp-server) 及账号实际发现的工具为准。

火山模型在 [火山方舟控制台](https://console.volcengine.com/ark) 开通并创建 API Key。文本模型、语音识别、语音合成的权限和配置需分别核实。高德及苹果提醒事项尚未接入网页，目前无需为此配置额外凭证。

## 当前使用流程

1. 输入城市和地标，查询真实自取门店；这里不是自动定位。
2. 选择门店，读取当前可售菜单。
3. 选择商品及套餐内选项，生成真实报价。
4. 核对门店、商品、取餐方式和金额，再明确确认。

未开启订单执行时，页面可查询与核价，但不能创建订单，也不会显示虚假的「下单成功」。开启执行后，确认操作可能创建真实待支付订单；创建成功不等于支付成功。

价格和可售状态会变化。提交前重新核价，变化后重新确认。提交超时或重启遇到执行中订单时，按「结果未知」处理，不能盲目重复下单。

## 验证与范围

```sh
uv run python -m unittest discover -s tests -v
```

确认状态机的单元测试使用测试专用适配器验证边界，不访问真实账号、不创建订单。生产页面使用真实官方接口，没有运行时 mock 退路。单元测试通过不能代替真实订单联调。

- [实际麦当劳只读联调](docs/mcd-validation.md)
- [nanobot 与火山模型实验](docs/nanobot-validation.md)
- [Personal Agent 底座调研](docs/personal-agent-research.md)
- [当前范围与后续验收](docs/current-scope.md)
- [架构和确认流程](ARCHITECTURE.md)

语音连续对话、定位／高德、苹果提醒事项、用户长期记忆管理、Agent 自动规划和外送仍属后续阶段。第一条 A1 交易验收要求是：明确确认后创建真实订单，返回订单号与官方支付入口；当前尚未通过。

## 开源来源

本项目使用 FastAPI、React、官方 MCP Python SDK 等开源组件，底座研究参考 nanobot、Hermes 和 OpenClaw。是否最终嵌入 nanobot 尚待完整流程验证。引用上游代码时应保留对应许可和版权，项目不暗示麦当劳或其他服务的官方背书。
