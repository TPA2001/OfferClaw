# OfferCabin 网页服务镜像（多用户账号版，无 Playwright 依赖）
# 使用 1ms.run 镜像加速（大陆网络直连 Docker Hub 不通；备选 docker.m.daocloud.io）
FROM docker.1ms.run/library/python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple \
    OFFERCABIN_STATIC_DIR=/app/frontend/web \
    OFFERCABIN_ADMIN_STATIC_DIR=/app/frontend/admin

WORKDIR /app

# 先装依赖（利用层缓存）
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 后端代码 + 前端静态资源（主站 + 管理后台）
COPY backend/app ./app
COPY backend/run.py ./run.py
COPY backend/scripts ./scripts
COPY frontend/web ./frontend/web
COPY frontend/admin ./frontend/admin

# 运行数据目录（SQLite 默认落这里，可挂载卷）
RUN mkdir -p /app/data

# 非 root 运行
RUN useradd -m -u 1001 offercabin && chown -R offercabin:offercabin /app
USER offercabin

# 主应用 8000（公开）+ 管理后台 8001（容器内 0.0.0.0，宿主映射收窄到 127.0.0.1）
EXPOSE 8000 8001

# 双 app 双端口启动（run.py 内 asyncio.gather 拉起主应用与管理后台）
CMD ["python", "run.py"]
