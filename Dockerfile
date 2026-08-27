# OfferClaw 网页服务镜像（多用户账号版，无 Playwright 依赖）
# 使用 1ms.run 镜像加速（大陆网络直连 Docker Hub 不通；备选 docker.m.daocloud.io）
FROM docker.1ms.run/library/python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    OFFERCLAW_STATIC_DIR=/app/frontend/web

WORKDIR /app

# 先装依赖（利用层缓存）
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码 + 前端静态资源
COPY backend/app ./app
COPY frontend/web ./frontend/web

# 运行数据目录（SQLite 默认落这里，可挂载卷）
RUN mkdir -p /app/data

# 非 root 运行
RUN useradd -m -u 1001 offerclaw && chown -R offerclaw:offerclaw /app
USER offerclaw

EXPOSE 8000

# 生产用 uvicorn 直接启动（无 Playwright，无 Windows 事件循环问题）
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
