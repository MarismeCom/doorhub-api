# API Reference

## 认证

### 登录

```bash
curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin"}'
```

响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "access_token": "...",
    "refresh_token": "...",
    "token_type": "bearer",
    "expires_in": 3600,
    "role": "admin"
  }
}
```

### 刷新 Token

```bash
curl -X POST "http://localhost:8000/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "<refresh_token>"}'
```

### 当前用户

```bash
curl -X GET "http://localhost:8000/api/v1/system-users/me" \
  -H "Authorization: Bearer <access_token>"
```

## API Secret

API Secret 归属某个系统用户。明文 Secret 只在创建成功时返回一次。

支持两种传递方式：

```bash
-H "X-API-Secret: sk_xxx"
```

```bash
-H "Authorization: Bearer sk_xxx"
```

创建 API Secret：

```bash
curl -X POST "http://localhost:8000/api/v1/system-users/operator01/api-secrets" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "name": "doorhub-integration",
    "expires_at": "2026-12-31T23:59:59+08:00"
  }'
```

## 系统用户

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/api/v1/system-users/me` | 获取当前系统用户 | 是 |
| `GET` | `/api/v1/system-users` | 获取系统用户列表 | 管理员 |
| `POST` | `/api/v1/system-users` | 创建系统用户 | 管理员 |
| `GET` | `/api/v1/system-users/{username}` | 获取系统用户详情 | 管理员 |
| `PATCH` | `/api/v1/system-users/{username}` | 更新角色或状态 | 管理员 |
| `POST` | `/api/v1/system-users/{username}/reset-password` | 重置密码 | 管理员 |
| `POST` | `/api/v1/system-users/me/change-password` | 修改自己的密码 | 是 |
| `GET` | `/api/v1/system-users/{username}/api-secrets` | 获取 API Secret 列表 | 管理员 |
| `POST` | `/api/v1/system-users/{username}/api-secrets` | 创建 API Secret | 管理员 |
| `DELETE` | `/api/v1/system-users/{username}/api-secrets/{secret_id}` | 撤销 API Secret | 管理员 |

## 门禁用户

门禁用户是 ZKTeco 设备里的人员数据，不是后台登录用户。

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/api/v1/users` | 获取门禁用户列表 | 否 |
| `GET` | `/api/v1/users/next-user-id` | 获取建议用户 ID | 是 |
| `POST` | `/api/v1/users` | 创建本地用户，状态为待同步 | 是 |
| `PUT` | `/api/v1/users/{user_id}` | 更新本地用户，状态为待同步 | 是 |
| `DELETE` | `/api/v1/users/{user_id}` | 设置用户离职，状态为待同步 | 是 |
| `POST` | `/api/v1/users/{user_id}/sync` | 同步单个用户到设备 | 是 |
| `POST` | `/api/v1/users/sync/batch` | 批量同步待同步用户 | 是 |
| `POST` | `/api/v1/users/sync/from-device` | 从设备预览、写入或覆盖本地用户 | 是 |
| `GET` | `/api/v1/users/sync/status` | 获取同步状态 | 否 |

从设备同步支持三种模式：

| mode | 说明 |
|------|------|
| `preview` | 只预览差异，不修改本地数据库 |
| `write_missing` | 只把本地缺失的设备用户写入本地 |
| `overwrite_local` | 用设备数据覆盖本地差异用户，并写入本地缺失用户 |

同步状态：

| status | 说明 |
|--------|------|
| `pending` | 待同步 |
| `synced` | 已同步到设备 |
| `pending_delete` | 待同步删除或离职 |
| `synced_deleted` | 已从设备删除或禁用 |
| `failed` | 同步失败 |

## 打卡与考勤

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/api/v1/attendances` | 获取原始打卡记录 | 否 |
| `POST` | `/api/v1/attendances/sync` | 手动同步打卡记录 | 否 |
| `GET` | `/api/v1/attendances/sync/status` | 获取打卡同步状态 | 否 |
| `GET` | `/api/v1/attendances/sync/settings` | 获取打卡同步配置 | 否 |
| `PUT` | `/api/v1/attendances/sync/settings` | 更新打卡同步配置 | 否 |
| `GET` | `/api/v1/attendance-records` | 获取考勤日报记录 | 否 |
| `POST` | `/api/v1/attendance-records/recalculate` | 重算考勤日报 | 否 |
| `GET` | `/api/v1/attendance-records/export/monthly` | 导出月度考勤 CSV | 否 |
| `GET` | `/api/v1/attendance-records/holiday-cache/status` | 获取节假日缓存状态 | 否 |
| `GET` | `/api/v1/attendance-records/holiday-cache/settings` | 获取节假日缓存配置 | 否 |
| `PUT` | `/api/v1/attendance-records/holiday-cache/settings` | 更新节假日缓存配置 | 否 |
| `POST` | `/api/v1/attendance-records/holiday-cache/refresh` | 手动刷新节假日缓存 | 否 |
| `GET` | `/api/v1/attendance-records/holiday-cache/calendar` | 获取月度节假日缓存 | 否 |

同步打卡记录：

```bash
curl -X POST "http://localhost:8000/api/v1/attendances/sync" \
  -H "Content-Type: application/json" \
  -d '{"device_ip": "192.168.1.201", "incremental": true}'
```

## 门禁控制

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `POST` | `/api/v1/door/open` | 远程开门 | 是 |
| `POST` | `/api/v1/door/close` | 返回设备不支持主动关门说明 | 是 |
| `GET` | `/api/v1/door/logs` | 获取开门记录 | 否 |

`/api/v1/door/unlock` 仍保留为兼容别名，但不出现在 OpenAPI schema 中。

远程开门：

```bash
curl -X POST "http://localhost:8000/api/v1/door/open" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -d '{
    "device_ip": "192.168.1.201",
    "unlock_seconds": 3,
    "remark": "访客放行"
  }'
```

## 设备管理

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/api/v1/devices` | 获取设备列表 | 否 |
| `POST` | `/api/v1/devices` | 创建设备 | 否 |
| `PUT` | `/api/v1/devices/{device_id}` | 更新设备 | 否 |
| `DELETE` | `/api/v1/devices/{device_id}` | 删除设备 | 否 |
| `GET` | `/api/v1/devices/{ip}/status` | 获取设备状态 | 否 |

## 工作台

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| `GET` | `/api/v1/dashboard/summary` | 获取工作台统计摘要 | 是 |

## 健康检查

```bash
curl -X GET "http://localhost:8000/health"
```

响应：

```json
{
  "status": "healthy",
  "uptime_seconds": 3600,
  "timestamp": "2026-04-30T10:30:00"
}
```
