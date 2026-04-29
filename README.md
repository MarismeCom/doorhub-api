# Door Access System 门禁管理系统

> 基于 ZKTeco SDK (pyzk 0.9) + Python 3.13 + PostgreSQL 16 + FastAPI

## 技术栈

| 组件 | 版本 |
|------|------|
| Python | 3.13.5 |
| PostgreSQL | 16+ |
| FastAPI | >=0.100.0 |
| SQLAlchemy | >=2.0 (AsyncSession) |
| ZK SDK | pyzk==0.9 |
| 环境管理 | uv |

---

## 项目结构

```
door-access-system/
├── app/
│   ├── main.py                    # FastAPI 应用入口
│   ├── deps.py                    # 统一依赖注入
│   ├── exceptions.py              # 自定义异常与全局 handler
│   ├── core/
│   │   ├── config.py              # 配置管理
│   │   ├── security.py            # JWT、密码哈希、默认管理员初始化
│   │   ├── scheduler.py           # 定时任务
│   │   ├── zk_client.py           # ZKTeco 设备客户端
│   │   └── auth.py                # 兼容层，转发到 security.py
│   ├── db/
│   │   ├── base.py                # SQLAlchemy Base 与模型注册
│   │   └── session.py             # AsyncSession、async engine、get_db
│   ├── models/
│   │   ├── user.py                # User
│   │   ├── system_user.py         # SystemUser
│   │   ├── device.py              # Device
│   │   ├── attendance.py          # Attendance、DoorLog
│   │   └── __init__.py
│   ├── schemas/
│   │   ├── user.py                # UserCreate / UserResponse / Token*
│   │   ├── system_user.py         # SystemUser* / ChangePasswordRequest
│   │   ├── device.py              # DeviceResponse / UnlockRequest
│   │   ├── attendance.py          # AttendanceResponse / SyncResponse
│   │   └── __init__.py
│   ├── repositories/
│   │   ├── user.py                # UserRepository
│   │   ├── system_user.py         # SystemUserRepository
│   │   ├── device.py              # DeviceRepository
│   │   ├── attendance.py          # AttendanceRepository / DoorLogRepository
│   ├── services/
│   │   ├── user.py                # 门禁用户业务
│   │   ├── system_user.py         # 系统用户业务
│   │   ├── device.py              # 设备管理业务
│   │   ├── attendance.py          # 考勤同步业务
│   │   ├── door.py                # 门禁控制业务
│   ├── integrations/              # 所有第三方对接统一放这里
│   │   └── feishu/                # 飞书集成模块
│   │       ├── __init__.py
│   │       ├── client.py          # 飞书 API 封装（发消息、查用户等）
│   │       ├── longconn.py        # 长链接 WebSocket 守护与事件分发
│   │       ├── handlers.py        # 飞书事件处理器（审批、打卡通知等）
│   │       ├── schemas.py         # 飞书回调报文模型
│   │       └── router.py          # /api/v1/feishu/** HTTP 回调入口
│   ├── api/
│   │   ├── __init__.py
│   │   ├── v1/                    # 标准 API 版本入口（async）
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── system_users.py
│   │   │   ├── devices.py
│   │   │   ├── attendances.py
│   │   │   ├── door.py
│   │   │   ├── feishu.py / 或集成 router 挂载点
│   │   │   └── __init__.py
├── alembic/                 # 数据库迁移
│   ├── env.py
│   └── versions/
│       ├── 001_init_tables.py
│       └── 002_add_system_users.py
├── tests/                   # 单元测试
│   └── integrations/
│       └── feishu/
│           ├── test_client.py
│           └── test_handlers.py
├── pyproject.toml           # 项目配置
├── alembic.ini              # Alembic 配置
├── .env.example             # 环境变量模板
├── start.py                 # 启动脚本
└── README.md
```

说明：
- 当前主链路是严格的 `api/v1 -> services -> repositories -> models -> db/session.py` async 结构。
- 项目已移除旧兼容层，不再保留 `app/api/routes`、`app/routers`、`app/database.py`、`app/*_service.py`、`app/*_repository.py`、顶层转发文件。

---

## 飞书接入设计

### 模块归属

飞书接入设计为系统内置模块，放在 `app/integrations/feishu/`，而不是做成插件化动态加载能力。

原因：
- 飞书集成需要直接复用现有 `db`、`services`、`deps`，属于系统一等公民能力。
- 当前业务边界清晰，插件化不会带来可观收益，反而会增加生命周期管理、依赖注入、配置装配和测试复杂度。
- 以内置模块实现，更符合现有分层架构，也更利于后续维护和联调。

当前接入方式采用飞书企业应用“事件与回调”中的长连接模式，基于飞书官方 Python Server SDK 的 `lark_oapi.ws.Client` 实现事件消费。

### 职责分层

`app/integrations/feishu/` 内部职责需要严格分工：

- `client.py`：封装飞书开放平台 API 调用，例如发消息、查用户、获取 tenant access token 等。
- `longconn.py`：只负责长链接保活、WebSocket 建连、重连和事件分发，不承载业务逻辑。
- `handlers.py`：承载飞书事件的业务处理逻辑，例如审批事件、打卡通知、人员同步触发等。
- `schemas.py`：定义飞书回调与事件载荷的 Pydantic 模型，负责报文解析和结构约束。
- `router.py`：只处理飞书平台发起的 HTTP 回调，例如 URL 验证、事件回调入口。

明确约束：
- `handlers.py` 必须通过 `services/` 层操作业务数据。
- 事件处理器不直接访问 `repositories/`，也不直接操作数据库 session。
- `router.py` 与 `longconn.py` 是两条独立通道：前者处理 HTTP 回调，后者处理长链接事件，不互相混用职责。
- 生产事件消费主通道为长连接；`router.py` 保留给 URL 验证、卡片回调或后续确需 HTTP 回调的场景。

### 扩展策略

后续如果接入钉钉或企业微信，直接在 `app/integrations/` 下平行增加新目录即可，例如：

```text
app/integrations/
├── feishu/
├── dingtalk/
└── wecom/
```

要求保持结构和职责对称，沿用相同设计原则：
- 平台接入层只处理第三方协议和事件编排。
- 所有业务逻辑统一回落到 `services/` 层。
- 不为单一平台引入额外插件系统，避免架构复杂化。

### 当前开发约定

- 使用飞书官方 Python SDK：`lark-oapi`
- 应用启动时由 FastAPI `lifespan` 自动拉起飞书长连接守护线程
- 当前默认通过 `FEISHU_EVENT_SUBSCRIPTIONS` 配置要注册的事件类型，使用通用 `register_p2_customized_event(...)` 分发到 `handlers.py`
- 如需新增审批、通讯录、门禁相关事件，优先在 `handlers.py` 增加事件级处理函数，再决定是否下沉新的 `services/` 能力
- 机器人自定义菜单事件使用 `application.bot.menu_v6`；例如菜单项 `event_key=door_open` 可映射到门禁开门动作
- 多设备菜单可通过 `FEISHU_BOT_MENU_DEVICE_EVENT_MAP` 配置，例如 `{"door_open_hq":"192.168.1.201","door_open_lab":"192.168.1.202"}`
- 建议通过 `FEISHU_BOT_MENU_ALLOWED_OPEN_IDS` / `FEISHU_BOT_MENU_ALLOWED_USER_IDS` 配置允许操作的飞书用户白名单

---

## 快速开始

### 环境要求

> **⚠️ 严禁使用系统 Python 环境**，必须使用 uv 创建的虚拟环境

### 1. 创建虚拟环境（必须）
```bash
uv venv .venv
source .venv/bin/activate
```

### 2. 安装依赖
```bash
uv sync --extra dev
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，配置数据库连接等信息
```

当前默认示例数据库连接：

```env
DATABASE_URL=postgresql://postgres:123456@10.64.69.61:5432/doorhub
```

#### 生成 JWT `SECRET_KEY`

请不要直接使用示例里的默认 `SECRET_KEY`，建议用随机高强度字符串替换。可以使用以下任一方式生成：

```bash
# openssl
openssl rand -hex 32
```

```bash
# Python
python -c "import secrets; print(secrets.token_hex(32))"
```

```bash
# uv 环境
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

生成后写入 `.env`：

```env
SECRET_KEY=替换成你生成的随机字符串
```

### 4. 数据库迁移
```bash
uv run alembic upgrade head
```

### 5. 启动服务
```bash
# 方式 1：直接用 uvicorn
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 方式 2：使用项目脚本
uv run start
```

### 6. 访问 API 文档
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

## Docker 部署

### 后端 Dockerfile

后端已提供 [Dockerfile](/Users/airsmon/Documents/marisme/01_Projects/doorhub/backend/Dockerfile)，可直接在 `backend` 目录构建：

```bash
cd /Users/airsmon/Documents/marisme/01_Projects/doorhub/backend
docker build -t doorhub-backend:latest .
```

运行示例：

```bash
docker run -d \
  --name doorhub-backend \
  -p 8000:8000 \
  --env-file .env \
  doorhub-backend:latest
```

### 前端 Dockerfile

前端已提供 [Dockerfile](/Users/airsmon/Documents/marisme/01_Projects/doorhub/frontend/Dockerfile)，并附带 [nginx.conf](/Users/airsmon/Documents/marisme/01_Projects/doorhub/frontend/nginx.conf)：

```bash
cd /Users/airsmon/Documents/marisme/01_Projects/doorhub/frontend
docker build -t doorhub-frontend:latest .
```

运行示例：

```bash
docker run -d \
  --name doorhub-frontend \
  -p 8080:80 \
  doorhub-frontend:latest
```

### Nginx 反向代理示例

如果你希望由宿主机 Nginx 统一代理前后端，可以参考下面配置：

```nginx
server {
    listen 80;
    server_name doorhub.example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /redoc {
        proxy_pass http://127.0.0.1:8000/redoc;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

说明：
- 前端容器监听 `8080`
- 后端容器监听 `8000`
- `/api/`、`/docs`、`/redoc` 都转发到 FastAPI
- 其余请求交给前端静态站点

---

## API 接口文档

### 认证接口

#### 认证说明

- 系统登录用户与门禁设备用户已分离
- 登录用户角色分为 `admin` 和 `user`
- 当前受保护接口支持 JWT Bearer Token
- 当前受保护接口也支持 API Secret
- 应用启动时会自动确保默认管理员存在

#### API Secret 说明

- API Secret 归属某个系统用户
- 每个系统用户最多只支持 `3` 个有效 API Secret
- API Secret 支持设置过期时间
- 明文 Secret 只会在创建成功时返回一次
- 已过期或已撤销 Secret 不能继续调用接口

传递方式支持以下两种：

```bash
-H "X-API-Secret: sk_xxx"
```

```bash
-H "Authorization: Bearer sk_xxx"
```

#### 默认管理员

- 用户名：`admin`
- 密码：`admin`
- 角色：`admin`

#### 获取访问令牌
```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

**响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer",
    "expires_in": 3600,
    "role": "admin"
  }
}
```

#### 刷新访问令牌
```bash
curl -X POST "http://localhost:8000/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "your_refresh_token"}'
```

#### 获取当前登录用户
```bash
curl -X GET "http://localhost:8000/api/v1/system-users/me" \
  -H "Authorization: Bearer your_access_token"
```

#### 使用 API Secret 获取当前登录用户
```bash
curl -X GET "http://localhost:8000/api/v1/system-users/me" \
  -H "X-API-Secret: sk_xxx"
```

---

### 系统用户管理接口

> 系统用户用于后台登录与权限控制，和门禁设备里的 `users` 表不是同一类数据。

#### 获取系统用户列表
```bash
curl -X GET "http://localhost:8000/api/v1/system-users" \
  -H "Authorization: Bearer your_access_token"
```

#### 创建系统用户
```bash
curl -X POST "http://localhost:8000/api/v1/system-users" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "username": "operator01",
    "password": "secret123",
    "role": "user"
  }'
```

#### 获取系统用户详情
```bash
curl -X GET "http://localhost:8000/api/v1/system-users/operator01" \
  -H "Authorization: Bearer your_access_token"
```

#### 更新系统用户角色或启用状态
```bash
curl -X PATCH "http://localhost:8000/api/v1/system-users/operator01" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "role": "admin",
    "is_active": true
  }'
```

#### 管理员重置系统用户密码
```bash
curl -X POST "http://localhost:8000/api/v1/system-users/operator01/reset-password" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "new_password": "newsecret123"
  }'
```

#### 当前用户修改自己的密码
```bash
curl -X POST "http://localhost:8000/api/v1/system-users/me/change-password" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "old_password": "admin",
    "new_password": "admin456"
  }'
```

#### 获取系统用户的 API Secret 列表
```bash
curl -X GET "http://localhost:8000/api/v1/system-users/operator01/api-secrets" \
  -H "Authorization: Bearer your_access_token"
```

#### 创建 API Secret
```bash
curl -X POST "http://localhost:8000/api/v1/system-users/operator01/api-secrets" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "name": "doorhub-integration",
    "expires_at": "2026-12-31T23:59:59+08:00"
  }'
```

**响应示例：**
```json
{
  "code": 0,
  "message": "API Secret 创建成功，请立即保存明文 Secret",
  "data": {
    "secret": "sk_xxxxxxxxxxxxxxxxxxxxxxxxx",
    "secret_meta": {
      "id": 1,
      "name": "doorhub-integration",
      "secret_prefix": "sk_xxxxxxxx",
      "expires_at": "2026-12-31T15:59:59+00:00",
      "last_used_at": null,
      "revoked_at": null,
      "created_at": "2026-04-29T10:00:00+00:00"
    }
  }
}
```

#### 撤销 API Secret
```bash
curl -X DELETE "http://localhost:8000/api/v1/system-users/operator01/api-secrets/1" \
  -H "Authorization: Bearer your_access_token"
```

#### 使用 API Secret 调用业务接口
```bash
curl -X GET "http://localhost:8000/api/v1/users?page=1&page_size=20" \
  -H "X-API-Secret: sk_xxx"
```

#### 角色说明
| role | 说明 |
|------|------|
| `admin` | 管理员，可管理系统用户、门禁用户、同步和开门 |
| `user` | 普通用户，可使用普通受保护接口 |

---

### 门禁用户管理接口（两步流程）

> 这里的用户是门禁设备用户，不是系统登录用户。当前支持两类同步流程：
>
> 1. 本地数据库 -> 设备：先在本地创建/删除，再推送到 ZK 设备
> 2. 设备 -> 本地数据库：先预览设备用户，再选择只写入缺失用户或覆盖本地用户

#### 获取用户列表
```bash
curl -X GET "http://localhost:8000/api/v1/users?page=1&page_size=20"
```

**响应示例：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "total": 1,
    "page": 1,
    "page_size": 20,
    "users": [
      {
        "uid": 1,
        "user_id": "EMP001",
        "name": "张三",
        "privilege": 0,
        "password": "",
        "card": 0,
        "sync_status": "pending",
        "created_at": "2026-04-28T10:00:00+08:00"
      }
    ]
  }
}
```

#### 创建用户（第一步：仅保存到本地数据库，状态为 pending）
```bash
curl -X POST "http://localhost:8000/api/v1/users" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "name": "张三",
    "user_id": "EMP001",
    "privilege": 0,
    "password": "",
    "group_id": "1",
    "card": 0,
    "device_ip": "192.168.1.201"
  }'
```
**响应：**
```json
{
  "code": 0,
  "message": "用户创建成功（待同步）",
  "data": {
    "uid": 1,
    "user_id": "EMP001",
    "name": "张三",
    "password": "",
    "sync_status": "pending"
  }
}
```

#### 删除用户（第一步：仅本地软删除，状态为 pending_delete）
```bash
curl -X DELETE "http://localhost:8000/api/v1/users/EMP001" \
  -H "Authorization: Bearer your_access_token"
```

#### 同步单个用户到 ZK 设备（第二步）
```bash
curl -X POST "http://localhost:8000/api/v1/users/EMP001/sync?device_ip=192.168.1.201" \
  -H "Authorization: Bearer your_access_token"
```
**响应：**
```json
{
  "code": 0,
  "message": "同步成功",
  "data": {
    "status": "success",
    "message": "同步成功"
  }
}
```

#### 批量同步所有待同步用户到 ZK 设备
```bash
curl -X POST "http://localhost:8000/api/v1/users/sync/batch?device_ip=192.168.1.201" \
  -H "Authorization: Bearer your_access_token"
```
**响应：**
```json
{
  "code": 0,
  "message": "批量同步完成: 成功 5, 失败 0",
  "data": {
    "total": 5,
    "success": 5,
    "failed": 0,
    "errors": []
  }
}
```

#### 获取同步状态
```bash
# 获取所有待同步用户状态
curl -X GET "http://localhost:8000/api/v1/users/sync/status"

# 获取指定用户状态
curl -X GET "http://localhost:8000/api/v1/users/sync/status?user_id=EMP001"
```
**响应：**
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "pending_count": 2,
    "users": [
      {"user_id": "EMP001", "name": "张三", "sync_status": "pending", "sync_error": null},
      {"user_id": "EMP002", "name": "李四", "sync_status": "failed", "sync_error": "设备连接超时"}
    ]
  }
}
```

#### 从设备预览同步到本地数据库

> 推荐前端先调用预览接口，展示“本地缺失用户”“本地差异用户”“UID 冲突用户”，再让操作员决定后续动作。

```bash
curl -X POST "http://localhost:8000/api/v1/users/sync/from-device" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "device_ip": "192.168.1.201",
    "mode": "preview"
  }'
```

**响应示例：**
```json
{
  "code": 0,
  "message": "设备用户预览完成",
  "data": {
    "device_ip": "192.168.1.201",
    "mode": "preview",
    "device_total": 10,
    "local_total": 8,
    "matched_count": 6,
    "missing_in_local_count": 2,
    "different_in_local_count": 1,
    "uid_conflict_count": 1,
    "inserted_count": 0,
    "updated_count": 0,
    "skipped_count": 2,
    "supported_actions": ["preview", "write_missing", "overwrite_local"],
    "missing_in_local": [
      {
        "uid": 9,
        "user_id": "EMP009",
        "name": "王五",
        "privilege": 0,
        "password": "",
        "card": 10009,
        "action": "missing_in_local",
        "local_snapshot": null
      }
    ],
    "different_in_local": [
      {
        "uid": 2,
        "user_id": "EMP002",
        "name": "李四-设备",
        "privilege": 0,
        "password": "",
        "card": 10002,
        "action": "different_in_local",
        "local_snapshot": {
          "uid": 2,
          "user_id": "EMP002",
          "name": "李四",
          "privilege": 0,
          "password": "",
          "group_id": "",
          "card": 0,
          "sync_status": "synced"
        }
      }
    ],
    "uid_conflicts": [
      {
        "uid": 3,
        "user_id": "EMP099",
        "name": "冲突用户",
        "privilege": 0,
        "password": "",
        "card": 0,
        "action": "uid_conflict",
        "local_snapshot": {
          "uid": 3,
          "user_id": "EMP003",
          "name": "赵六",
          "privilege": 0,
          "password": "",
          "group_id": "",
          "card": 0,
          "sync_status": "synced"
        }
      }
    ]
  }
}
```

#### 从设备写入本地缺失用户

> 对应前端按钮建议：`写入缺失用户`

```bash
curl -X POST "http://localhost:8000/api/v1/users/sync/from-device" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "device_ip": "192.168.1.201",
    "mode": "write_missing"
  }'
```

#### 用设备数据覆盖本地并写入缺失用户

> 对应前端按钮建议：`覆盖本地数据库`

```bash
curl -X POST "http://localhost:8000/api/v1/users/sync/from-device" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "device_ip": "192.168.1.201",
    "mode": "overwrite_local"
  }'
```

#### 设备 -> 本地同步模式说明
| mode | 说明 |
|------|------|
| `preview` | 只预览差异，不修改本地数据库 |
| `write_missing` | 只把本地缺失的设备用户写入本地 |
| `overwrite_local` | 用设备数据覆盖本地差异用户，并写入本地缺失用户 |

#### 同步状态说明
| status | 说明 |
|--------|------|
| `pending` | 待同步（新建/修改） |
| `synced` | 已同步到设备 |
| `pending_delete` | 待同步删除 |
| `synced_deleted` | 已从设备删除 |
| `failed` | 同步失败 |

---

### 打卡记录接口

#### 获取打卡记录
```bash
curl -X GET "http://localhost:8000/api/v1/attendances?user_id=EMP001&start_date=2024-01-01T00:00:00Z&end_date=2024-01-31T23:59:59Z&page=1&page_size=20"
```

#### 手动同步打卡记录
```bash
curl -X POST "http://localhost:8000/api/v1/attendances/sync" \
  -H "Content-Type: application/json" \
  -d '{"device_ip": "192.168.1.201", "incremental": true}'
```

---

### 门禁控制接口

#### 远程开门
```bash
curl -X POST "http://localhost:8000/api/v1/door/unlock" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer your_access_token" \
  -d '{
    "device_ip": "192.168.1.201",
    "unlock_seconds": 3,
    "remark": "访客放行"
  }'
```

#### 获取开门记录
```bash
curl -X GET "http://localhost:8000/api/v1/door/logs?device_ip=192.168.1.201&page=1&page_size=20"
```

---

### 设备管理接口

#### 获取设备列表
```bash
curl -X GET "http://localhost:8000/api/v1/devices"
```

#### 获取设备状态
```bash
curl -X GET "http://localhost:8000/api/v1/devices/192.168.1.201/status"
```

---

### 健康检查

#### 健康检查端点
```bash
curl -X GET "http://localhost:8000/health"
```

**响应：**
```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "timestamp": "2024-01-15T10:30:00"
}
```

---

## 通用响应格式

### 成功响应
```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

### 错误响应
```json
{
  "code": 4001,
  "message": "未授权",
  "detail": "Token 已过期，请重新登录",
  "request_id": "req_abc123"
}
```

### 错误码说明

| code | 说明 |
|------|------|
| 0 | 成功 |
| 1001 | 设备连接失败 |
| 1002 | 设备操作超时 |
| 2001 | 用户不存在 |
| 2002 | 用户 ID 已存在 |
| 2003 | 批量操作部分失败 |
| 3001 | 开门指令失败 |
| 4001 | 未授权（Token 无效） |
| 4002 | Token 已过期 |
| 4003 | 刷新 Token 失败 / 权限不足 |
| 4004 | 超出 API 请求限制 |
| 5000 | 服务器内部错误 |
| 5001 | 数据库操作失败 |
| 5002 | 设备响应异常 |

---

## 环境变量配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DATABASE_URL | PostgreSQL 连接字符串 | postgresql://postgres:123456@10.64.69.61:5432/doorhub |
| SECRET_KEY | JWT 密钥 | your-super-secret-key-change-in-production |
| ALGORITHM | JWT 算法 | HS256 |
| ACCESS_TOKEN_EXPIRE_MINUTES | Token 过期时间(分钟) | 60 |
| ZK_DEVICE_IPS | ZK 设备 IP 列表(逗号分隔) | 192.168.1.201,192.168.1.202 |
| ZK_DEVICE_PORT | ZK 设备端口 | 4370 |
| ZK_DEVICE_TIMEOUT | 设备连接超时(秒) | 5 |
| ZK_DEVICE_ENCODING | 设备字符编码 | gbk |
| SYNC_INTERVAL_MINUTES | 打卡记录同步间隔(分钟) | 5 |
| RATE_LIMIT_PER_MINUTE | API 限流(每分钟) | 100 |
| APP_HOST | 服务监听地址 | 0.0.0.0 |
| APP_PORT | 服务监听端口 | 8000 |

---

## 运行测试

```bash
# 运行所有测试
uv run pytest

# 运行指定测试文件
uv run pytest tests/test_basic.py -v

# 代码检查
uv run ruff check .
uv run mypy .
```

---

## API 接口总览

| 方法 | 路径 | 描述 | 认证 |
|------|------|------|------|
| POST | `/api/v1/auth/login` | 获取访问令牌 | 否 |
| POST | `/api/v1/auth/refresh` | 刷新访问令牌 | 否 |
| GET | `/api/v1/system-users/me` | 获取当前系统用户 | 是 |
| GET | `/api/v1/system-users` | 获取系统用户列表 | 是（管理员） |
| POST | `/api/v1/system-users` | 创建系统用户 | 是（管理员） |
| GET | `/api/v1/system-users/{username}` | 获取系统用户详情 | 是（管理员） |
| PATCH | `/api/v1/system-users/{username}` | 更新系统用户角色/状态 | 是（管理员） |
| POST | `/api/v1/system-users/{username}/reset-password` | 重置系统用户密码 | 是（管理员） |
| GET | `/api/v1/system-users/{username}/api-secrets` | 获取 API Secret 列表 | 是（管理员） |
| POST | `/api/v1/system-users/{username}/api-secrets` | 创建 API Secret | 是（管理员） |
| DELETE | `/api/v1/system-users/{username}/api-secrets/{secret_id}` | 撤销 API Secret | 是（管理员） |
| POST | `/api/v1/system-users/me/change-password` | 当前用户修改密码 | 是 |
| GET | `/api/v1/users` | 获取门禁用户列表 | 否 |
| POST | `/api/v1/users` | 创建用户（本地 pending） | 是 |
| DELETE | `/api/v1/users/{user_id}` | 设置用户离职（本地 pending_disable） | 是 |
| POST | `/api/v1/users/{user_id}/sync` | 同步单个用户到设备 | 是 |
| POST | `/api/v1/users/sync/batch` | 批量同步待同步用户 | 是 |
| POST | `/api/v1/users/sync/from-device` | 从设备同步用户到本地（预览/写入/覆盖） | 是 |
| GET | `/api/v1/users/sync/status` | 获取同步状态 | 否 |
| GET | `/api/v1/attendances` | 获取打卡记录 | 否 |
| POST | `/api/v1/attendances/sync` | 同步打卡记录 | 否 |
| POST | `/api/v1/door/open` | 远程开门 | 是 |
| POST | `/api/v1/door/close` | 门状态关闭指令说明 | 是 |
| GET | `/api/v1/door/logs` | 获取开门记录 | 否 |
| GET | `/api/v1/devices` | 获取设备列表 | 否 |
| GET | `/api/v1/devices/{ip}/status` | 获取设备状态 | 否 |
| GET | `/health` | 健康检查 | 否 |

---

## 版本信息

- 文档版本：v1.3
- 生成时间：2026-04-28


## 待进行

### 前端界面

门禁用户
1. 门禁用户页面：样式错乱、本地门禁用户增加查询功能

设备管理
1. 设备管理：设备列表中增加状态字段；增加删除、编辑按钮

打卡记录
1. 打卡记录：筛选条件需要更新：组件使用日期、用户支持模糊搜索；
2. 用户ID联动门禁用户，显示用户名称
3. 打开时间：时间错乱，使用Asia/Shanghai时区
4. 状态：状体是什么含义？打开类型转换为枚举类型（比如生物、密码、ID卡）

其他优化

工作台
1. 增加统计功能：用户数量、打开记录数
