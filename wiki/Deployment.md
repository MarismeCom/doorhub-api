# Deployment

## Docker 构建

在 `doorhub-api` 目录执行：

```bash
docker build -t doorhub-api:latest .
```

## Docker 运行

```bash
docker run -d \
  --name doorhub-api \
  -p 8000:8000 \
  --env-file .env \
  doorhub-api:latest
```

容器默认执行：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

## 数据库迁移

容器部署前或发布流程中需要执行：

```bash
uv run alembic upgrade head
```

如果在容器内执行，请确保容器能够访问 PostgreSQL，且 `.env` 中的 `DATABASE_URL` 指向正确地址。

## Nginx 反向代理示例

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

## 发布检查

- `.env` 已配置生产数据库。
- `SECRET_KEY` 已替换为随机强密钥。
- 默认管理员密码已修改。
- Alembic 迁移已执行到最新版本。
- 服务可访问 `/health`。
- 如果启用飞书长连接，确认企业应用凭据和事件订阅已配置。
