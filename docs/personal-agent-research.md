# Personal Agent 专项调研

日期：2026-11-04。研究对象：完整个人助手产品及其可嵌入运行时。

## 修正上一轮的比较方法

上一轮偏重框架与依赖数量。LangGraph 模板具备工具执行循环，不等于已经具备完整个人助手能力。Personal Agent 也不要求采用特定框架；应以实际行为验收，而非项目名称验收。

本项目需要跨任务、跨会话持续服务同一个人：维护个人资料与偏好、查找历史、选择不同生活工具、允许纠正和忘记、在真实操作前等待确认。自动学习 Skill、主动提醒、多渠道接入属于可参考能力，不因为上游提供就全部纳入第一版。

## 五个产品候选与工程判断

### 1. nanobot：优先做适配验证

[项目](https://github.com/HKUDS/nanobot)，MIT。

个人助手能力：WebUI、会话、个人资料、长期记忆、Skill、MCP 和调度。不是只有一个工具调用模板。

重要发现：官方提供异步 Python SDK，可调用 `run` / `stream`，观察结构化进度并使用稳定 session key。我们可能保留自己的 FastAPI 和适老前端，在同一进程嵌入运行时，无需整体 fork 所有界面。这里是文档支持的集成路径，不是已经验证的实现。

记忆包含用户资料、长期事实、会话与摘要；默认长期整理涉及 Consolidator 和 Dream。独立 SDK 不启动 Dream 调度。因此“嵌入 SDK 就自动得到全部网关功能”不成立。我们的家庭地址必须及时、确定地保存，不能等后台整理。

代价：当前默认依赖已包含文档处理、搜索等非必需包。关闭工具不等于减少安装依赖；不要为追求少几个包临时裁剪到破坏运行时。现有语音转写也不能直接当作豆包流式连续会话已支持。

判定：完整 Personal Agent 路线首选验证对象，是否最终采用取决于安装和扩展实验。

依据：[SDK](https://github.com/HKUDS/nanobot/blob/main/docs/python-sdk.md)、[记忆](https://github.com/HKUDS/nanobot/blob/main/docs/memory.md)、[MCP 配置](https://github.com/HKUDS/nanobot/blob/main/docs/guides/configure-mcp-tools.md)、[配置](https://github.com/HKUDS/nanobot/blob/main/docs/configuration.md)、[依赖](https://github.com/HKUDS/nanobot/blob/main/pyproject.toml)。

### 2. Hermes Agent：重点备选

[项目](https://github.com/NousResearch/hermes-agent)，MIT。

个人助手能力：用户画像、持久记忆、历史检索、Skill、调度与 MCP。HTTP MCP 可配置认证头和工具筛选，适合进一步验证麦当劳接入。

默认记忆文件与 SQLite 历史相结合，不必为了基本记忆额外部署外部记忆服务。资料在会话开始时形成快照，写入后当前会话的即时可见性要按工具返回和状态处理验证，不能只测下一次启动。

网页层支持主题、UI 插件和 FastAPI 后端插件，值得评估用插件交付适老任务页，而不是维护上游大 fork。改变管理面板外观不等于完成录音、任务卡片和语音确认；仍需验证稳定的对话接入点。

代价：当前依赖／安装管理较复杂；pyproject 的声明范围与注释提到的最新 Python 运行策略存在细节差别，应按选定发布版安装验证，不能据范围推定 Python 3.11 路径可用。只安装所需 web、MCP 等能力，不默认安装 all。

判定：第二验证对象；如果插件方案能明显少写前后端胶水代码，可能超过 nanobot。

依据：[README](https://github.com/NousResearch/hermes-agent)、[记忆](https://hermes-agent.nousresearch.com/docs/user-guide/features/memory)、[MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp)、[网页扩展](https://hermes-agent.nousresearch.com/docs/user-guide/features/extending-the-dashboard)、[依赖](https://github.com/NousResearch/hermes-agent/blob/main/pyproject.toml)。

### 3. OpenClaw：完整个人助手参照，运行时备选

[项目](https://github.com/openclaw/openclaw)，MIT。

具有本地 Gateway、个人记忆、Skill／插件、多入口与设备能力。官方文档提供 HTTP 对话接口，以及 MCP 连接和审批配置。应区分当前文档／main 与具体稳定版：插件与 MCP 集成方式不能跨版本照搬。

可行方向：保留独立本地 Gateway，用我们的网页和业务适配对接，避免把整个仓库改成老人界面。这样可复用成品能力，但引入 Node 运行时和进程间状态协调。它并非天然要求部署 Redis 等服务，不能因为仓库大就将其描述为多服务重系统。

代价：能力范围很广；若再加 Python 后端，会出现两个运行时。MCP 的通用审批或命令审批不等于商品／金额／地址绑定的业务确认。

判定：若仅配置加薄界面即可复用，则值得；在 3—4 天内深改核心不优先。

依据：[README](https://github.com/openclaw/openclaw/blob/main/README.md)、[依赖](https://github.com/openclaw/openclaw/blob/main/package.json)、[记忆](https://docs.openclaw.ai/concepts/memory)、[HTTP 接入](https://docs.openclaw.ai/gateway/openai-http-api)、[MCP](https://docs.openclaw.ai/tools/mcp)、[命令审批](https://docs.openclaw.ai/tools/exec-approvals)。

### 4. Leon：方向相关，当前分支状态增加风险

[项目](https://github.com/leon-ai/leon)，MIT。

本地个人助手，强调语音、记忆、原生 Skill 和 agentic 执行，产品定位相关。README 明确说明 develop 是 2.0 Developer Preview，文档尚未准备好，旧指南多对应旧架构；master 是较稳定的旧版。这种分支差异使短期接入与排错成本较难预测。当前 develop 安装也涉及 Node、pnpm 和桥接组件。

判定：参考产品与 Skill 分层，不作为本次优先底座。此结论来自上游对当前版本的说明，不是认为它缺少 Personal Agent 能力。

依据：[当前 README](https://github.com/leon-ai/leon/blob/develop/README.md)、[package.json](https://github.com/leon-ai/leon/blob/develop/package.json)。

### 5. Khoj：偏个人知识助手，部署不符合本次轻量偏好

[项目](https://github.com/khoj-ai/khoj)，AGPL-3.0。

提供个人知识检索、自托管助手和自动化能力。当前官方 compose 包含 pgvector/PostgreSQL，并列出搜索、沙箱等服务；server 明确依赖 database。不是每个附加服务都必须启用，但默认路线仍重于本项目计划的文件／SQLite 存储。

判定：记忆与个人知识产品参考，不优先用于生活交易助手。AGPL 不妨碍开源面试项目，采用时需保留许可并履行相应开源要求；不将它列为“不允许使用”。

依据：[项目](https://github.com/khoj-ai/khoj)、[官方 compose](https://github.com/khoj-ai/khoj/blob/master/docker-compose.yml)。

## 修订后的推荐

先比较 nanobot 嵌入与 Hermes 插件两条完整 Personal Agent 复用路径，OpenClaw 为配置型备选。LangGraph 小模板降为轻量自建的回退方案，不继续作为已定首选。

这些顺序是静态调研判断，不是实测性能或开发耗时排名。依赖少仍然重要，但应比较“安装与改造总成本”，而非直接包数。不能为了减少框架包又自行补写完整的记忆、历史、Skill、任务恢复系统。

选定完整运行时后，不再叠加 LangGraph，除非出现它确实能解决的独立流程需求。优先复用一套 Agent 调度核心。

## Personal Agent 验收用例

1. 首次询问家庭地址并保存。重启、新建对话后说“回家”，能读取正确地址，不依赖旧对话仍在上下文。
2. “以后不吃辣”跨任务生效；“今天想清淡一点”不变成永久偏好。
3. 同一个助手能处理点餐、出行和提醒事项，缺参数时追问，工具不可用时明确说明。
4. 能查找历史任务，报告真实订单／提醒事项结果，而非只生成回复。
5. 能修改、忘记资料。用户可见记忆删除后，后续检索／摘要不得无提示重新恢复；历史是否一并删除需明确提供选项。
6. 交易工具不能直接绕过后端确认。原始下单工具不暴露给其他自由执行路径；改商品、金额、地址后旧确认失效。

固定业务流程也可以是 Personal Agent 的一部分。个性化、持续记忆与跨场景工具协作必须有实际验证，不能只在提示词中扮演“私人助手”。

## 下一步最小验证，仍不直接开发完整产品

对首选限定半天左右做安装、扩展和个人记忆验证；失败及时换备选。先验证：Mac 环境安装、火山兼容模型工具调用、跨会话记忆、远程 MCP 认证和工具筛选、结构化进度回传、确认闸门的可接入点。

订单确认应由我们的适配层绑定具体方案。仅在聊天里写“请确认”，或依赖工具描述中的危险提示，不算满足要求。

通过首选验证后再定底座，先用只读点餐工具核价，经过用户明确确认再验证真实订单创建。随后才开发任务页与语音主流程。

本轮仅访问公开源码与官方文档，没有安装／运行候选项目、调用真实账户或改变系统资料。尚未证明哪个候选能开箱即用满足豆包流式语音、订单确认和定位要求。
