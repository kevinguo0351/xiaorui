# 北京滴滴场景

实现模块 `app/didi_scenario.py`：DidiScenario(transactions, provider=None)，公开 schemas 和 dispatch。模型只可查询、准备方案、查本人记录。共享事务管理器负责持久化、所有权、再次确认、执行前重核价、比较实质订单信息、重启和未知结果处理。

| 老人任务 | 实现与边界 |
|---|---|
| 帮我回家／去医院 | 本轮起点 + 明确保存目的地，真实 POI 搜索，确认具体接送点 |
| 大概要多少钱／便宜一点 | 实时报价与车型列表，不编造优惠可用性 |
| 选某车型／换地方 | 重新报价、准备确认方案，不直接发单 |
| 确认叫车 | 宿主调用 quote 后比较，再调用 execute；默认配置仍以宿主开关为准 |
| 司机来了吗／车牌是什么 | 仅查询本人已创建订单，保留官方状态、车型、车牌和预计时间 |
| 司机在哪里 | 进行中订单实际司机坐标，不推测老人位置 |
| 不坐了 | 查状态和明确取消费后准备取消；平台未给费用时停止并引导官方订单页 |
| 超时／断网／重启 | 不自动发单或取消；未知结果保持待核查 |
| 预约／修改进行中目的地／投诉退款 | 未实现，明确说明并转官方渠道 |

只读白名单需增加 `taxi_query_order`、`taxi_get_driver_location`；已有 `maps_textsearch`、`taxi_estimate`。写白名单只给 host-confirmed 通道增加 `taxi_create_order`、`taxi_cancel_order`。订单查询接受事务记录 action_id，manager.get 必须校验 owner；quote 和 execute 接口只供共享管理器调用。query_order(order_id) 供宿主轮询，不含司机电话。

官方依据：https://mcp.didichuxing.com/api 。本轮没有真实发单、取消或支付。离线适配器测试不构成真实交易验收；此前真实 POI 与估价证据仍适用，取消费用字段不能当作官方保证存在的字段。当前账号控制台提示 MCP 叫车可能个人账户免密支付，真实交易必须确认。

## 本轮验证补充

10 项滴滴专项离线测试通过：无候选不能准备、报价trace刷新不触发实质变化、价格变化必须重确认、取消费未知阻止提案、外部owner记录不查询、司机电话和路线脱敏、失败搜索清除旧报价、执行只用最新trace、陌生写响应保留私有核查证据、接送点附带ETA变化不影响比较。上述执行测试只注入测试响应，不连接远程写操作。

实际只读联调使用临时 SQLite ActionManager，enabled 永远为 false，查询北京西站与国贸商城，取得车型并准备本地确认方案；首次后续重核价遇间歇性连接失败。因此不能将该次运行声明为稳定闭环或真实发单验收。接送点比较只保留名称、地址和六位小数坐标，排除平台偶发附带字段；保留实际接送点变化的重确认要求。

## 真实模型聊天验收（隔离临时工作区）

所有订单执行开关固定 false；没有发单、取消或付款。下列为本轮实际模型回复和工具轨迹，公开地标不代表用户位置。

```json
[
  {
    "case": "home",
    "prompt": "帮我打车回家。",
    "reply": "您好，我可以帮您叫车回家。\n\n不过我还没看到您保存的家庭地址，也不能猜测当前位置。请告诉我：\n1. 您现在在哪里上车？（比如附近地标/小区名）\n2. 要回哪个地址？",
    "trace": [
      {
        "type": "run.started"
      },
      {
        "type": "run.completed"
      }
    ],
    "plan_count": 0
  },
  {
    "case": "cancel",
    "prompt": "帮我取消刚才叫的车。",
    "reply": "我这边没有查到您本人进行中的叫车记录，暂时不能准备取消。\n\n请您在滴滴官方 App 的“订单”里找到刚才那笔订单，查看是否还能取消及是否有取消费；也可以把订单页面情况告诉我，我再帮您一步步看。",
    "trace": [
      {
        "type": "run.started"
      },
      {
        "type": "tool.started",
        "name": "didi_list_rides"
      },
      {
        "type": "tool.completed",
        "name": "didi_list_rides"
      },
      {
        "type": "run.completed"
      }
    ],
    "plan_count": 0
  },
  {
    "case": "ride",
    "prompt": "仅做北京公开地点的只读演示，不是我的当前位置：从北京西站到国贸商城，请先查两个地点让我确认。",
    "reply": "北京西站查到了，推荐起点请选：\n\n1. 北京西站\n丰台区莲花池东路118号\n\n国贸商城这次查询失败，滴滴连接或权限暂时有问题，所以还不能估价或叫车。您可以稍后再试，或换个目的地名称（比如“国贸”）我再查。",
    "trace": [
      {
        "type": "run.started"
      },
      {
        "type": "tool.started",
        "name": "didi_search_places"
      },
      {
        "type": "tool.started",
        "name": "didi_search_places"
      },
      {
        "type": "tool.error",
        "name": "didi_search_places"
      },
      {
        "type": "tool.completed",
        "name": "didi_search_places"
      },
      {
        "type": "tool.failed",
        "name": "didi_search_places"
      },
      {
        "type": "run.completed"
      }
    ],
    "plan_count": 0
  },
  {
    "case": "ride",
    "prompt": "起点和终点都选刚才查询的第一个地点。帮我查真实车费，选择快车并准备方案给我确认，不要直接叫车。",
    "reply": "出行方案，操作：叫滴滴；车型：快车；预估费用：49.00元；实际上车点：北京西站-北侧-地下停车场P1-网约车点；实际下车点：北京中国大饭店；支付提醒：确认后会真实叫车，关联账号可能免密扣款；实际车费以平台结算为准。。本次预估费用 49.00 元。家人尚未开启这项真实交易执行，当前只准备方案。",
    "trace": [
      {
        "type": "run.started"
      },
      {
        "type": "tool.started",
        "name": "didi_search_places"
      },
      {
        "type": "tool.completed",
        "name": "didi_search_places"
      },
      {
        "type": "tool.started",
        "name": "didi_estimate_ride"
      },
      {
        "type": "tool.completed",
        "name": "didi_estimate_ride"
      },
      {
        "type": "tool.started",
        "name": "didi_prepare_ride"
      },
      {
        "type": "tool.completed",
        "name": "didi_prepare_ride"
      },
      {
        "type": "run.completed"
      }
    ],
    "plan_count": 1
  },
  {
    "case": "confirmation-disabled",
    "reply": "家人尚未开启这项真实订单执行；本次没有提交。",
    "trace": [
      {
        "type": "host.confirmation"
      }
    ]
  }
]
```
