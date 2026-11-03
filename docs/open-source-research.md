# 开源底座调研与选型建议

调研日期：2026-11-04。状态：待讨论的选型建议，未开始业务实现。

> 补充：用户要求优先比较完整 Personal Agent，而非仅比较框架。后续结论见 [Personal Agent 专项调研](personal-agent-research.md)。本篇推荐仅适用于轻量技术组件比较，不能当作最终产品底座定案。

## 结论

推荐以 LangGraph 官方 `react-agent` 小模板作为 Agent 核心参考，搭配独立语音与提醒事项适配器；不直接整体改造通用个人助手。这样保留已讨论的 React、FastAPI、SQLite 路线，减少与需求无关的代码与服务。此为源码和依赖清单层面的工程判断，尚未经过安装、性能或真实账号联调验证。

优先级：满足已确认需求 → 3—4 天落地 → 必需依赖少 → 容易解释和维护。

## 调研方法和证据范围

- 查看项目 README、依赖清单，以及部分核心实现和许可证。
- 四个项目保存了 GitHub 提交 SHA、提交时间、归档状态与对应依赖快照，见 `research/2026-11-04/`。其他项目本轮通过网页查看，未保存固定提交快照。
- 不安装、不执行下载的候选代码，不访问用户提醒事项，不创建交易订单。
- “直接依赖”是清单声明项，不是安装后的全部传递依赖、包大小、内存占用或服务进程数；带平台条件的声明未按当前平台过滤。不能只按数量衡量轻重。
- 当前仍有维护活动不等于版本稳定。真正采用时固定具体提交／发布版和依赖锁文件。

## 六个底座候选

| 项目 | 已核实的内容 | 对本项目的判断 |
| --- | --- | --- |
| [langchain-ai/react-agent](https://github.com/langchain-ai/react-agent) | MIT；Python 3.11+；7 个直接依赖声明；核心是模型与工具两个节点的循环 | 首选核心参考，缺少产品界面、语音、业务确认和持久化集成 |
| [HKUDS/nanobot](https://github.com/HKUDS/nanobot) | MIT；Python 3.11+；提供 WebUI、记忆、会话、MCP；本轮网页清单有 41 个直接依赖声明 | 最接近完整 Personal Agent 的备选，但当前功能面很广，裁剪和理解成本需要谨慎评估 |
| [lastmile-ai/mcp-agent](https://github.com/lastmile-ai/mcp-agent) | Apache-2.0；Python 3.10+；网页清单有 22 个直接依赖声明，包括 NumPy、scikit-learn 和遥测相关包 | MCP 工作流参考，第一版不同时叠加另一套 Agent 编排框架 |
| [pipecat-ai/pipecat](https://github.com/pipecat-ai/pipecat) | BSD-2-Clause；保存快照有 25 个直接依赖声明；支持多种音频传输与语音流水线 | 语音备选；音频运行库和框架学习成本高于简单云端桥接，需要以实际节省的工作量判断 |
| [livekit/agents](https://github.com/livekit/agents) | Apache-2.0；保存的 agents 子包有 32 个直接依赖声明，包含 AV、NumPy、遥测等 | 实时语音能力强；浏览器标准路径增加 LiveKit 服务或云端接入，不优先用于单机一问一答 |
| [Open-LLM-VTuber](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) | 主代码 MIT，Live2D 示例素材另有许可；Python >=3.10,<3.13；35 个直接依赖声明，包含 Torch、ONNX 和多个供应商 SDK | 完整语音产品参考；数字人和本地推理等能力超出本项目需要，不建议整体 fork |

源码依据：

- [react-agent 依赖](https://github.com/langchain-ai/react-agent/blob/main/pyproject.toml)、[核心图](https://github.com/langchain-ai/react-agent/blob/main/src/react_agent/graph.py)。ReAct 是推理与行动模式，与前端 React 不是同一个概念。
- [nanobot 依赖](https://github.com/HKUDS/nanobot/blob/main/pyproject.toml)、[WebUI 依赖](https://github.com/HKUDS/nanobot/blob/main/webui/package.json)、[MCP 实现](https://github.com/HKUDS/nanobot/blob/main/nanobot/agent/tools/mcp.py)。
- [mcp-agent 依赖](https://github.com/lastmile-ai/mcp-agent/blob/main/pyproject.toml)。Temporal、Redis 在可选项中，不应误写成必需服务。
- [Pipecat 依赖](https://github.com/pipecat-ai/pipecat/blob/main/pyproject.toml)。不要求所有人部署媒体服务；支持 FastAPI WebSocket 等路径。Torch 等部分包属于可选项，不应混入默认依赖判断。
- [LiveKit 依赖](https://github.com/livekit/agents/blob/main/livekit-agents/pyproject.toml)、[项目说明](https://github.com/livekit/agents)。控制台语音模式不等于浏览器部署路径。
- [VTuber 依赖](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber/blob/main/pyproject.toml)、[许可证](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber/blob/main/LICENSE)。

## 推荐模板实际能复用多少

react-agent 是 Agent 模板，不是可直接换皮的完整产品。默认包含 Tavily 搜索和多个模型供应商适配，拟移除本项目不用的部分。它的工具执行节点会直接运行工具，没有我们要求的订单确认闸门，不能直接接上创建订单工具交付。

可参考／复用：状态定义、模型工具绑定、工具结果回传、循环终止控制。运行时拟直接从 FastAPI 调用图，不把 Studio 或单独 Agent 平台作为产品运行前提；这一方式仍需最小验证。

必须新增：

1. Mac 启动与配置向导、环境检查、已构建前端。
2. 浏览器录音、重采样、流式转写、播报、自动接续和停顿处理。
3. 高德、麦当劳、提醒事项适配；工具白名单与参数校验。
4. 订单方案、确认绑定、过期处理、重复执行保护和超时核查。
5. SQLite 历史与长期资料；查询、覆盖确认、修改、删除。
6. 当前任务卡片、定位授权、坐标转换、任务切换与错误反馈。

因此，该路线减少的是底座复杂度，不能承诺省掉语音和交易业务工作。

## 两个专用组件候选

### 苹果提醒事项：优先验证 remindctl

[openclaw/remindctl](https://github.com/openclaw/remindctl) 使用 EventKit，支持增查改、完成任务、权限状态和 JSON 输出；MIT。README 要求 macOS 14+，源码构建另需 Swift 工具链；Package.swift 声明一个外部包 Commander。使用预编译工具与让用户自行编译是不同部署成本。

推荐先验证预编译版本／Homebrew 安装、首次授权和 JSON 读写，避免第一步就自行开发原生桥接。还需检查发布资产、签名／系统拦截和分发条件，不能只因 Swift 包少就认定零依赖。

后端仅通过固定可执行文件与参数数组调用，不用 shell=True，不允许模型拼任意命令；使用稳定 ID，写入后读回验证。

依据：[README](https://github.com/openclaw/remindctl/blob/main/README.md)、[Package.swift](https://github.com/openclaw/remindctl/blob/main/Package.swift)、[许可证](https://github.com/openclaw/remindctl/blob/main/LICENSE)。

### 豆包语音：doubao-speech 为轻量候选，尚不定案

[Hypnus-Yuan/doubao-speech](https://github.com/Hypnus-Yuan/doubao-speech) 是第三方客户端，不是火山官方 SDK。MIT，清单声明 click、PyYAML、websockets 三个直接依赖。README 提供接受异步字节流、返回增量识别结果的接口，适合验证浏览器音频桥接。

需要验证真实账号授权、资源 ID、增量结果、终包行为、取消、并发连接和 TTS 播放。网页音频拟统一为接口所需 PCM，避免因格式转换引入 FFmpeg；是否可行由联调确认。麦克风采集在浏览器，暂不安装该包的 PyAudio 可选项。

项目版本较早，README 的覆盖率和质量宣传不作为可靠性结论。若适配成本高，使用官方示例封装 WebSocket 协议；若轮次控制成为主要障碍，再评估 Pipecat。

依据：[README](https://github.com/Hypnus-Yuan/doubao-speech/blob/main/README.md)、[依赖](https://github.com/Hypnus-Yuan/doubao-speech/blob/main/pyproject.toml)。

## 推荐的最小运行形态

一个 Python 后端进程提供网页和 API，SQLite 保存数据；需要时调用一个本地提醒事项 CLI；云端调用火山引擎、麦当劳、高德。第一版不引入 Redis、PostgreSQL、向量数据库、容器或常驻媒体服务器。此处是目标架构，最终安装包数量需锁版本后解析才能得到。

## 开工前的验证关口

先通过小实验验证，不先搭全量产品。

1. 交易优先：麦当劳工具发现 → 自取门店 → 餐品详情 → 核价；用户明确确认后创建真实订单，核对订单号和官方支付入口。随后验证外送地址和配送链路。任何读取或创建失败都保留真实错误，不填假结果。
2. 语音：浏览器音频 → 豆包增量文字 → Agent 回复 → 豆包播报；验证追问后接续、长停顿、手动结束、停止播报再录音。
3. 提醒事项：权限检查 → 创建一条明确标识的测试任务 → 按 ID 读取 → 完成；先确认使用哪个列表。
4. 高德：Key 权限、POI／路线／天气、定位坐标转换；打车能力返回唤端链接，不等于叫车订单，单独验证 Mac 上的交接体验。
5. 安装：在干净环境检查 uv、Python、前端产物和 remindctl，记录首次授权步骤。仅能在当前机器运行不算部署验收。

没有账号凭证，无法判定 API 已跑通；当前调研没有使用真实账户、创建订单或修改系统资料。

若第一天未验证交易链路，应立即报告并比较可申请的替代服务；不能将真实查询或本地提醒事项当作用户已确认的交易验收替代品。
