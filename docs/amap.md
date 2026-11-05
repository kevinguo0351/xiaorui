# 高德地图接入

使用官方 REST API，无额外 SDK。地点搜索、地理编码、步行／驾车路线与实时天气通过四个 `amap_` 工具接入现有 Agent。服务地址固定为 `https://restapi.amap.com`，不接受模型传任意 URL，失败不使用 mock 回退。该能力没有创建订单或支付权限。

在[高德控制台](https://console.amap.com/dev/key/app)创建应用，添加「Web服务」类型 Key，填入项目 `.env` 的 `AMAP_KEY=`。不要使用 JS API 类型 Key，不要提交或在聊天发送 Key。Key 仅后端读取并对 HTTP 日志脱敏。官方服务的额度和权限以控制台为准；服务拒绝时不声称查询成功。

示例：说“查一下北京西站到国贸怎么走”，小瑞搜索起终点，请用户确认候选后查询路线。地点可用 `amap_geocode` 解析明确地址；路线只使用当前会话查到的高德坐标。返回米、秒、最多三条路线与关键道路指引，以及官方地图路线链接。只有步行和驾车，不宣称实时跟随导航、偏航重算或滴滴已叫车。地图路线链接不含 Key，但含所选地点，用户点击后会交给高德地图。

天气示例：“北京今天天气怎么样？”先取得城市 adcode，再读取官方天气与 reporttime。当前不使用 IP 定位，不猜用户位置，不把地理编码或测试地标记作家。

官方资料：[地点搜索](https://lbs.amap.com/api/webservice/guide/api/search)、[地理编码](https://lbs.amap.com/api/webservice/guide/api/georegeo)、[路线规划](https://lbs.amap.com/api/webservice/guide/api/newroute)、[天气](https://lbs.amap.com/api/webservice/guide/api/weatherinfo)。

离线测试使用注入的 HTTP／服务响应，仅验证端点、凭据保护、真实候选的参数传递、失败清空候选、单位和报告时间保留，不代替官方真实联调。开发时本地未配置 AMAP_KEY，因此官方查询与真实模型完整流程尚待 Key 配置后验收。
