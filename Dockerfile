# ── SJHL SP Manager - Docker 镜像 (多阶段构建) ──────────────
# 构建:  docker build -t sjhl-sp-manager .
# 运行:  docker run -d -p 1115:1115 -v sjhl-data:/app/data --name sjhl sjhl-sp-manager

# ══ 阶段 1: 构建前端 ═══════════════════════════════════════
FROM node:22-alpine AS frontend-builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --registry=https://registry.npmmirror.com

COPY frontend/ ./
RUN npx vite build --outDir /build/dist

# ══ 阶段 2: 运行后端 ═══════════════════════════════════════
FROM python:3.12-slim

LABEL org.opencontainers.image.title="SJHL SP Manager"
LABEL org.opencontainers.image.description="世纪互联 SharePoint 文件传输管理器"

ENV SJHL_HOST=0.0.0.0
ENV SJHL_PORT=1115
ENV SJHL_DATA_DIR=/app/data
ENV SJHL_FRONTEND_DIST=/app/frontend/dist
ENV SJHL_CORS_ORIGINS=*
ENV SJHL_TRANSFER_CONCURRENCY=2
ENV SJHL_ENABLE_DOCS=0
ENV TZ=Asia/Shanghai

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

COPY backend/ .
COPY --from=frontend-builder /build/dist/ frontend/dist/

RUN mkdir -p /app/data

EXPOSE 1115

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:1115/api/state')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1115", "--log-level", "info"]
