# Getting Started

## 环境要求

- Python 3.13+
- PostgreSQL 16+
- uv
- 可访问的 ZKTeco 门禁设备

严禁直接使用系统 Python 环境，建议始终使用 uv 创建的虚拟环境。

## 创建虚拟环境

```bash
uv venv .venv
source .venv/bin/activate
```

## 安装依赖

```bash
uv sync --extra dev
```

## 配置环境变量

```bash
cp .env.example .env
```

至少需要确认：

```env
DATABASE_URL=postgresql://admin:password@localhost:5432/doorhub
SECRET_KEY=replace-with-a-random-secret
ZK_DEVICE_IPS=192.168.1.201
```

生成随机 `SECRET_KEY`：

```bash
uv run python -c "import secrets; print(secrets.token_hex(32))"
```

## 执行数据库迁移

```bash
uv run alembic upgrade head
```

## 启动服务

开发模式：

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

项目脚本：

```bash
uv run start
```

## 访问文档

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health Check: http://localhost:8000/health

## 默认管理员

| 用户名 | 密码 | 角色 |
|--------|------|------|
| `admin` | `admin` | `admin` |

应用启动时会自动确保默认管理员存在。首次部署后请立即修改默认密码。

## 登录示例

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

响应中的 `access_token` 可用于访问受保护接口：

```bash
curl -X GET "http://localhost:8000/api/v1/system-users/me" \
  -H "Authorization: Bearer <access_token>"
```
