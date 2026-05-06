# Configuration

配置由 `app/core/config.py` 通过 Pydantic Settings 读取，默认从 `.env` 加载。

## 基础配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://admin:password@localhost:5432/doorhub` |
| `SECRET_KEY` | JWT 签名密钥 | `your-super-secret-key-change-in-production` |
| `ALGORITHM` | JWT 算法 | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Access Token 过期分钟数 | `60` |
| `APP_HOST` | 服务监听地址 | `0.0.0.0` |
| `APP_PORT` | 服务监听端口 | `8000` |
| `APP_RELOAD` | 是否启用 uvicorn reload | `False` |
| `APP_TIMEZONE` | 应用时区 | `Asia/Shanghai` |
| `RATE_LIMIT_PER_MINUTE` | API 限流阈值 | `100` |

## ZKTeco 设备配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ZK_DEVICE_IPS` | 设备 IP 列表，逗号分隔 | `192.168.1.201` |
| `ZK_DEVICE_PORT` | 设备端口 | `4370` |
| `ZK_DEVICE_TIMEOUT` | 连接超时秒数 | `5` |
| `ZK_DEVICE_ENCODING` | 设备字符编码 | `gbk` |
| `ZK_DEVICE_OMIT_PING` | 是否跳过 ping 检测 | `False` |

## 飞书配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `FEISHU_APP_ID` | 飞书企业应用 App ID | 空 |
| `FEISHU_APP_SECRET` | 飞书企业应用 App Secret | 空 |
| `FEISHU_VERIFICATION_TOKEN` | 飞书事件校验 Token | 空 |
| `FEISHU_ENCRYPT_KEY` | 飞书事件加密 Key | 空 |
| `FEISHU_ENABLE_LONG_CONNECTION` | 是否启用长连接 | `False` |
| `FEISHU_EVENT_SUBSCRIPTIONS` | 长连接订阅事件，逗号分隔 | `approval.approval.updated_v4,application.bot.menu_v6` |
| `FEISHU_LOG_LEVEL` | 飞书 SDK 日志等级 | `INFO` |
| `FEISHU_BOT_MENU_DOOR_OPEN_EVENT_KEY` | 单设备开门菜单事件 key | `door_open` |
| `FEISHU_BOT_MENU_DOOR_OPEN_DEVICE_IP` | 单设备菜单对应设备 IP | 空 |
| `FEISHU_BOT_MENU_DOOR_OPEN_SECONDS` | 菜单开门秒数 | `3` |
| `FEISHU_BOT_MENU_NOTIFY_OPERATOR` | 是否通知操作者 | `False` |
| `FEISHU_BOT_MENU_DEVICE_EVENT_MAP` | 多设备菜单映射 JSON | 空 |
| `FEISHU_BOT_MENU_ALLOWED_OPEN_IDS` | 允许操作的 open_id 白名单 | 空 |
| `FEISHU_BOT_MENU_ALLOWED_USER_IDS` | 允许操作的 user_id 白名单 | 空 |

多设备菜单映射示例：

```env
FEISHU_BOT_MENU_DEVICE_EVENT_MAP={"door_open_hq":"192.168.1.201","door_open_lab":"192.168.1.202"}
```

## 考勤配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ATTENDANCE_PLAN_START` | 默认上班时间 | `09:00` |
| `ATTENDANCE_PLAN_END` | 默认下班时间 | `18:00` |
| `ATTENDANCE_WORKDAY_PROVIDER` | 工作日来源 | `ailcc` |
| `ATTENDANCE_WORKDAY_API_URL` | 自定义工作日 API 地址 | 空 |
| `ATTENDANCE_AILCC_API_BASE_URL` | AILCC 节假日 API 地址 | `https://holiday.ailcc.com` |
| `ATTENDANCE_AILCC_API_TOKEN` | AILCC API Token | 空 |

## 安全建议

- 生产环境必须替换默认 `SECRET_KEY`。
- 首次启动后立即修改默认管理员密码。
- API Secret 明文只在创建时返回一次，应按凭据管理方式保存。
- 不要把 `.env` 提交到 Git。
