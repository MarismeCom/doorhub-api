# Architecture

## 目录结构

```text
doorhub-api/
├── app/
│   ├── main.py                  # FastAPI 应用入口、lifespan、路由注册
│   ├── deps.py                  # 统一依赖注入
│   ├── exceptions.py            # 自定义异常与全局 handler
│   ├── api/v1/                  # 标准 API 版本入口
│   ├── core/                    # 配置、安全、运行时、后台任务、设备客户端
│   ├── db/                      # SQLAlchemy Base、engine、AsyncSession
│   ├── integrations/feishu/     # 飞书开放平台接入
│   ├── models/                  # SQLAlchemy 模型
│   ├── repositories/            # 数据访问层
│   ├── schemas/                 # Pydantic 请求与响应模型
│   └── services/                # 业务服务层
├── alembic/                     # 数据库迁移
├── tests/                       # 自动化测试
├── Dockerfile
├── pyproject.toml
└── start.py
```

## 分层约定

主链路为：

```text
api/v1 -> services -> repositories -> models -> db/session.py
```

- `api/v1` 只处理 HTTP 入参、依赖注入、响应包装和异常映射。
- `services` 承载业务规则、跨模型编排和设备操作流程。
- `repositories` 封装数据库查询与持久化。
- `models` 定义数据库结构。
- `schemas` 定义接口输入输出结构。
- `core` 放置横切能力，例如配置、安全、运行时管理、ZK 客户端和后台任务。
- `integrations` 放置第三方平台协议适配，不能绕过 `services` 直接操作业务数据。

## 应用启动流程

`app/main.py` 的 lifespan 会在启动时执行：

1. 设置应用事件循环引用。
2. 创建数据库表结构兜底。
3. 确保默认管理员存在。
4. 确保配置中的门禁设备已入库。
5. 启动考勤同步、节假日缓存和飞书长连接守护。

关闭时会停止飞书长连接、节假日缓存和考勤同步任务。

## 认证模型

- 管理后台登录用户存储在系统用户表中。
- 门禁设备用户和系统登录用户是两类数据。
- 受保护接口支持 JWT Bearer Token。
- 部分集成场景可使用 API Secret。
- 默认管理员会自动初始化，首次部署后应立即修改密码。

## 第三方集成原则

后续如接入钉钉、企业微信，可在 `app/integrations/` 下平行新增目录：

```text
app/integrations/
├── feishu/
├── dingtalk/
└── wecom/
```

集成层只处理第三方协议、签名、事件解析和事件分发。业务逻辑统一落到 `services` 层。
