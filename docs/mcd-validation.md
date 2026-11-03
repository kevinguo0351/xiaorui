# 麦当劳真实 MCP 验证

当前状态：已连接官方账号，工具发现、真实门店查询、菜单查询、套餐详情和核价通过。未创建订单。

## 用户需要配置

1. 打开 [麦当劳 MCP 官方平台](https://open.mcd.cn/mcp)。
2. 用本人手机号登录，进入控制台，阅读并同意服务协议，激活 MCP Token。
3. 仅在项目根目录 `.env` 填写 `MCD_MCP_TOKEN=`，不粘贴到聊天或 GitHub。

来源：[官方接入指南](https://github.com/M-China/mcd-mcp-server)。服务为 Streamable HTTP，地址 `https://mcp.mcd.cn`，Authorization 使用 Bearer Token。

## 已准备的验证脚本

使用隔离环境中已安装的官方 MCP Python SDK，不增加新的依赖。

```sh
.research/nanobot/venv/bin/python experiments/mcd_probe.py
```

默认只握手并发现工具，保存当前账号实际可见的工具和 JSON Schema。每次验证都重新发现工具，不根据旧文档猜测参数。未知工具默认拒绝，服务端 readOnlyHint 不构成执行授权。

工具 schema 写入 `docs/research/2026-11-04/mcd-probe/tool-catalog.json`；读取结果仅写入被 Git 忽略的 `.research/mcd/`，设置文件权限 0600。报告不保存地址、账号信息或参数，仅记录状态和结果位置。

指定查询工具：

```sh
.research/nanobot/venv/bin/python experiments/mcd_probe.py --tool query-nearby-stores --args-file .research/mcd/store-query.json
```

参数文件根据实际发现的 schema 和用户指定地点填写；当前没有创建示例参数以免伪造门店或城市。离线准备只验证脚本能导入、缺凭证时退出和拒绝写操作，不宣称真实接口已跑通。

## 下一阶段

按自取顺序验证：工具发现 → 确定测试门店 → 查询菜单 → 餐品详情 → 核价。核价返回后检查商品、取餐方式、总价和必要参数，才准备订单确认模块。

本脚本明确不支持 create-order、cancel-order、领取优惠券、积分兑换、抽奖或修改地址。它没有实现交易确认模块，不能通过添加一个命令行参数直接开始下单。

真实订单创建需完成绑定具体方案的后端确认控制后，再由用户明确确认执行。MCP 层没有报错不等于业务成功，业务返回必须独立检查；核价不成功时不能使用模型估计的价格替代。

## 实际联调结果（2026-11-04）

用户提供 Token 后保存到被忽略的本地 `.env`，未写入源码或公开报告。使用官方 MCP Python SDK 连接 `https://mcp.mcd.cn` 成功，发现 36 个工具，包括下单能力，但脚本只允许白名单查询。

测试地点为上海人民广场，是公开接口测试地点，不代表用户当前位置。调用链：

1. `query-nearby-stores`：业务成功，返回 5 家门店。
2. 选择返回结果中的麦当劳上海黄浦华旭国际大厦餐厅。
3. `query-meals`：业务成功，返回 52 个商品。
4. `query-meal-detail`：获取板烧鸡腿堡三件套的真实轮次、选项和编码。
5. `calculate-price`：使用详情中的默认组合，业务成功，返回金额 3450；与菜单展示的 34.50 元一致。组合为板烧鸡腿堡、中薯条、可乐中杯。

已检查门店编码、套餐编码、数量和金额在返回链中一致；所有调用的业务 `success=true`、`code=200`，不是仅检查 HTTP 或 MCP 成功。

原始结果只保存在被忽略的 `.research/mcd/`。去除凭证的验证摘要见 [verified-summary.json](research/2026-11-04/mcd-probe/verified-summary.json)。菜单和价格只是本次查询快照，下单前必须重查。

## 接入时发现的差异

- 实际工具 schema 与公开文档示例有差异。例如附近门店查询的当前 searchType 枚举仅 1、2，不能直接照旧文档传经纬度参数。
- MCP 文本返回带有展示说明和 JSON 业务内容；新增 `mcd_payload.py` 提取明确的业务对象，不执行说明文字。无法识别的返回保留为未验证，不能编造业务成功。
- 到店自取不传 beCode；具体套餐要用真实 round 和商品 code 组合，不能只传套餐名。
- 未使用优惠券、随单会员卡或积分；未验证饮食限制、外送、订单创建及支付链接。

这意味着麦当劳可继续作为交易主场景候选，但 A1 验收尚未完成。下一步先实现具体方案的二次确认与重复执行保护，再经用户确认验证订单创建。
