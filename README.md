# 小瑞 · 面向老年人的 Personal Agent

**让老人说句话，就能更自主地安排生活。**

小瑞希望像一个熟悉老人、耐心可靠的年轻人在身边：通过自然语音帮助打车、点餐等生活事务，记住经过确认的习惯与兴趣，并在同意的范围内适时交流、分享喜欢的内容。家人前期协助设置，老人日常自主使用。

当前是 Mac 本地单用户项目，使用云端豆包模型与语音服务。已接入 nanobot、持久会话、显式个人资料管理、图片消息、单条语音与持续通话入口，以及麦当劳／瑞幸／滴滴场景。界面和受控执行层已有实现，真实查询与部分实验已通过；完整真人语音、三平台交易、后台提醒和干净环境交付仍待验收。主动了解偏好、抖音推荐和作品故事分享属于后续规划。

## 原始任务（原文保留）

> 实现一套可本地部署的 Personal Agent 服务。语言、模型、调度框架、Skill 全部自选；核心要求是尽可能对接真实外部 API（如高德、麦当劳等），而非 mock 接口，最终交付可一键本地跑起来的版本，附带设计说明，以 GitHub 链接的形式给出

原始文件：[面试任务原文](docs/original-task.md)。产品理想态是后续扩展，不能冒充原题的额外评分要求。

## 本地运行

需要 macOS、Python 3.12、[uv](https://docs.astral.sh/uv/)；构建前端需要 Node.js/npm。

```sh
# 仅首次且没有 .env 时复制；已有配置不要覆盖
cp .env.example .env
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

打开 [小瑞](http://127.0.0.1:8000)。也可双击根目录 `启动.command`；已附带前端构建时可跳过 npm 步骤。默认只允许本机访问，按单进程运行。

## 必要配置

凭据只填本机 `.env`，不提交 GitHub。文本与语音需要分别开通服务；配置存在不代表远端权限已通过。

| 配置 | 用途 |
| --- | --- |
| `ARK_API_KEY`、`ARK_BASE_URL`、`ARK_MODEL` | 豆包文本模型；模型 ID 使用账号已开通的值 |
| `ARK_CONTEXT_WINDOW_TOKENS` | 本地上下文预算，默认 64000，不得超过模型支持长度 |
| `DOUBAO_SPEECH_API_KEY` | 豆包语音 Key，与文本 Key 不同 |
| `DOUBAO_ASR_RESOURCE_ID` | 默认 `volc.seedasr.sauc.duration`，流式识别 2.0 |
| `DOUBAO_TTS_RESOURCE_ID`、`DOUBAO_TTS_VOICE` | 默认 `seed-tts-2.0`、`zh_female_vv_uranus_bigtts` |
| `MCD_MCP_TOKEN`、`LUCKIN_MCP_TOKEN`、`DIDI_MCP_KEY` | 三个平台各自的官方 MCP 凭据 |
| `MCD_ORDER_ENABLED`、`LUCKIN_ORDER_ENABLED`、`DIDI_ORDER_ENABLED` | 默认均为 `false`；开启也不能代替每个具体方案的二次确认 |

真实叫车需由本人或家人明确开启：在本机 `.env` 设置 `DIDI_ORDER_ENABLED=true` 后重启服务；启动命令中的同名环境变量优先于 `.env`，不能仍强制设为 `false`。开启只允许执行已核对且再次确认的当前方案，不会立即发单。确认前重新估价，车型、费用或接送点变化时再次确认；结果未知不重复提交。关联滴滴账号可能免密扣款。麦当劳与瑞幸的开关独立配置，无需同时开启。

官方入口：[火山方舟](https://console.volcengine.com/ark)、[豆包语音](https://console.volcengine.com/speech/service)、[麦当劳 MCP](https://open.mcd.cn/mcp)、[瑞幸 MCP](https://open.lkcoffee.com/mcp)、[滴滴 MCP](https://mcp.didichuxing.com/)。语音使用新版 `X-Api-Key` 鉴权，旧版 AppID/Token 不能直接代填。

若模型返回 `SetLimitExceeded`，检查方舟开通管理中的模型用量上限与安心体验模式；只充值余额可能无法解除该限制。缺凭据或接口失败时如实提示，不使用假菜单、假价格、假转录或假订单。

## 使用方式

- 左侧切换文字／单条语音；录音点击开始，再次点击停止发送。右侧加号可发图片或接通语音通话。处理中可继续补充，通话中可打字、插话或挂断。
- 说“查一下从北京国贸到北京西站打车大概多少钱”，或“帮我看看附近的麦当劳”。没有定位结果时先提供地标，再选择真实候选。
- 方案展示具体内容与费用后，按页面或准确口令确认。改条件使旧确认失效；叫车可能涉及关联账号免密扣款，付款与订单创建分别核实。
- 日常保留同一个持续对话，右上角“我的资料卡”填写家庭住址、本人电话、子女／主要联系人和备用联系人；核对后确认保存，聊天不能自动覆盖这些重要资料。
- 普通喜好可说“请记住……”“查看我的资料”“忘记……”，临时要求不自动永久保存。

## 文档导航

| 文档 | 唯一职责 |
| --- | --- |
| [原始任务](docs/original-task.md) | 原题原文，完整保留 |
| [产品理念](docs/product-identity.md) | 为谁做、理想体验、长期方向 |
| [当前状态与路线图](docs/roadmap.md) | 已有能力、缺口和下一步优先级 |
| [架构](ARCHITECTURE.md) | 模块分工、数据与执行边界 |
| [交互设计](docs/interaction-design.md) | 聊天、语音、图片和自然播报 |
| [服务边界](docs/services.md) | 麦当劳／瑞幸／滴滴的能力与限制 |
| [验收清单与证据](docs/acceptance.md) | 怎样算完成、实际证据和复现命令 |

`docs/acceptance/` 保存去凭证证据，`docs/research/` 保存原始调研材料，`experiments/` 保存复现脚本；它们不作为另一套规划。产品文档以此导航为准。

## 验证与开源

```sh
uv run python -m unittest discover -s tests -q
node --test frontend/tests/voice.test.cjs
```

离线测试不代替真实模型、外部接口、真人语音或真实交易验收。真实接口实验可能产生费用，真实交易必须先确认具体方案。

使用 FastAPI、React、官方 MCP Python SDK 和固定版本 nanobot；保留依赖原许可证，引用代码保留许可与版权。项目不暗示服务平台官方背书。
