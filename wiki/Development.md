# Development

## 常用命令

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run mypy .
```

运行指定测试：

```bash
uv run pytest tests/test_auth.py -v
```

## 数据库迁移

创建迁移：

```bash
uv run alembic revision --autogenerate -m "describe change"
```

执行迁移：

```bash
uv run alembic upgrade head
```

回退一版：

```bash
uv run alembic downgrade -1
```

## 新增业务接口建议流程

1. 在 `schemas/` 中定义请求和响应结构。
2. 在 `models/` 中定义或更新数据库模型。
3. 在 `repositories/` 中封装查询和持久化。
4. 在 `services/` 中实现业务规则。
5. 在 `api/v1/` 中注册路由。
6. 增加或更新测试。

## 测试目录

```text
tests/
├── conftest.py
├── test_auth.py
├── test_devices.py
├── test_users.py
├── test_attendances.py
└── integrations/feishu/
```

## 响应格式

成功响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

错误响应：

```json
{
  "code": 4001,
  "message": "未授权",
  "detail": "Token 已过期，请重新登录",
  "request_id": "req_abc123"
}
```

## 错误码

| code | 说明 |
|------|------|
| `0` | 成功 |
| `1001` | 设备连接失败 |
| `1002` | 设备操作超时 |
| `2001` | 用户不存在 |
| `2002` | 用户 ID 已存在或请求数据不合法 |
| `2003` | 批量操作部分失败或重复字段 |
| `3001` | 开门指令失败 |
| `4001` | 未授权 |
| `4002` | Token 已过期 |
| `4003` | 刷新 Token 失败或权限不足 |
| `4004` | 超出 API 请求限制 |
| `5000` | 服务器内部错误 |
| `5001` | 数据库操作失败 |
| `5002` | 设备响应异常 |
