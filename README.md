# DoorHub API

DoorHub API 是基于 FastAPI、PostgreSQL 和 ZKTeco 设备协议的门禁管理后端，负责系统登录、门禁用户、设备管理、打卡记录、远程开门、飞书事件接入和后台同步任务。

详细文档已整理到 GitHub Wiki 结构，见 [wiki/Home.md](wiki/Home.md)。

## 支持设备

| 品牌 / 协议 | 型号 | 支持状态 | 说明 |
| --- | --- | --- | --- |
| ZK / ZKTeco | xFace600 | 已测试支持 | 当前已完成门禁用户、打卡流水、设备状态与远程开门等核心流程测试 |

## 技术栈

| 组件 | 版本 / 说明 |
|------|-------------|
| Python | 3.13+ |
| FastAPI | API 服务与 OpenAPI 文档 |
| PostgreSQL | 16+ |
| SQLAlchemy | 2.x async ORM |
| Alembic | 数据库迁移 |
| pyzk | 0.9，ZKTeco 设备通信 |
| uv | Python 环境与依赖管理 |

## 项目架构

```text
doorhub-api/
├── app/
│   ├── main.py                  # FastAPI 应用入口、lifespan、路由注册
│   ├── deps.py                  # 数据库、当前用户、管理员等依赖注入
│   ├── exceptions.py            # 统一异常处理
│   ├── api/v1/                  # HTTP API 路由
│   ├── core/                    # 配置、安全、运行时、设备客户端、后台任务
│   ├── db/                      # SQLAlchemy Base、engine、AsyncSession
│   ├── integrations/feishu/     # 飞书开放平台接入
│   ├── models/                  # 数据库模型
│   ├── repositories/            # 数据访问层
│   ├── schemas/                 # Pydantic 请求与响应模型
│   └── services/                # 业务服务层
├── alembic/                     # 数据库迁移脚本
├── tests/                       # 自动化测试
├── Dockerfile                   # 后端镜像构建
├── pyproject.toml               # 项目依赖与工具配置
├── start.py                     # `uv run start` 入口
└── wiki/                        # GitHub Wiki 页面源文件
```

主链路保持为：

```text
api/v1 -> services -> repositories -> models -> db/session.py
```

第三方平台接入放在 `app/integrations/`，业务逻辑仍回落到 `services/` 层。

## 快速使用

### 1. 创建虚拟环境

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
```

至少需要确认：

```env
DATABASE_URL=postgresql://admin:password@localhost:5432/doorhub
SECRET_KEY=replace-with-a-random-secret
ZK_DEVICE_IPS=192.168.1.201
```

生产环境请用随机强密钥替换 `SECRET_KEY`：

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

### 4. 初始化数据库

```bash
uv run alembic upgrade head
```

### 5. 启动服务

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

或使用项目脚本：

```bash
uv run start
```

启动后访问：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health

默认管理员会在应用启动时自动确保存在：

| 用户名 | 密码 | 角色 |
|--------|------|------|
| `admin` | `admin` | `admin` |

首次部署后请立即修改默认密码。

## 常用命令

```bash
# 运行测试
uv run pytest

# 代码检查
uv run ruff check .
uv run mypy .

# 构建镜像
docker build -t doorhub-api:latest .

# 运行容器
docker run -d --name doorhub-api -p 8000:8000 --env-file .env doorhub-api:latest
```

## API 入口

| 模块 | 路径前缀 |
|------|----------|
| 认证 | `/api/v1/auth` |
| 系统用户 | `/api/v1/system-users` |
| 门禁用户 | `/api/v1/users` |
| 打卡记录 | `/api/v1/attendances` |
| 考勤记录 | `/api/v1/attendance-records` |
| 工作台 | `/api/v1/dashboard` |
| 门禁控制 | `/api/v1/door` |
| 设备管理 | `/api/v1/devices` |
| 飞书回调 | `/api/v1/feishu` |

更多接口示例、环境变量、部署方式和飞书接入说明见 [Wiki 首页](wiki/Home.md)。
