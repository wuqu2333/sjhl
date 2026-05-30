# ── SJHL SP Manager - Docker 镜像 ──────────────────────────
# 构建:  docker build -t sjhl-sp-manager .
# 运行:  docker run -d -p 1115:1115 -v sjhl-data:/app/data --name sjhl sjhl-sp-manager

FROM python:3.12-slim

LABEL org.opencontainers.image.title="SJHL SP Manager"
LABEL org.opencontainers.image.description="世纪互联 SharePoint 文件传输管理器 - Worker 模式主控端"

ENV SJHL_HOST=0.0.0.0
ENV SJHL_PORT=1115
ENV SJHL_DATA_DIR=/app/data
ENV SJHL_CORS_ORIGINS=*
ENV SJHL_TRANSFER_CONCURRENCY=2
ENV SJHL_ENABLE_DOCS=0
ENV TZ=Asia/Shanghai

WORKDIR /app

# 安装依赖
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ .

# 复制前端构建产物 (需先 build frontend)
COPY frontend/dist/ frontend/dist/

# 数据持久化目录
RUN mkdir -p /app/data

EXPOSE 1115

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:1115/api/state')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "1115", "--log-level", "info"]
