# Feishu Integration

飞书接入是系统内置模块，位于 `app/integrations/feishu/`。它不是插件化动态加载能力，而是一等公民集成。

## 模块职责

| 文件 | 职责 |
|------|------|
| `client.py` | 封装飞书开放平台 API 调用，例如发消息、查用户、获取 tenant access token |
| `longconn.py` | 负责 WebSocket 长连接建连、保活、重连和事件分发 |
| `handlers.py` | 承载飞书事件业务处理，例如审批事件、机器人菜单事件 |
| `schemas.py` | 定义飞书回调与事件载荷模型 |
| `router.py` | 处理 HTTP 回调，例如 URL 验证、卡片回调或后续 HTTP 事件入口 |

## 设计约束

- `handlers.py` 必须通过 `services/` 层操作业务数据。
- 事件处理器不直接访问 `repositories/`。
- 事件处理器不直接操作数据库 session。
- `router.py` 和 `longconn.py` 是两条独立通道。
- 生产事件消费主通道为长连接。

## 长连接事件

应用启动时由 FastAPI lifespan 自动尝试拉起飞书长连接守护。是否启用由 `FEISHU_ENABLE_LONG_CONNECTION` 控制。

当前默认订阅：

```env
FEISHU_EVENT_SUBSCRIPTIONS=approval.approval.updated_v4,application.bot.menu_v6
```

新增事件时，优先在 `handlers.py` 增加事件级处理函数，再决定是否下沉新的 `services/` 能力。

## 机器人菜单开门

单设备菜单示例：

```env
FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY=door_open
FEISHU_BOT_MENU_DOOR_OPEN_DEVICE_IP=192.168.1.201
FEISHU_BOT_MENU_DOOR_OPEN_SECONDS=3
```

多设备菜单示例：

```env
FEISHU_BOT_MENU_DEVICE_EVENT_MAP={"door_open_hq":"192.168.1.201","door_open_lab":"192.168.1.202"}
```

白名单示例：

```env
FEISHU_BOT_MENU_ALLOWED_OPEN_IDS=ou_xxx,ou_yyy
FEISHU_BOT_MENU_ALLOWED_USER_IDS=user_xxx,user_yyy
```

如果配置了白名单，只有命中的飞书用户可以触发开门。

## 扩展到其他平台

接入钉钉或企业微信时，在 `app/integrations/` 下平行增加目录：

```text
app/integrations/
├── feishu/
├── dingtalk/
└── wecom/
```

保持相同原则：

- 平台接入层处理第三方协议和事件编排。
- 业务逻辑统一回落到 `services/` 层。
- 不为单一平台引入额外插件系统。
