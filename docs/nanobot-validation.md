# nanobot 本地基础验证

日期：2026-11-04。版本：PyPI nanobot-ai 0.4.0；Python 3.12.13；macOS 26.5.1；arm64。

## 结论

可以继续作为首选做真实模型与业务联调。安装、SDK 导入、真实存储读写和工具注册通过；完整 Agent 对话尚未验证，不能称为产品已跑通。

## 环境与安装

现有 uv 可用。为避免改变全局 Python，使用项目内 `.research/nanobot/venv`；缓存位于 `/tmp/xiaorui-uv-cache`。未读取或复用 `~/.nanobot` 的配置、记忆与凭证。创建了独立 probe-workspace 和 probe-sessions。

固定安装版本 0.4.0，共安装 108 个发行包，包括传递依赖及 nanobot 本身。实际清单见 [依赖快照](research/2026-11-04/nanobot-probe/installed-requirements.txt)。这不是完整产品最终锁文件，也不表示其他平台解析结果相同。

```sh
uv --cache-dir /tmp/xiaorui-uv-cache venv --python /opt/homebrew/bin/python3.12 .research/nanobot/venv
uv --cache-dir /tmp/xiaorui-uv-cache pip install --python .research/nanobot/venv/bin/python nanobot-ai==0.4.0
```

以上 Python 路径是本机已有路径，不是未来交付启动脚本。

## 已通过的本地检查

| 检查 | 结果 | 证明边界 |
| --- | --- | --- |
| 安装并导入 Nanobot SDK | 通过 | 尚未初始化完整 Agent 或连接模型 |
| 写入长期记忆，另启 Python 进程读取 | 通过 | 存储持久化，不代表模型能自动提取或召回 |
| 写入历史会话，另启进程读取 | 通过 | 存储持久化，不代表完整对话恢复 |
| 注册自定义只读工具并读取实际文件 | 通过 | 工具注册／执行接口可用，尚未由模型选择执行 |
| 拒绝不符合工具参数的调用 | 通过 | 普通参数校验，不等于交易授权检查 |
| 注销工具 | 通过 | 注册表可移除工具，完整运行时的默认工具管理仍需验证 |

脚本：[experiments/nanobot_probe.py](../experiments/nanobot_probe.py)。写、读使用两个独立进程：

```sh
.research/nanobot/venv/bin/python experiments/nanobot_probe.py write
.research/nanobot/venv/bin/python experiments/nanobot_probe.py read
```

结果：[write.json](research/2026-11-04/nanobot-probe/write.json)、[read.json](research/2026-11-04/nanobot-probe/read.json)。仅写入隔离测试资料，不使用假模型、假外部接口或真实用户资料。

## 重要源码发现：默认 Hook 不适合单独承担授权

安装版本中的 `CompositeHook._for_each_hook_safe` 默认捕获回调异常并记录，后续可继续。它也有内部 `_reraise` 分支，但不应把未验证的内部开关当作交易授权契约。

证据：[实际安装源码片段](research/2026-11-04/nanobot-probe/hook-behavior.txt)。

订单二次确认必须在实际调用远端接口的工具内部或执行层强制校验，绑定用户、任务、参数、有效期和一次性授权。不能只在执行前 Hook 抛异常；不能只依赖模型提示词。直接下单工具和可绕过授权的 shell 路径也不能暴露给模型。

## 尚待真实验证

需要本地配置火山引擎文本模型凭证、兼容接口地址和已开通的模型 ID；麦当劳则需要用户本人申请的 Token。凭证不通过聊天收集，不写入调研证据或 GitHub。

后续按顺序：完整 SDK 初始化 → 模型真实回复／工具调用 → 新对话与新进程语义记忆 → 工具限制与确认执行层 → 麦当劳只读查询和核价 → 明确确认后真实创建订单。豆包语音和高德定位另行验证。

这轮没有调用付费 API、创建订单、访问提醒事项或启动常驻服务；新增的是可复现的基础实验和报告，未进入完整业务实现。

## 后续：真实火山模型联调

用户随后提供了火山示例与凭证，并用于实际接口验证。凭证仅保存于被忽略的 `.env`，权限设置为 0600；nanobot 的隔离配置只保存环境变量引用。本节取代前文“尚待真实模型验证”的对应状态。

- 官方 Responses 图片请求成功：返回 completed，耗时 12.85 秒，2061 tokens。仅证明请求可用，未独立评估图片回答准确性，也不是语音时延指标。
- nanobot + Responses：第一次因供应商扩展参数在 SDK 中的传法失败；调整后，模型成功调用资料工具并写入真实文件，但后续工具回传遭服务拒绝，提示 input 中不支持 async 字段。记录为完整流程失败，不修改上游代码。
- nanobot + Chat Completions：关闭深度思考，完整跑通模型选择工具、写入测试偏好、读取工具结果和回答，耗时 4.99 秒。
- 另启 Python 进程与全新 session：模型调用工具读取已存偏好并回答，耗时 4.57 秒。没有在该轮输入重复偏好内容。

以上时长包含本地初始化及模型／工具往返，只是单次观测，不是稳定性能保证。测试资料明确标记为虚构测试用户输入；文件存储、工具执行及云端模型都是真实实现，不使用 mock 服务。没有执行交易、支付或修改苹果提醒事项。

该实验显式要求模型调用工具，不证明无提示自动记忆、自动选择工具或记忆纠错已经实现。它验证了真实模型与框架、资料工具、跨进程存储之间的最小链路。

完整 SDK 初始化成功。实验通过内部 `_loop.tools` 收缩工具表，仅开放资料工具，证明此版本可验证但也引入私有接口依赖；产品实现需改用受控组合入口或固定版本的薄适配。业务授权和默认工具禁用仍是必须单独验证的环节。

拟将 Chat Completions 作为当前火山适配路径，保留 Responses 不兼容记录；尚未最终锁定底座或模型。实验脚本为 [nanobot_live_probe.py](../experiments/nanobot_live_probe.py) 和 [ark_probe.py](../experiments/ark_probe.py)。结果存于 `research/2026-11-04/nanobot-probe/ark-*.json`。
