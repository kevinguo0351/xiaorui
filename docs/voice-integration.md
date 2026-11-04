# 豆包语音接入

小瑞分别使用豆包语音识别和语音合成；方舟文本模型 Key 不等于语音服务 Key。本轮接入真实官方 API，没有浏览器识别或预录音冒充豆包的退路。缺少凭证时保持文字操作，并显示配置提示。

## 开通与配置

1. 打开 [豆包语音新版控制台](https://console.volcengine.com/speech/service)，按控制台要求完成账号、计费和服务开通。
2. 开通流式语音识别 2.0 小时版，以及语音合成 2.0；以账号可用资源、音色和实际计费说明为准。
3. 在新版控制台创建可调用上述服务的 API Key，填入项目本机 `.env` 的 `DOUBAO_SPEECH_API_KEY=`。不要提交 GitHub 或发送到聊天。
4. 默认资源为 `DOUBAO_ASR_RESOURCE_ID=volc.seedasr.sauc.duration`、`DOUBAO_TTS_RESOURCE_ID=seed-tts-2.0`，默认音色 `DOUBAO_TTS_VOICE=zh_female_vv_uranus_bigtts`。若账号权限与默认值不匹配，按控制台修改。
5. 语音配置每次请求读取，保存后无需重启；访问 `/api/voice/status` 确认配置存在。这不是远端鉴权成功证明。

当前适配新版 `X-Api-Key` 鉴权；旧版 AppID + Access Token 不能直接填作这个 Key，需使用新版控制台或另行增加旧版鉴权适配。

## 调用流程

- `/api/voice/asr` 是浏览器到本地服务的 WebSocket。等待 `ready` 后发送二进制 16 kHz 单声道、小端 PCM16；发 `{"type":"finish"}` 结束，或 `{"type":"cancel"}` 取消。服务返回 `partial`／`final` 及 `text`，失败返回 `error` 和用户提示。
- 网关实时转发至 `wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async`，封装官方 gzip 二进制协议。最大录音 60 秒；识别中间结果不触发下单。
- `/api/voice/tts` 接收 `{"text":"短句"}`，向 `https://openspeech.bytedance.com/api/v3/tts/unidirectional` 请求合成，解码分块音频后聚合为 `audio/mpeg`。这是短句合成后播放，不声称已经实现音频边生成边播放。
- 录音和播报音频仅在内存中处理。声音会发送到火山语音服务，并非完全离线推理。请求限长、超时或权限失败时显示错误，不生成假的成功音频。

## 验收状态

离线单测覆盖二进制协议终包、序号、gzip、错误码、截断帧、解压上限、合成 base64、空白／超长文本、缺失 Key 和跨来源 WebSocket 拒绝。测试专用数据不连接真实账号。

2026-11-04 本机浏览器验证：点击语音入口，未配置 Key 时明确提示，保持文字入口可用；未请求麦克风权限。截图见 `voice-configuration-preview.jpg`。全量离线测试 36 项通过。

**真实网关链路已通过，真人麦克风待验收**：已通过本机 HTTP 接口生成 MP3，再以 200ms PCM16 分包通过本机 WebSocket 获得 partial 和 final 结果。以下浏览器真人交互仍需检查：

1. 用户主动点麦克风并授权，能看到实时识别；点停止后仅提交一次最终文本。
2. 说“帮我买份麦当劳，三十五元以内”，走真实门店与套餐推荐；读出的价格与卡片一致。
3. 能停止／重播介绍；录音开始前停止播报，避免回声误识别。
4. 拒绝麦克风授权、断网、Key 无权限时能退出录音并恢复打字。
5. 说“确认下单”仍须明确审阅具体方案，不绕过交易确认；默认真实订单开关保持关闭。

## 官方参考

- [大模型流式语音识别 API：鉴权、资源 ID 和二进制协议](https://docs.volcengine.com/docs/doubao-voice/large-model-streaming-automatic-speech-recognition-api-1?lang=en)
- [语音合成 HTTP 单向流式 API](https://docs.volcengine.com/docs/doubao-voice/unidirectional-streaming-text-to-speech-http?lang=zh)

接口与服务开通情况可能变化，以官方控制台及文档为准。

## 按用户提供的 ASR 文档校对

优化版 `bigmodel_async` 与二遍识别配置一致。常规音频分包调整为文档推荐的 200ms（16kHz 单声道 PCM16 为 6400 字节），结束时仍发送剩余尾帧；解析器兼容文档成功码 `20000000`，并保留无 code 返回格式。新增对应回归测试，离线测试共 37 项。真实账号验证结果见下文。

## 真实权限检查（2026-11-04）

使用本机凭据检查官方接口：ASR `volc.seedasr.sauc.duration` 返回 HTTP 403、requested resource not granted；TTS `seed-tts-2.0` 返回 HTTP 403、资源未授权（错误码 45000030）。用户提供的调用示例为录音文件识别资源 `volc.seedasr.auc`，不等于实时识别授权。尚待开通目标资源，不记录密钥或原始账号响应。补充 `python-socks` 依赖以支持本机现有 SOCKS 代理环境。

### 用户开通后首次复查（历史结果）

实时识别现已通过 WebSocket 鉴权，并收到可解析的官方协议响应（静音探针，不代表真人转录验收）。语音合成仍返回 HTTP 403 / 45000030，提示 `volc.seedtts.default` requested resource not granted；仍需确认同项目的语音合成 2.0 授权。未生成可播放问候音频。

### 最终权限生效与真实音频闭环（2026-11-04）

权限生效后，`POST /api/voice/tts` 返回 HTTP 200，实际生成 39213 字节 MP3。使用 macOS afconvert 转为 16kHz 单声道 PCM16，通过本机 `/api/voice/asr` 按 200ms 分包发送，得到 ready、多次 partial 以及 final：

> 你好，我是小瑞，帮我买一份麦当劳，预算35元。

这验证了真实语音合成、音频解码、流式识别和本地网关，不代表浏览器麦克风权限或真人方言效果已验收。合成测试音频保存在被忽略的 `.local-data/xiaorui-voice-greeting.mp3`，不含用户录音。此前 403 为权限生效前的历史检查结果。
