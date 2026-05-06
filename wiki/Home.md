# DoorHub API Wiki

DoorHub API 是门禁管理系统的后端服务，提供系统认证、门禁用户管理、设备管理、打卡记录、考勤统计、远程开门、飞书事件接入和后台同步任务。

## 导航

- [Getting Started](Getting-Started.md)
- [Architecture](Architecture.md)
- [Configuration](Configuration.md)
- [API Reference](API-Reference.md)
- [Feishu Integration](Feishu-Integration.md)
- [Deployment](Deployment.md)
- [Development](Development.md)
- [Roadmap](Roadmap.md)

## 核心能力

| 能力 | 说明 |
|------|------|
| 系统认证 | JWT Bearer Token、刷新令牌、API Secret |
| 系统用户 | 管理后台登录用户和权限角色 |
| 门禁用户 | 管理 ZKTeco 设备用户，支持本地到设备、设备到本地同步 |
| 设备管理 | 管理设备配置、状态检测和初始化 |
| 打卡与考勤 | 同步打卡记录，生成考勤日报，支持工作日配置 |
| 门禁控制 | 远程开门和开门日志 |
| 飞书接入 | 飞书长连接事件消费、机器人菜单事件、HTTP 回调入口 |

## 技术栈

| 组件 | 版本 / 说明 |
|------|-------------|
| Python | 3.13+ |
| FastAPI | API 服务与 OpenAPI 文档 |
| PostgreSQL | 16+ |
| SQLAlchemy | 2.x async ORM |
| Alembic | 数据库迁移 |
| pyzk | 0.9，ZKTeco 设备通信 |
| lark-oapi | 飞书开放平台 Python SDK |
| uv | Python 环境与依赖管理 |

## 常用地址

| 地址 | 说明 |
|------|------|
| `http://localhost:8000/docs` | Swagger UI |
| `http://localhost:8000/redoc` | ReDoc |
| `http://localhost:8000/health` | 健康检查 |

## GitHub Wiki 使用方式

GitHub Wiki 本质是一个单独的 Git 仓库。可以把本目录中的 Markdown 文件同步到 wiki 仓库：

```bash
git clone git@github.com:<owner>/<repo>.wiki.git
cp wiki/*.md <repo>.wiki/
cd <repo>.wiki
git add .
git commit -m "docs: initialize backend wiki"
git push
```

如果当前仓库托管平台没有启用 Wiki，也可以直接保留 `wiki/` 目录作为项目内文档源。
