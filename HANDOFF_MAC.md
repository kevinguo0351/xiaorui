# 小瑞＋Poki：Mac 从零部署与实时语音改进 Handoff

更新日期：2026-11-05。交接给用户本人及下一位在 **Mac 本机**工作的开发者／Codex。本文是部署与后续开发交接，**不是已经在用户 Mac 部署成功的验收报告**。

快速导航：[代码状态](#1-从哪里接手代码分支与当前状态) · [Mac 安装](#4-mac-从零部署操作稿) · [语音升级](#5-语音升级持续自然对话而非只加快逐句播报) · [Tailscale](#6-tailscale远程访问和受控手机是两个链路)

## 0. 先看结论：网络与语音都要分层

**推荐顺序：Mac 本机小瑞 → 独立 Poki 真机观察 → GPT-Live 自然对话试验 → 受控接入手机工具 → Tailscale 远程访问。不要同时更换语音、手机执行和网络入口。**

Tailscale 分三种场景：

- **你人在外，受控 iPhone 留家：**设计上可通过 Tailscale 到家中 Mac，再由 Mac 控制家里 USB／同局域网 iPhone。优先用经过认证的 SSH 本地转发，实际仍须验收。
- **同一部被控 iPhone 随你出门：**不能承诺安装 Tailscale 就可控制。VPN 单播可达不等于 Bonjour／usbmuxd 发现、Apple 配对与开发者服务通道全部可用。此项单列研究，不算已支持。
- **外地手机只当小瑞网页客户端：**与“控制这部手机”是两件事。当前小瑞只允许回环 Host／精确 Origin，直接套 Tailscale Serve 会遇到拒绝；手机 HTTPS、身份认证与管理员设置授权是后续工程。

用户明确要接近 **GPT Live 的连续、自然、可插话体验**。首选试验方向为 **GPT-Live 长连接语音前台＋client delegation 接现有小瑞办事后端**；旧版 ASR→模型→口语改写→逐句 TTS 保留为基线与回退。不要把“逐句预取更快”写成已经达到 GPT Live。

### 本文标记

- **已知／源码事实**：本轮读过代码或官方文档；不等于用户设备已实测。
- **已完成验收**：明确写明环境及证据的项目。
- **设计／待开发**：需要后续改代码，不能只粘配置就宣称可用。
- **工程估计／建议目标**：排期或验收初值，不是已有性能成绩。

## 1. 从哪里接手：代码、分支与当前状态

| 项目 | 当前事实 |
|---|---|
| 当前用户 Fork | https://github.com/kevinguo0351/xiaorui |
| 原版工作分支 | `trial/local-run-rust-assessment`；应用代码基线 `60f4425da1c35dd7142570a50db3bbac481d20f2`，本文之后的交接提交以远端最新 HEAD 为准 |
| Flutter 分支 | `xiaohu_flutter`；`a39133b8fa66d8c1addbe0c5323dff21f8713806` |
| 原仓库 | https://github.com/perry112926-ai/xiaorui |
| 草稿 PR | https://github.com/perry112926-ai/xiaorui/pull/1 ，本轮核查为 OPEN／Draft，未合并；下一位开发者重新查询状态 |
| Poki 上游 | https://github.com/JosssphZhou/poki |
| Poki 审查基线 | `ea28be1872952a27b0dade59e6ccc6405854ef19`；只读克隆检查过，未安装／构建／连接真机；尚未在当前账号创建 Poki Fork |
| 开发验证环境 | Ubuntu Linux；不是用户 Mac，也不是 iPhone 实机 |
| 最近程序验证 | 后端 177 项、React 前端 45 项测试通过；生产构建通过；浏览器桌面与 390/320 像素宽度通过。Flutter 先前 11 项测试及 Web 构建通过 |
| 当前服务凭据 | 本轮本机五类内置服务均未配置；不代表用户其他机器或账号没有凭据。Mac 上须重新检查，不读取或复用别人的账号资料 |
| 实际已接入 | FastAPI／nanobot、React、豆包 ASR／TTS 网关、麦当劳／瑞幸／滴滴适配、家人配置页、受控确认层、独立 Flutter Web 预览 |
| **尚未接入** | **Poki 手机工具、GPT-Live、Seeduplex、手机独立运行、远程 HTTPS 认证入口、任意自定义 MCP 注册** |

当前原版有暖纸色界面、三套动态角色、改名／头像、长按输入框语音、状态条、取消录音、停止播报、我说完了、挂断；这些是现有功能，不必重做。

### 不可丢失的规则

- 先读项目 `AGENTS.md`；每轮完整修改验证后自动本地 commit，只提交本轮文件。保留其他修改，不重置工作区、不强推。
- 用户个人 ChatGPT 登录为默认。只有用户明确说“开 workflow”或“用公司 API”时才可进入单次公司流程；当前没有此授权。Windows 公司脚本不是 Mac 部署步骤，不能擅自把个人上下文复制进去。
- `.env`、`.local-data/`、Poki 配对文件、bearer token、屏幕内容与私人运行记录不进 Git，不粘到聊天或公共 PR。
- 保存 API 凭据不等于开启下单／叫车／取消／支付权限；保持三个 `*_ORDER_ENABLED=false`。
- 停止播报／挂断不是取消任务，更不是撤销订单；未知结果不自动重发。
- 不用假菜单、假价格、假转录或假连接状态替代远端调用。

## 2. 执行路线与停点

| 阶段 | 当轮只证明什么 | 交付证据 | 停止条件 |
|---|---|---|---|
| M0 环境 | Mac 具备依赖，源代码和版本正确 | 环境清单、HEAD、端口检查 | 非 Mac 或小瑞依赖版本不满足；完整 Xcode 缺失仅暂停 M2／Poki |
| M1 原版小瑞 | 本机页面、文字、字幕和播报按实际配置工作 | HTTP 状态、两轮对话、缺配置分支 | 缺凭据则只记界面与错误通过，不算真实闭环 |
| M2 独立 Poki | Mac 能观察指定测试 iPhone 页面 | 指定设备、当前 App、可人工核查屏幕 | 仅列出设备不算通过；锁屏、授权或开发者服务失败先停 |
| M3 自然语音 | 一种新实时提供方能持续来回说、插话与慢停顿 | 基线对比、10 场景记录、计费／会话释放 | 无模型权限、音频不断重复或业务事实失真则回退 |
| M4 手机适配 | 小瑞受控调用一个明确手机观察能力 | 任务 ID、来源与结果证据 | 不开放所有低层点击、付款或自动解锁 |
| M5 远程 | 指定操作者能安全访问家中服务 | SSH／网络／网页／语音分别验收 | 不放宽全部 Host／Origin，不开公网 Funnel |

**排期只是工程估计：**设备与账户已准备好时，先给 M1＋M2 一个 1–2 个工作日的验证窗口；实时语音先做单独原型再决定替换，另安排数日。Xcode 下载、系统升级、模型权限、设备配对及真机问题不包含在估计内。不要把排期写成承诺或完成标准。

## 3. 下一位开发者的第一条指令

把下面整段交给 Mac 上的 Codex：

> 读取本仓库 HANDOFF_MAC.md 和 AGENTS.md，先盘点这台 Mac 的真实环境与 Git 状态，核对远端 HEAD、草稿 PR 和 Poki 审查版本。先完成 M0／M1，再独立验证 M2；不要直接把 Poki 全部工具暴露给小瑞。优先为 GPT-Live＋现有 nanobot 的 client delegation 制作隔离原型，目标是连续对话和插话，而非仅缩短逐句 TTS。不要静默更换用户指定模型；若访问不到 GPT-Live，报告并按本文备用路径评估。所有真实凭据由用户在本机填写，不打印、不提交。Xcode 条款、手机信任／开发者模式／UI Automation、账号登录、远程登录与网络访问授权由用户亲自完成或明确批准；不要读取手机密码、自动付款或发消息。每次只完成一个可验收增量，记录真实证据和未完成项；源码更改验证后 commit。默认使用个人账户，不启动公司 API。结束时报告已做／没做／下一步，不把模拟或静态检查写成真机通过。


## 4. Mac 从零部署操作稿

以下命令尚未在用户 Mac 执行。先跑原版，Poki、Flutter 都是独立可选步骤；首次以前台终端运行，便于查看错误和停止。

### 4.1 先检查 Mac，不先安装一大套

在 Mac 本机终端执行。第一项不是 Darwin 就停下：

```sh
uname -s
sw_vers
uname -m
xcode-select -p
xcodebuild -version
command -v git
git --version
command -v brew
command -v uv
command -v node
command -v npm
```

- **小瑞本身**：Python 3.12（项目要求 `>=3.12,<3.13`）、uv、Node/npm；浏览器需要允许麦克风和音频播放。
- **只有还要安装 Poki 时**：macOS 15+、**完整 Xcode**（仅 Command Line Tools 不够）、Node.js 24+、Python 3、Rust/Cargo、ffmpeg/ffprobe，以及兼容设备的 Apple 开发者支持文件。当前要求以 Poki `docs/install.md` 和 `bin/setup` 为准。
- `uname -m` 用来分辨 Apple Silicon `arm64` 与 Intel `x86_64`。不要把 Linux 已安装目录、Linux Flutter SDK 或虚拟环境拷到 Mac 使用。

**必须由用户在 Mac 上亲自完成**：安装并打开 Xcode、同意许可和首次组件安装；系统管理员密码；Apple／GitHub／模型账户登录。若完整 Xcode 尚未准备好，暂停 M2／Poki 并记录这个具体卡点；M1 小瑞所需依赖满足时可以先继续，不把 Poki 环境写成已经完成。Xcode 路径应按本机实际安装位置选择；不要盲目运行需要 sudo 的修复命令。

#### 4.1.1 Homebrew、Node 和 uv

若 `brew` 不存在，**让用户在 Mac 浏览器打开 [Homebrew 官方站](https://brew.sh/)，自行运行当时页面显示的安装步骤**。不替用户输入管理员密码；不用搜索广告或第三方镜像的一键脚本。安装完成后按安装器实际显示的 Next steps 配置 shell。重新打开终端后确认：

```sh
brew --version
brew --prefix
```

缺少时再安装，不重复安装已满足的工具。下面使用 Node 24，既能构建小瑞，也满足审查版本 Poki 的要求：

```sh
brew install uv node@24
export PATH="$(brew --prefix node@24)/bin:$PATH"
uv --version
node --version
npm --version
```

`node@24` 是 keg-only；上面的 PATH 只作用于当前终端。另开终端时也需配置，或由用户按 Homebrew caveats 加入自己的 shell 配置，先检查已有内容，避免反复追加。

uv 可管理项目所需 Python，不修改系统 Python：

```sh
uv python install 3.12
```

依据：[uv 安装](https://docs.astral.sh/uv/getting-started/installation/)、[uv Python 管理](https://docs.astral.sh/uv/guides/install-python/)、[Homebrew node@24](https://formulae.brew.sh/formula/node@24)。

### 4.2 在用户自己的 fork 克隆原版，并核实最新 head

建议路径 `~/Developer/xiaorui`。以下克隆命令仅用于该目录尚不存在时；存在就检查目录和远程，不覆盖、不 reset、不 clean：

```sh
mkdir -p "$HOME/Developer"
git clone --branch trial/local-run-rust-assessment --single-branch \
  https://github.com/kevinguo0351/xiaorui.git "$HOME/Developer/xiaorui"
cd "$HOME/Developer/xiaorui"
git remote -v
git branch --show-current
git status --short
git fetch origin trial/local-run-rust-assessment
git rev-parse HEAD
git rev-parse origin/trial/local-run-rust-assessment
```

这里 clone 后的 `origin` 应为**自己的 fork**；这和旧 Linux 工作目录将 `fork` 命名为自己的 fork 不同，不能直接照搬旧远程名。若目录是已有 checkout，有未完成修改就保留，先说明再处理；干净目录只允许 `git pull --ff-only origin trial/local-run-rust-assessment` 更新，不强推、不自动解决未知冲突。

随后读当前 checkout 的 `AGENTS.md`、`README.md`、`ARCHITECTURE.md`、`docs/roadmap.md`、`docs/services.md`、`docs/acceptance.md`、`docs/acceptance/warm-design.md`。遵守项目“不提交密钥、只提交本任务改动、适当验证后本地 commit”的要求；纯部署无代码修改时，不为制造提交而改文件。

若本机已有 GitHub CLI 且用户已登录，可只读核实已有 PR：

```sh
gh pr view 1 --repo perry112926-ai/xiaorui \
  --json url,state,isDraft,headRefName,headRefOid,baseRefName,headRepositoryOwner
```

未安装／未登录则用浏览器查看上述 PR URL，不为部署另装 GitHub CLI 或创建新 PR。若 PR head 与自己的远程分支不一致，报告差异，先确认版本来源；不把旧 `60f4425` 当作永远最新。

### 4.3 安装锁定依赖，保留现有配置

在小瑞目录内：

```sh
cd "$HOME/Developer/xiaorui"
export PATH="$(brew --prefix node@24)/bin:$PATH"
uv sync --locked --python 3.12
npm --prefix frontend ci
npm --prefix frontend run build
```

项目已有 `uv.lock` 和 `frontend/package-lock.json`，先使用锁定依赖，不先升级库或重写技术栈。

只在 `.env` 不存在时创建，不打印文件内容：

```sh
cd "$HOME/Developer/xiaorui"
if [ ! -e .env ]; then
  (umask 077; cp .env.example .env)
fi
chmod 600 .env
git check-ignore .env .local-data/
```

不要运行 `cat .env`、`printenv`、`env` 或把 key 放在命令行参数／截图／聊天中。由用户在本机编辑器或小瑞“设置与家人协助”填写；无需把凭据提供给下一位 agent。

需要分别核实：

- 豆包文本：`ARK_API_KEY`、`ARK_MODEL`，服务地址按已开通账号设置；不要把语音 Key 当文本 Key。
- 豆包语音：`DOUBAO_SPEECH_API_KEY` 与账号开通的识别／合成资源及音色。
- 麦当劳、瑞幸、滴滴：各自 MCP 凭据与查询权限。
- `MCD_ORDER_ENABLED`、`LUCKIN_ORDER_ENABLED`、`DIDI_ORDER_ENABLED` 仍保持 false。

已有 `.env` 不覆盖，不从旧机器自动提取凭据；配置标记为“已填写”不等于远端连通或交易可用。

### 4.4 用 Mac 原生入口启动原版，避免只读预览串模式

**终端 A：运行小瑞，保持窗口打开。** 先检查 8000 端口：

```sh
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

无输出且非零退出通常表示没有监听者。若已有监听，先识别是不是用户正在运行的原版／Flutter 预览；不要 `killall`、`pkill` 或盲杀端口进程。关闭自己负责的前台实例时用它所在终端的 Control+C，然后确认端口释放。

原版启动明确覆盖可能继承的预览标志，三项执行开关也只在这个子进程内关闭：

```sh
cd "$HOME/Developer/xiaorui"
export PATH="$(brew --prefix node@24)/bin:$PATH"
umask 077
mkdir -p .local-data
chmod 700 .local-data
env XIAORUI_READ_ONLY=0 \
  MCD_ORDER_ENABLED=false LUCKIN_ORDER_ENABLED=false DIDI_ORDER_ENABLED=false \
  ./启动.command
```

`启动.command` 已审查：切到自身目录、创建运行目录（上述部署命令另行设置私有权限）、`uv sync --locked`、必要时构建前端、调用 macOS `/usr/bin/open`，最终在前台执行 uvicorn，监听 `127.0.0.1:8000`。若不希望它自动开浏览器，在上述 env 前缀中再加 `PERSONAL_AGENT_NO_BROWSER=1`，之后手动：

```sh
open http://127.0.0.1:8000/
```

**不要在 Mac 推荐 `scripts/open-chat.sh`**：它是 Linux 入口，最后使用 `xdg-open`。正常原版的 `XIAORUI_READ_ONLY=0` 允许配置与原版工具集；三项订单执行 false 才是本轮禁交易的执行边界，两者不是同一个开关。

**终端 B：只读检查服务。** 不输出密钥：

```sh
cd "$HOME/Developer/xiaorui"
curl --fail --silent --show-error --max-time 5 http://127.0.0.1:8000/api/health | \
  uv run --no-sync python -c 'import json,sys; d=json.load(sys.stdin); print({k:d.get(k) for k in ("ok","read_only","agent_configured","mcd_configured","order_execution_enabled")})'
```

预期至少 `ok=true`、原版 `read_only=false`、`order_execution_enabled=false`。其余配置标记按本机真实状态报告。不要让同一个 8000 端口同时跑多个 worker、原版和只读预览；不改为 `0.0.0.0`，不设置通配 CORS，不把 localhost 地址当作手机共享链接。

#### 4.4.1 小瑞的逐层验收

1. **页面**：真正加载暖色原版首页，角色图片不 404；390px 窄屏、头像设置、改名、返回、刷新都可用。
2. **文本**：未配置应明确报未接通；配置后发一条普通问候，核对真实模型响应。此步骤可能产生模型费用，不能用预置回答代替。
3. **语音**：浏览器权限由用户选择。检查短按打字、按住输入框说话／松开发送／上滑取消；拒绝权限、等待识别时取消、重复错误后再试、停止播报、持续通话的“我说完了”与挂断。挂断不声称已取消后端任务。
4. **一个官方查询**：用户提供真实城市／地标后查询门店或菜单，保留来源及实际返回；空结果、缺权限和超时如实显示。三项执行开关仍 false，不做真实交易。
5. **离线检查**（不替代前四项）：

```sh
cd "$HOME/Developer/xiaorui"
uv run --no-sync python -m unittest discover -s tests -q
node --test frontend/tests/*.test.cjs
```

每层记录实际版本、命令退出码、真实成功／失败／未测。不要将“网页打开”写成“完整真人语音与真实查询已验收”。

### 4.5 可选：独立安装 Poki MCP，不先换掉小瑞 Agent

只有用户仍希望增加 iPhone 自动化，才进入本节。小瑞原版验收失败时，先修小瑞，不拿 Poki 安装来替代收口。

#### 4.5.1 补齐 Poki 专用环境

完整 Xcode、首次组件和许可由用户完成后，检查：

```sh
xcodebuild -version
xcrun --find swiftc
xcrun --find clang
node --version
python3 --version
cargo --version
rustc --version
ffmpeg -version
ffprobe -version
```

缺 ffmpeg 时：`brew install ffmpeg`。缺 Rust 时，让用户查看 [Rust 官方安装页](https://rust-lang.org/tools/install/) 并自行完成 rustup 交互安装，再开新终端或按安装器指引加载环境；不要向 agent 提供管理员密码。Poki `bin/setup` 会再次核对工具，并构建其固定版本 idevice 依赖及原生桥。

#### 4.5.2 克隆隔离目录，读取当前安装说明

不存在目标目录时：

```sh
git clone https://github.com/JosssphZhou/poki.git "$HOME/Developer/poki-mcp"
cd "$HOME/Developer/poki-mcp"
git checkout --detach ea28be1872952a27b0dade59e6ccc6405854ef19
git rev-parse HEAD
git status --short
```

**执行 setup 前**重新读取该 checkout 的 `AGENTS.md`、`docs/install.md`、`docs/configuration.md`、`docs/physical-iphone.md`、`docs/verification.md`、`skills/poki-mcp/SKILL.md`。它们是应审查的上游安装资料，不授权忽略用户边界、索取密钥、操作未授权手机或自动付款。若较新版本提出新权限，先解释差异。本交接首轮明确要求独立前台终端，覆盖上游默认后台 daemon 的启动建议。

准备好后：

```sh
cd "$HOME/Developer/poki-mcp"
export PATH="$(brew --prefix node@24)/bin:$PATH"
./bin/setup
```

失败就记录失败工具和原因；不重跑未知手机动作。当前没有用户自己的 Poki fork；若后续确需改代码，再单独创建用户 fork／开发分支，保留 AGPL-3.0-only 与第三方许可，不把临时上游克隆说成已 fork。

#### 4.5.3 终端 C：前台运行 Poki daemon

另开终端，不停止小瑞终端 A。隔离 state，使用系统分配端口：

```sh
cd "$HOME/Developer/poki-mcp"
export PATH="$(brew --prefix node@24)/bin:$PATH"
export POKI_MCP_STATE_DIR="$HOME/Library/Application Support/Xiaorui/poki-mcp-state"
(umask 077; mkdir -p "$POKI_MCP_STATE_DIR")
chmod 700 "$POKI_MCP_STATE_DIR"
npm start -- --port 0
```

看到 `"event":"ready"` 只表示 daemon 监听完成。它只绑定 127.0.0.1；端口与 token 保存在私有 endpoint 文件。**不要打印或上传整个 `mcp.json`，不要把 token 写进浏览器、Git、聊天或全局环境文件。** 不手工暴露 HTTP 服务到公网／局域网。

#### 4.5.4 接入现有 Codex：MCP-only，不新增模型登录

本节适用于 Mac 上本来就在用 Codex 的用户。无需运行 `npm ci --prefix agent`、`poki login`，也不需要 OpenAI API Key 或单独的 Poki 模型账号。若本机 Codex 尚未安装／登录，由用户按官方安装和登录方式完成；不迁移旧机登录文件，不替用户输入登录信息。

先核实本机 CLI 参数和已有 entry，避免覆盖同名配置：

```sh
codex mcp add --help
codex mcp list
```

已有 `poki-mcp` 时，先检查它是否就是本次目录和 state；保留未知旧配置，不直接覆盖。确认无同名 entry 后，在终端 D：

```sh
cd "$HOME/Developer/poki-mcp"
export PATH="$(brew --prefix node@24)/bin:$PATH"
node --version
poki_checkout="$PWD"
poki_node="$(command -v node)"
poki_state_dir="$HOME/Library/Application Support/Xiaorui/poki-mcp-state"
codex mcp add poki-mcp --env "POKI_MCP_STATE_DIR=$poki_state_dir" \
  -- "$poki_node" "$poki_checkout/src/stdio.mjs"
```

这里 state 路径不是凭据；真正 daemon token 由 stdio bridge 在本机读取。使用已核实的 node 绝对路径，避免 GUI Codex 的 PATH 找不到 Homebrew node。

依据：[OpenAI 官方 MCP 文档](https://learn.chatgpt.com/docs/extend/mcp)及编写时本机 `codex mcp add --help` 的只读检查；新 Mac 的 CLI 仍需重查。不要输出用户已有 MCP entry 的 token 或凭据。

按 Poki 当前 `AGENTS.md` 把完整 skill 目录放入当前客户端的 skill 目录。目标存在就先检查，不覆盖。不存在时可用：

```sh
cd "$HOME/Developer/poki-mcp"
poki_skill_destination="${CODEX_HOME:-$HOME/.codex}/skills/poki-mcp"
if [ -e "$poki_skill_destination" ]; then
  printf '%s\n' '已有 poki-mcp skill；请先检查并保留本地修改，不自动覆盖。'
else
  mkdir -p "$(dirname "$poki_skill_destination")"
  cp -R skills/poki-mcp "$poki_skill_destination"
fi
```

读取安装后的 `SKILL.md`，重启或新开 Codex 会话加载新工具。接入 Codex 成功不等于接入了小瑞 nanobot；小瑞到 Poki 的宿主只读适配器仍是后续开发任务。

#### 4.5.5 手机准备必须由用户完成，准备完才运行设备命令

**在任何设备命令（包括列表发现）之前，先获得用户对这台手机已准备好的确认。** 由用户在手机／Mac 界面完成：

1. USB 连接指定 iPhone，解锁，点击“信任此电脑”。
2. 开启 Developer Mode，完成手机要求的重启／确认。
3. 在开发者设置开启 UI Automation。
4. 需要的 Apple 开发者支持文件由用户通过完整 Xcode 完成设备准备；不要下载来源不明的开发者镜像，不绕过安全设置。

确认完成后，重新读 Poki `docs/physical-iphone.md`。只有需要挂载本机已存在的兼容 Apple 签名支持镜像时，且用户已确认设备和权限，才运行该文档的 `prepare-device.mjs`；缺文件就停下让用户完成 Xcode 设备准备。

**终端 D：只在上述确认后执行最小检查：**

```sh
cd "$HOME/Developer/poki-mcp"
export PATH="$(brew --prefix node@24)/bin:$PATH"
node --version
export POKI_MCP_STATE_DIR="$HOME/Library/Application Support/Xiaorui/poki-mcp-state"
node bin/call.mjs poki_mcp_status
node bin/call.mjs list_devices
```

报告版本、实际 commit、工具目录、指定手机是否出现，必要设备 ID 仅保留本机。设备出现不等于截图、无障碍读取、中文输入、点击效果或具体 App 任务都通过。

首个真机 POC 应另行得到用户授权：用户手动打开一个页面，小瑞读出当前 App 和一条可核查屏幕文字。先不点击、不输入、不发消息、不叫车、不下单、不支付。Poki 的 tools/list profile 是发现设置，不能代替小瑞宿主层的工具白名单；不得将全部手机工具原样交给模型。

### 4.6 Flutter 是另外一个可选预览，不混入原版首轮部署

默认先不安装 Flutter、Android Studio、Java、Android SDK。用户明确要看 Flutter 时，再按 [Flutter 官方安装](https://docs.flutter.dev/install)为本机芯片安装 stable SDK，建议 `~/Developer/flutter`，记录实际版本，配置当前终端 PATH；不要引用旧 Linux 的 SDK 路径。

用独立目录与配置：

```sh
git clone --branch xiaohu_flutter --single-branch \
  https://github.com/kevinguo0351/xiaorui.git "$HOME/Developer/xiaorui-flutter"
cd "$HOME/Developer/xiaorui-flutter"
git fetch origin xiaohu_flutter
git rev-parse HEAD
git rev-parse origin/xiaohu_flutter
```

读该分支自己的 AGENTS／README／`docs/flutter-preview.md`。SDK 确实装在建议目录后，才使用：

```sh
export PATH="$HOME/Developer/flutter/bin:$PATH"
flutter --version
flutter doctor -v
```

然后按该分支锁定依赖、只在缺失时创建自己的 `.env`、构建预览。**先在终端 A 以 Control+C 关闭原版，确认 8000 空闲**，再：

```sh
cd "$HOME/Developer/xiaorui-flutter"
uv sync --locked --python 3.12
env MCD_ORDER_ENABLED=false LUCKIN_ORDER_ENABLED=false DIDI_ORDER_ENABLED=false \
  ./scripts/start-flutter.sh --build
```

另开终端 `open http://127.0.0.1:8000/flutter/`。这个启动脚本在其子进程里强制 `XIAORUI_READ_ONLY=1`，共享后端的 React 页面也受到只读限制；这是预期行为，不是原版配置保存坏了。预览服务停止后再按第 4.4 节显式 `XIAORUI_READ_ONLY=0` 启动原版。网页预览成功不等于 Android／iPhone 客户端已验收。

### 4.7 生命周期、私有日志、备份和失败处理

#### 前台终端分工

| 终端 | 作用 | 正常停止方法 |
| --- | --- | --- |
| A | 小瑞原版，127.0.0.1:8000 | Control+C，等进程退出，再确认端口 |
| B | 小瑞健康检查／测试／手动 open | 命令结束即退出，不持有第二个服务器 |
| C（可选） | Poki daemon，127.0.0.1 上随机端口 | Control+C，等待会话和进程清理 |
| D（可选） | Poki 状态检查、Codex MCP 注册 | 只做已授权的检查；不自动重放设备动作 |

首轮不配置 launchd、自启、自动登录、远程解锁或持久后台任务。要长期运行，在所有验收结束后再单独设计私有日志、进程重启和升级方案。

需要保存日志时，先创建用户私有目录（umask 077、目录 700、文件 600）；日志可能含个人对话、屏幕和平台错误，不贴全文、不提交 Git。普通 `tee` 会改变 shell 的退出码与前台进程处理，首轮优先保留直接前台输出并仅记录去敏的错误摘要。

#### 备份

`.env` 与 `.local-data` 都是私有本机数据，不在 GitHub。备份到用户选定的私有／加密位置，**先停服务**再做 SQLite 和相关文件一致快照。不要把 Linux 的 `.venv`、node_modules 或原生构建缓存当作 Mac 环境迁移包。

示例只在已有 `.env` 和 `.local-data`、服务已经停止时运行；先检查空间，因为启动器也把 Python／uv 缓存放在 `.local-data`，整个目录可能较大：

```sh
cd "$HOME/Developer/xiaorui"
du -sh .local-data
backup_dir="$HOME/Library/Application Support/Xiaorui/backups/$(date +%Y%m%d-%H%M%S)"
(
  umask 077
  mkdir -p "$backup_dir"
  chmod 700 "$backup_dir"
  tar -czf "$backup_dir/private-state.tar.gz" .env .local-data
  git rev-parse HEAD > "$backup_dir/code-commit.txt"
)
```

这个压缩包含密钥和个人数据，不上传到聊天、Issue 或 PR。恢复前核对代码／数据格式与来源；不要整包把旧机 Python、缓存恢复到 Mac，也不要覆盖运行中的数据库或现有配置。

#### 失败与回退

- **端口占用／打开了错误版本**：查明具体监听进程，在对应前台终端停下；不用自动杀全局 Python／Node。核实地址 `/` 与 `/flutter/`、checkout 与模式。
- **配置存在但调用失败**：保留真实错误和已填写／未验证的区别。不要反复提交会产生外部动作的请求；不自动换模型、账号或提高交易权限。
- **代码更新后失败**：保留旧 commit SHA、未提交修改和私有备份；停服务。优先在新 worktree／新目录检出已知良好 commit，重新装锁定依赖并构建后验证。不要 `git reset --hard`、不要删 `.local-data` 作为“修复”。如果版本涉及数据库迁移，先核对兼容性，不盲目恢复。
- **手机动作超时／停止**：结果可能未知。先看真实手机／官方订单状态，再决定下一步；不得因为网络断开或 UI 显示“停止”就重放点击、消息、下单、取消或支付。
- **缺 Mac／权限／凭据**：报告具体卡点和仍未测试的层；不能写“部署完成”或“闭环已跑通”。

若未来要从 Linux 远程进入 Mac，由用户在 macOS 共享设置手动开启 Remote Login、选择获准账户并完成自己的认证。那是单独的远程接入任务；本交接不打开远程登录、不创建公网端口，也不向 agent 发送账户密码。


## 5. 语音升级：持续自然对话，而非只加快逐句播报

资料核查日期：2026-11-05。本节是下一位实施 agent 的工作单，**没有实际调用语音服务，没有测得真人延迟，也没有证明账号已获新模型权限**。

**建议：优先验证一个长连接、可同时听说、自动接话和插话的语音前台，把小瑞现有 nanobot／官方服务／Poki 作为异步业务后台。先尝试字面意义的 GPT-Live 1＋client delegation；若账号、地区、网络或中文听感不满足门槛，再选择豆包 Seeduplex。一次只实现一个实时提供方，不同时建设三套。**旧 ASR→LLM→TTS 链路保留为故障回退，不能把“逐句预取更快”算成 Live 体验已完成。

### 5.1 已知现状与真正要改变的体验

以下是**仓库硬数据**，不是服务性能测试：

| 当前代码 | 已有能力／限制 | 对下一步的含义 |
|---|---|---|
| `app/voice.py` 的 ASR | `bigmodel_async`；16 kHz／单声道 PCM16；WebSocket 上传与识别字幕；二遍识别；`end_window_size=2000` | 输入已经流式，不要误判为需要从零重写 ASR |
| `app/voice.py` 的 TTS | 上游 HTTP 分块响应被累积为整个 MP3，结束后才返回 | 上游流式不等于用户听到流式，当前存在整句缓冲 |
| `frontend/src/useVoice.ts` | 等 `blob()` 完整到达再播放；当前句播放期间预取下一句；通过 generation 和 AbortController 抛弃旧音频 | 有一句预取，仍非音频块连续播放，也非全双工会话 |
| `app/agent.py`、`app/speech.py` | 主模型结束后，某些回复还会 await 一次有超时限制的口语改写；关键事实／已简短回复已有宿主直出路径 | 先分别计时，不能把全部等待归因于 TTS，也不能为快而移除事实校验 |
| `useVoice.ts`、`HoldToTalk.tsx` | 通话以 3 秒静默判停；输入框按住 350ms 启动、松开发送；另有“我说完了” | 两个阈值都是设计初值；保留明确结束和无障碍按钮，不能声称已适合所有老人 |

**体验验收**应是：进入一次通话后不用反复按按钮；老人说到一半思考时不会抢答；小瑞说话时能听见“等等”；后台查门店或操作手机耗时较长时，仍能听用户补充预算，且不凭空宣告查询成功。

### 5.2 首先选择提供方，再做一个实时前台

**首选实验：GPT-Live 1，模型 ID `gpt-live-1`，不是旧的 `gpt-realtime`。**官方当前把它定义为可同时听说的语音前台，推理与工具工作可交给独立后端。模型名和当前能力已查官方页面；当前项目权限、中文效果和实际网络延迟仍待实测。[OpenAI Docs：GPT-Live 1](https://developers.openai.com/api/docs/models/gpt-live-1)

浏览器优先 WebRTC：音频走媒体轨道，控制事件走 data channel；Mac 服务端使用项目 API Key 创建 `/v1/live/sessions` 并交换 SDP。标准密钥只在可信后端，不写浏览器、localStorage、日志或二维码。手机页面必须用 HTTPS；现有 ChatGPT／Codex 登录不能当作这个项目已具备 API Key、额度或新模型权限的证据。[OpenAI Docs：WebRTC](https://developers.openai.com/api/docs/guides/voice-webrtc)、[MDN：AudioWorklet 的安全上下文要求](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet)

为了保留小瑞业务，采用 `delegation: {type: "client"}`。`session.delegation.created` 只有 delegation 元数据和时间位置，**没有用户任务正文**；收集 `session.input_transcript.delta` 与当前任务状态后，由宿主构造请求。保存 `delegation.id`，经核验的结果通过带同一 ID 的 `session.commentary.append` 回到前台；该事件可改述内容，不代表已经逐字播报或播放完成。完整工具原文和个人资料仍留在业务后台。[OpenAI Docs：Delegation and tools](https://developers.openai.com/api/docs/guides/live-delegation)

Live 适配器与业务任务分离：

```text
手机／Mac 浏览器 ——持续 WebRTC 语音—— GPT-Live
      │                                │
      │任务板、文字、显式停止            │ client delegation／侧带事件
      └────────── Mac FastAPI ───────────┘
                    │
             有版本号的业务 job
                    │
           nanobot → 官方 API／Poki
                    │
       经核验的结果／真实进度 → 语音前台与任务板
```

Live 提示词只承担角色、慢速清晰说话、适度回应、等待和移交条件；完整权限与业务流程放后台。按当前官方模板，保留 Backchannel／Interruption／Delegation policy 三部分，移交触发使用文档指定的 `Generate <|SpawnThinking|>`。不要只写“我会查询”就当成任务已进入队列。[OpenAI Docs：Prompting GPT-Live](https://developers.openai.com/api/docs/guides/live-prompting)

**中文备选：豆包 Seeduplex 3.0。**当前正式文档给出的地址是 `wss://openspeech.bytedance.com/api/v3/duplex/realtime/dialogue`，采用 JSON Realtime 事件；原 S2S 二进制协议不能原样复用。它支持 `tools`；工具调用按 `call_id` 配对回传。输入为 16 kHz 音频，输出为 24 kHz；输出 `pcm` 与 `pcm_s16le` 位深不同，必须明确指定并验证，不能复用旧解码假设。[豆包：Seeduplex 接口](https://docs.volcengine.com/docs/doubao-voice/end-to-end-real-time-voice-full-duplex-version?lang=zh)

Seeduplex 的新适配器须按官方输入约束发送实时音频；关闭麦克风但保持会话时发送对应 mute／unmute 事件；不要把旧 ASR 的 200ms 包直接照搬为新链路参数。新旧服务权限与音色分别核验，不因旧 ASR／TTS Key 存在就显示新实时模型已连接。[豆包：接入必读与音频约束](https://docs.volcengine.com/docs/doubao-voice/access-must-read?lang=zh)

**暂缓 RTC 全套改造。**火山 MMPG 能保留自有 Agent，但还需 RTC 应用、SDK、Token、AK／SK 签名及音频传输改造；它不是给现有 WebSocket 换个 URL。若直连实时适配器的回声、网络或端适配始终过不了验收，再评估它。[火山：基于自有 Agent 的 MMPG 接入](https://docs.volcengine.com/docs/real-time-communication/quick-integrate-custom-agent-via-gateway?lang=zh)

### 5.3 下一位 agent 的实施顺序与每步退出条件

1. **建立基线，但不要卡住实时体验实验。**保留现有模式，记录客户端“最后有效人声／主动结束、收到第一段有效音频、实际开始出声、用户打断到停声”和服务端“ASR final、入队、模型首字、工具开始／结束、口语改写、TTS 首块／末块”。不同机器的时钟不能直接相减；服务端报告本地单调时钟的阶段时长，客户端自己量完整等待。日志仅存随机关联 ID、阶段、状态和耗时，默认不存音频、转写、密钥、手机标识。纯闲聊与真实查询分开统计。
2. **早开独立实时实验分支。**提供方门槛通过后，先仅做长连接闲聊：一次进入、连续二十轮、边听边说、自动让话、停顿容忍、断网与关闭清理。此时不接任何交易工具。必须在实际 Mac 浏览器和手机 Safari 各跑一遍；只听 SDK 示例或跑 mock 测试不算通过。
3. **接业务 job，而非阻塞整条语音会话。**最小 API 是提交／补充／查询进度／停止本地工作的窄接口；由宿主把一个 delegation 映射为稳定 job ID。语音纠正“改成二十元”更新该 job 的条件版本，不能重复创建同一外部操作。Poki 慢查询在后台跑，语音前台继续听；任务完成时仅回送事实摘要、来源、时效和仍需用户确认的事项。
4. **先接一个只读查询，再接老人场景调音。**普通陪伴走快速实时前台；金额、门店、订单状态等关键内容只来自宿主核验。采用较少的“嗯、好”回应，一次问一个主要问题；用户要求慢一点时调音色／语速，并验证实际听感。不能用把所有判停时间缩短来换速度。
5. **旧链路保底优化独立进行。**若需要保留级联模式，先把已核验的完整文本通过 HTTP TTS 真实分块返回与播放，验证PCM样本格式并用 AudioWorklet 有界队列播放；不能对任意 MP3 网络块调用一次完整解码冒充流式。再升级双向 TTS，让宿主允许播报的稳定文本片段边进边出。普通闲聊可较快放行，价格、状态、确认方案等仍需宿主校验后放行。不要把 nanobot 原始 delta、工具参数或未核实的模型猜测直接送 TTS。

HTTP TTS 官方支持一次输入文本、分块输出音频，且推荐流式使用 PCM；这支持第 5 步的保底改造，但不提供全双工对话。[豆包：HTTP 单向流式 TTS](https://docs.volcengine.com/docs/doubao-voice/unidirectional-streaming-text-to-speech-http?lang=zh)

双向 TTS 支持文本输入与音频输出同时进行。连接可复用，但同一连接不能并行多个 session；取消后必须按会话事件重新开始，不能继续使用已取消会话。正式实现以该协议为准，别把它与 S2S 的 `response.cancel` 混用。[豆包：WebSocket 双向 TTS 协议与取消语义](https://docs.volcengine.com/docs/doubao-voice/websocket-bidirectional-streaming-v3?lang=en)

### 5.4 宿主必须实现的状态与安全边界

- **听、说、做分别建状态。**`voice_session_id`、`reply_generation`、`delegation_id`、`job_id`、`job_version` 各司其职。语音会话恢复不等于业务重试；收到旧音频、旧字幕、旧异步检查许可或旧工具回执时，先核对版本。断线重连先恢复任务状态，再决定是否需新查询，不重放外部写入。
- **“先别说”与“这件事不办了”分开。**前者立刻停止当前播放、丢弃排队音频，业务默认继续；后者由宿主停止未派发的后续步骤，并核对已派发操作的结果。取消外部订单／付款是新的交易动作，不能伪装成停止任务，更不能因为用户插话而自动执行。界面同时保留“停止播报”“停止这件事”“挂断”。
- **未听到的内容不能当作用户已听到。**本地记录实际播放进度。GPT-Live 按 Live 的播放／上下文契约处理；不可照抄 Realtime 的 `conversation.item.truncate`。若另做 Realtime 体验对照，WebSocket 需按实际已播放时长执行该截断，WebRTC 的行为以其官方指南为准。[OpenAI Docs：Realtime 中断与截断](https://developers.openai.com/api/docs/guides/realtime-conversations)
- **仅发指令不能保证即时闭嘴。**需要阻止用户听见输出时，在应用播放器／媒体桥静音、丢弃旧队列；sideband 本身不控制播放，输入静音也不等于输出静音。对关键业务语句，采取可控播放门闸，或暂停实时模型音轨，播放宿主已核验的精确口播。`commentary.append` 可能改述，不能保证金额逐字准确；宁可暂退到核验卡片＋受控口播，也不把关键事实全部交给提示词。[OpenAI Docs：Server-side controls／Check speech before playback](https://developers.openai.com/api/docs/guides/voice-server-controls)
- **真进度只能由真事件产生。**入队后才说“我收到这件事了”；工具实际启动后才显示“正在查门店”；得到结果才说“查到”；支付和下单没有回执不说成功。查询等候时允许简短安抚，但不编百分比、门店、价格或完成状态。沿用 `app/progress.py` 的宿主事件语义。
- **人声活动、分句、轮次结束和任务提交不是同一件事。**现 ASR 中间文本会更新；二遍识别的分句确定标记不自动等于用户明确提交。当前本地 3 秒静默与上游 2 秒分句分别测量，避免重复等待或提前截断。Live 不套用 Realtime 的 `semantic_vad` 字段；若采用 Realtime，对思考停顿另测其 semantic VAD 策略。[豆包：ASR 二遍识别](https://docs.volcengine.com/docs/doubao-voice/bidirectional-streaming-automatic-speech-recognition-websocket?lang=zh)、[OpenAI Docs：Realtime VAD](https://developers.openai.com/api/docs/guides/realtime-vad)
- **回声不能算用户确认。**先以耳机建立基线，再测手机扬声器、Mac 扬声器、电视人声；回声消除／降噪参数“已开启”不代表有效。咳嗽、短促环境声不能自动改预算或确认交易；明确按钮始终可用。真人大段思考时允许“我还没说完”，不反复催促。

### 5.5 验收指标：以下全部是建议目标，尚未测得，不能写成成果

| 指标与测量边界 | 首轮建议目标／判定 |
|---|---|
| 点击／按住达阈值后，到明显的界面收音反馈 | ≤150ms；权限弹窗／服务连接另计，不把“正在连接”写成“正在听” |
| 用户明确“等等”或点击停止，到最后可闻旧音频 | p95 ≤300ms；同时旧 generation 后续音频不得复活 |
| 简单闲聊：用户语义结束到第一段有意义回复出声 | p50 ≤1.0s、p95 ≤2.0s；固定“嗯”不计有效回答，思考等待和业务查询另报 |
| 慢业务：任务被接受到真实收件／查询状态反馈 | p95 ≤1s；不能把反馈当业务结果时间 |
| 已核验可播文本到第一声（旧级联回退模式） | 预热条件下 p95 ≤1.5s；显示冷启动、网络和服务端耗时 |
| 连续通话与取消 | 每设备至少20轮；旧回复复活、重复外部提交、取消后误提交均为0 |
| 老人停顿与背景噪声 | 与当前基线比较误抢话／误打断数量；绝不能只报平均延迟改善 |
| 业务真实性 | 测试集中关键金额／门店／状态必须逐项对照真实来源；任一虚报完成直接不通过 |

这些数字是**工程验收初值／估计，不是行业基准或服务 SLA**。每种设备／网络报告样本数、p50、p95、失败数及人工听感，不用少量样本的均值宣称普适改善。通话成本按真实服务 usage 记录，预算上限由用户确定。

### 5.6 十个中文验收场景

| 场景 | 用户输入／动作 | 必须观察的结果 |
|---|---|---|
| 1 文字与长按 | 短按输入文字；长按输入框说“帮我找附近的麦当劳”；首次权限未完成便松手 | 短按不录音；松手后不继续收音；迟到权限不得复活旧请求；保留可访问的语音按钮 |
| 2 慢慢想 | “我想吃……〔停2–5秒〕……清淡一点，还没说完。” | 记录各停顿的抢话表现；保留字幕和补充；手动“我说完了”可结束；未完成表达不触发交易 |
| 3 自然接话 | 连续20轮问候、追问“再慢一点”“刚才第二个是什么” | 不需每轮重新点麦克风；上下文不串，音色与语速可理解，无明显句间割裂 |
| 4 用户插话纠正 | 小瑞播报时说“等等，预算改成二十元” | 旧声及时停，旧音频不回来；同一 job 条件版本更新，不重复下单或新建相同任务 |
| 5 停说与停事 | 先说“你先别说，继续帮我查”；再说“这件事不办了” | 两种意图在任务板有不同结果；停止本地执行不冒充取消外部订单 |
| 6 真查询较慢 | 查实际门店／菜单，或经授权的 Poki 只读页面 | 等候时仍能说话；仅显示真实进度；结果有来源；未查到明确说明，不编门店和价格 |
| 7 方言、低声和数字 | 目标老人说“麦当劳、二十元、不要冰”；低音量、方言、混合店名各试 | 关键实体错了先核对；不以 ASR 字幕正确率替代任务参数正确率 |
| 8 扬声器与电视 | 小瑞自己播“需要您确认”，电视有人说“确认下单”，同时咳嗽 | 不把回声／电视当授权；误打断计数；只读宿主不能产生交易 |
| 9 网络与播放拒绝 | ASR／实时会话／工具运行中断网；浏览器拒绝自动播放；凭据缺失 | 说明真实故障；有手动重播与文字回退；不自动重放业务操作；连通状态不虚报 |
| 10 生命周期与迟到结果 | 识别等待时再按一次；切后台、开设置、挂断、刷新；随后旧结果到达 | 释放本地麦克风；旧音频不播；任务结果可按既有持久事件恢复；不重复创建任务 |

验收须保留文字记录与阶段时间；录音需先取得参与者同意。真实体验未通过时，mock／单元测试通过只能证明对应逻辑，不证明 Live 听感。

### 5.7 停止条件与回退

- 项目无目标模型权限、服务地区／网络不适用、费用无法接受：不假装配置成功；选择一个可用的备选，或回退现链路；不把个人／公司其他凭据搬来顶替。
- 未核实金额或状态被播报、任何未授权交易、旧 generation 复活或重复提交：立即停止扩大场景，修复宿主与播放门闸后重跑。
- 实时前台能闲聊但慢工具使会话失去响应：先修 job 与语音会话的解耦，不用更快 TTS 掩盖。
- 老人误抢话／电视误触发高于基线，或无法确认停止已经生效：回退显式“按住说话／点击结束”，不强推自动双工。
- 分块 TTS 已解决但首答仍慢：根据测量定位模型、口语改写、工具和网络；无证据不继续叠协议重写。

**交付定义：**完成的是一个提供方、一个真实只读场景、一个可持续的自然语音会话；同时给出真实测量、失败边界、回退入口和未验收项目。没有真人设备与凭据时只交实现和测试记录，明确“真实体验待验收”。

## 6. Tailscale：远程访问和受控手机是两个链路

研究日期：2026-11-05。只读研究；没有配置 Tailscale、SSH、Serve、防火墙或设备，没有运行 Poki 工具。以下命令是交接示例，尚未在用户 Mac 上执行。

**建议先采用“远程电脑 → Tailscale → 家中 Mac 的 SSH → Mac 本机小瑞”的方式。受控 iPhone 留在家里，通过已验证的 USB／同一局域网连接 Poki。不要承诺把同一部受控手机带出门后，仅靠 Tailscale 就能继续控制。**

### 6.1 两种拓扑必须分开说

| 场景 | 当前能说什么 | 证据级别 |
|---|---|---|
| A. 人在外地，使用另一台电脑远程访问家中 Mac；受控 iPhone 留在家里 | Tailscale 提供到 Mac 的私有网络连接；SSH 可把 Mac 回环服务转发到操作者电脑回环。Poki→iPhone 仍走家中的 USB／已配对同 LAN 链路。须在 Mac 实测后交付。 | Tailscale／OpenSSH 官方支持的网络能力；组合方案是工程设计，未在用户设备验收 |
| B. 同一部受控 iPhone 被带到外地，用蜂窝网络连接 Tailscale；Mac 留家 | **尚不支持交付保证。**iPhone 的 Tailscale IP 可达不等于 usbmuxd 能发现它，也不等于 CoreDevice 配对、RSD、开发者服务、屏幕与输入通道可用。不能把 A 的可行性移植到 B。 | Poki 明确记录 USB 初次配对与后续同局域网条件；跨公网／蜂窝场景未验证 |
| C. 外地手机只当小瑞网页客户端，另一部受控 iPhone 留家 | 属于远程 HTTPS 网页接入，不等于“远程控制这部外地手机”。当前小瑞服务边界会阻止直接 Serve 域名接入；移动网页接入须另做安全改造与验收。 | 当前代码事实；未来能力 |

**产品边界：当前小瑞尚未接入 Poki。以下拓扑说明网络可达关系，不表示小瑞网页已经能够调用手机工具；工具注册、授权与交易约束另需实现。**

Tailscale 的 MagicDNS 为 tailnet 设备提供 DNS 名称，不等于转发 Bonjour 服务发现。[官方 MagicDNS](https://tailscale.com/docs/features/magicdns)。截至本轮检查，官方仓库的 [mDNS 功能请求 #1013](https://github.com/tailscale/tailscale/issues/1013) 和 [通用组播功能请求 #11134](https://github.com/tailscale/tailscale/issues/11134) 均未关闭；维护者说明过后者尚未排期。故不能将 tailnet 当作自动延展的二层局域网。这里判断的是**不能保证自动发现与协议链路**，不是声称任何定制隧道方案都不可能。

Poki 检查版本 `ea28be1872952a27b0dade59e6ccc6405854ef19`：

- [physical-iphone.md](https://github.com/JosssphZhou/poki/blob/ea28be1872952a27b0dade59e6ccc6405854ef19/docs/physical-iphone.md) 第 7–34 行要求先 USB 信任与开发者准备，后续无线操作描述为同局域网，且部分无线检查未在后续输入改动后整体验证。
- [native/bridge/src/main.rs](https://github.com/JosssphZhou/poki/blob/ea28be1872952a27b0dade59e6ccc6405854ef19/native/bridge/src/main.rs#L271) 第 271–285 行实际连接链路为本机 `UsbmuxdConnection` 找 UDID → provider → `CoreDeviceProxy` → software tunnel → RSD。
- MagicDNS、单纯端口转发、exit node 或 subnet router 都不能凭名称证明上述链路已具备。不要猜开发者服务固定端口并开放一组端口来冒充验证。

### 6.2 为什么现在不能直接开 Tailscale Serve

小瑞当前源代码：

- `app/main.py:58–65`：HTTP Host 只允许 `localhost`、`127.0.0.1`、`::1`；出现 Origin 时须严格等于请求 scheme + Host。
- `app/voice.py:53–63`：ASR WebSocket 同样限制回环 Host，并要求精确 Origin；失败会拒绝连接。
- `pa_session` 是本地会话归属 cookie，**不是登录认证或家人管理员授权**。服务还提供 `/api/settings` 凭据编辑能力；只读预览能拒绝配置写入，但普通启动不能被当作已具备远程鉴权。

Tailscale Serve 官方支持把私有 tailnet HTTPS 访问反代到本机回环端口，并可添加用户身份头；服务必须主动校验身份和权限。它不会自动给小瑞实现管理员鉴权。[Serve 官方说明](https://tailscale.com/docs/features/tailscale-serve)、[Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve)。

**推论：**直接用外部 `*.ts.net` 地址浏览当前小瑞，若代理保留该 Host，会触发 HTTP／WS Host 拒绝；若改写为 localhost，浏览器的外部 HTTPS Origin 仍与当前校验不符。不能用“把 Host 和 Origin 都伪装成本机”绕过边界，也不要只为了页面能打开删除校验。

Serve 的 HTTPS 能力与小瑞应用兼容是两件事。首页能显示也不证明 SSE、ASR WebSocket、cookie、支付保护和配置授权均正确。

### 6.3 当前桌面远程接入：保留回环、通过认证 SSH 隧道

前提：用户已经授权并正确启用 Mac 的系统“远程登录”（标准 OpenSSH），只允许指定用户，SSH 公钥认证与主机指纹已核对；两台电脑在 tailnet 内且访问规则只给该操作者。不要为本轮研究启用服务。

这不要求开启 Tailscale 自有 SSH 服务器。官方说明 Tailscale SSH 服务器在 Mac 上仅支持其开源 `tailscale` + `tailscaled` CLI 版本；App Store／Standalone 版本不能直接套用 Linux 的 `tailscale up --ssh` 交接步骤。[Tailscale SSH 限制](https://tailscale.com/docs/features/tailscale-ssh)。标准 OpenSSH 可以通过 Tailscale IP 传输。[SSH over Tailscale](https://tailscale.com/docs/reference/ssh-over-tailscale)。

家中 Mac 保持原服务：`127.0.0.1:8000`。远程电脑另开终端：

```bash
ssh -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L 127.0.0.1:18000:127.0.0.1:8000 \
  MAC_USER@HOME_MAC_TAILSCALE_NAME
```

在**运行该 SSH 客户端的远程电脑**浏览器打开 `http://127.0.0.1:18000`。两处 `127.0.0.1` 分别代表客户端本机监听、SSH 服务器 Mac 本机目标。不要打开 `http://HOME_MAC_TAILSCALE_IP:8000`。`-L` 是 TCP 转发，会保留浏览器使用的本机 Host／Origin；因此与现有边界相容的设计成立，SSE／WebSocket 也走同一隧道，但真人语音仍须端到端实测。[OpenSSH 官方 -L/-N 说明](https://man.openbsd.org/ssh.1)。

保持终端开启，结束时 Ctrl-C 关闭 SSH 隧道。关隧道只停止访问，不会自动停止 Mac 服务、取消已接收任务或撤销已发送的外部操作。不得使用 `-g`、星号监听、`0.0.0.0` 监听或路由器公网映射来扩大此入口。

### 6.4 手机网页 HTTPS：另立后续工程，不当作已交付

未来如需 `https://MAC_NAME.TAILNET.ts.net` 手机访问，应保持后端回环监听，另行完成并测试：

1. 显式、精确的允许 Host 与 HTTPS Origin 配置，明确可信反向代理和转发 scheme；不能通配来源或任意信任 forwarded headers。
2. 可验证的登录／用户身份授权；家人配置页面和凭据写入必须有独立管理员权限。若采用 Serve 身份头，只信任受控本机代理注入，缺失身份、未授权用户和 tagged device 都应默认拒绝；不要把“在同一个 tailnet”当作任意成员可管理密钥。
3. WS 握手、Origin 校验、cookie Secure/SameSite/CSRF、SSE 不中断及断线恢复，并在目标 Safari／Chrome 实测麦克风与播放限制。
4. 原有交易宿主确认、只读模式、配置项白名单和密钥不回传仍必须成立；Poki 不得因为网络可达就直接获得原始支付／发送点击权限。
5. 访问控制只允许指定用户和设备；不启用 Funnel，不把配置编辑器公网发布。正式开通前，未授权访问配置和语音计费接口必须返回拒绝。

仅用于理解产品能力、**不是当前小瑞的执行步骤**：Serve 官方 CLI 形如 `tailscale serve --https=443 8000`，自动 TLS 依赖 tailnet HTTPS 配置。开通、常驻 `--bg`、证书和策略都属于另一次授权后的部署；不能先运行再解释。官方 CLI 记录 `tailscale serve status` 查询配置，按原端口与路径加 `off` 停止单项服务；不要无差别 `reset` 破坏用户已有服务。[Serve CLI](https://tailscale.com/docs/reference/tailscale-cli/serve)。

### 6.5 九项验收与停止门槛

这些是待执行清单，不是本轮已通过记录；不得打印密钥、完整配置文件或 Poki bearer token。

| 检查 | 通过证据 | 失败时怎么停 |
|---|---|---|
| 1. 划清设备角色 | 写清“外地操作者设备／家中 Mac／受控 iPhone”的位置和网络，确定 A、B 或 C | 若唯一受控 iPhone 将被带走，不能按 A 宣布交付 |
| 2. 家中 Mac 本地服务 | Mac 本地 `curl --fail http://127.0.0.1:8000/api/health` 正常；`lsof -nP -iTCP:8000 -sTCP:LISTEN` 显示仅回环；Mac 不休眠且网络稳定 | 本地失败先修本地，不开放外网绕过 |
| 3. tailnet 传输 | 两端 `tailscale status` 在线；远程 `tailscale ping HOME_MAC_NAME` 能到 Mac；记录 direct／relay 仅作延迟诊断 | ping 可达不能计为 SSH、小瑞或 iPhone 协议通过 |
| 4. SSH 认证与授权 | 指定非共享用户能用已核对的公钥登录；Mac 主机指纹一致；未授权账户被拒绝 | 指纹变化、密码共享或访问策略过宽时停止远程接入 |
| 5. 仅本机隧道 | 上述 `ssh -L` 成功；客户端 `lsof` 显示 18000 仅 127.0.0.1；关闭终端后该入口不可达 | 转发失败或端口被占用时换本地端口，不启用全网监听 |
| 6. 页面、消息和恢复 | 经 18000 打开原 React 首页；真实提交只读查询，SSE 更新、刷新恢复、重复提交去重如实记录 | 只收到页面不算消息链路通过；缺凭据须标待验证 |
| 7. 声音与停止行为 | 经同一隧道完成浏览器权限、字幕、ASR final、播报；取消未完成录音不提交，停止播报立即静音，断线有明确提示 | 分开记录网络、未配置、供应商权限、浏览器拒播；不把失败假装成连通 |
| 8. Poki 本地手机链路 | 在家中 Mac、获设备操作授权后，先 USB 验证截图／字段，再按上游说明验证同 LAN；锁屏和断连能明确失败 | 仅 list_devices 可见不能算输入／截图可用；出门蜂窝场景单列实验，不能套用同 LAN 证据 |
| 9. 敏感接口与收口 | 不存在公网／全 tailnet 无鉴权入口；只读启动拒绝交易与设置写入；关隧道后远程入口关闭；记录未完成任务仍可能继续 | 任意未授权用户可编辑密钥、调用计费语音或点击交易按钮时，不发布远程入口 |


## 7. 后续开发文件地图与验收记录

### 7.1 优先改动边界：保持业务后台，替换语音前台

下表路径均为仓库现存文件。新实时适配器、会话创建路由、Poki 受控适配器和远程登录授权层**目前不存在**，应在隔离分支新增，不能将本文设计当作已经能调用的 API。

| 现存文件 | 接手时先看什么 |
|---|---|
| [frontend/src/useVoice.ts](frontend/src/useVoice.ts) | 录音、ASR、VAD、完整 blob 播放、下一句预取、generation／AbortController；`speechMetrics` 和调试开关。新旧麦克风与播放器不得同时争抢设备 |
| [frontend/src/HoldToTalk.tsx](frontend/src/HoldToTalk.tsx) | 长按、释放、上滑取消、迟到权限处理；保留明确按钮和键盘可访问性 |
| [frontend/src/main.tsx](frontend/src/main.tsx) | 消息提交、SSE、任务显示与回复播报入口；实时字幕不能直接当成新任务无限提交 |
| [frontend/src/SettingsDialog.tsx](frontend/src/SettingsDialog.tsx) | 家人设置界面；当前字段不等于可任意注册 MCP 或新实时提供方 |
| [app/voice.py](app/voice.py)、[app/voice_protocol.py](app/voice_protocol.py) | 精确 Origin、流式 ASR 协议、TTS 完整缓冲；新协议应有独立适配器与格式验证 |
| [app/agent.py](app/agent.py)、[app/nanobot_runtime.py](app/nanobot_runtime.py) | Agent 主循环、工具宿主、计时、工具白名单接入；不要另建一个无约束的业务 Agent |
| [app/speech.py](app/speech.py) | 额外口语改写及关键事实直出；必须区分普通闲聊和可核查业务事实 |
| [app/contact.py](app/contact.py)、[app/contact_events.py](app/contact_events.py) | 会话归属、现有消息／执行回执和持久事件；新增 delegation→job 映射要复用可恢复状态 |
| [app/progress.py](app/progress.py) | 真事件到真状态；不生成假进度 |
| [app/skills.py](app/skills.py)、[app/read_only.py](app/read_only.py) | SCHEMAS、注册工具与只读允许集；新增 Poki 观察能力须宿主白名单校验，不能只修改模型提示词 |
| [app/actions.py](app/actions.py)、[app/plans.py](app/plans.py) | 确认方案、权限、版本与执行；任务停止不等于外部取消 |
| [app/settings.py](app/settings.py)、[app/main.py](app/main.py) | 配置字段与官方服务地址限制、Host／Origin；不能把 OpenAI Key 塞入 Ark 字段或放宽目标地址来迁就新提供方 |

**建议新增的工作单，均为待开发：**

1. 建立 `voice-live-poc` 本地分支，做服务端会话创建、浏览器 WebRTC、关闭清理。API Key 仅服务端可读；创建会话前校验归属、并发会话数、速率和预算，不能成为任意用户的计费代理。
2. 用应用级会话 ID 绑定 owner、提供方会话、delegation 和现有 job；字幕按时间顺序累积并处理重复／迟到片段。字幕不是交易确认。任务条件更改增加版本，旧结果只可显示为历史，不覆盖新条件。
3. 后端监听实际业务事件，再发布核验 commentary 与任务板状态。语音前台与业务不能互相阻塞；工具长任务期间继续接话。
4. 手机观察适配器只输出允许的 App 名／指定页面字段及来源时间；禁止模型直接调用任意 tap、fill、batch、剪贴板、通知、安装和支付工具。Poki 的通用审批并不覆盖所有能通向交易的点击路径。
5. 账号／模型／网络实际可用后再做一个真实查询。语音模式切换时释放旧麦克风、音轨、WebSocket、RTCPeerConnection、定时器和音频队列；断线不自动重放外部动作。

**最强反对理由与撤回条件：**全双工模型可能在中文方言、电视噪声、地区连通性或成本上不如现链路；这不能靠架构图消除。若真实老人听感与误抢话未改善，或关键业务事实无法可靠控制，则保留显式录音模式，停止扩大集成，优先修误触发与事实播报。暂缓提醒、后台监听、自动解锁、真实交易、任意 App 自动化、Rust 重写和三套实时提供方同时建设。

### 7.2 每轮留一张真实验收表

复制此模板到本机私有运行记录；仅将去敏摘要放到仓库 `docs/acceptance/`。手机标识、完整对话、录音、密钥和屏幕原图不默认入库。

| 项目 | 实际记录 |
|---|---|
| 日期／操作者／阶段 M0–M5 | 待填写 |
| Mac 型号、芯片、macOS、Xcode、浏览器／iOS 版本 | 待填写 |
| 小瑞分支／HEAD、Poki HEAD、提供方与模型 ID | 待填写；不含凭据 |
| Mac／操作者／受控手机位置、USB／Wi-Fi／蜂窝 | 待填写 |
| 配置已存在、远端已验证、未验证项 | 分开填写 |
| 真实命令、退出码、HTTP／WS 错误摘要 | 去敏填写 |
| 语音场景、样本数、首答 p50／p95、停声 p95、误抢话、句间断流／音频队列欠载次数 | 分设备与网络填写；未测写未测 |
| 查询来源、可核查结果、重复提交与恢复行为 | 待填写 |
| 麦克风／音轨／会话关闭、锁屏、休眠、断网结果 | 待填写 |
| 已通过／失败／未测、下一步、回退版本 | 待填写 |

**本轮交付边界：**完成统一交接文档、命令与源码静态核查；没有执行 Mac 安装、手机操作、Tailscale 配置或真实实时语音调用。本文测试数量沿用此前 Linux 程序验收记录，本轮文档检查不新增程序验收成绩。下一位实施者必须用上表填入 Mac／真人结果，才能把对应 M 阶段标为完成。
