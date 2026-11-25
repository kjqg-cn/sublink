# =========================
# Stage 1: Build Frontend
# =========================
FROM node:20-alpine AS frontend-builder
WORKDIR /build

# Install dependencies deterministically for optimal layer caching
COPY web/package.json web/package-lock.json ./web/
RUN cd /build/web && npm ci --registry=https://registry.npmmirror.com

# Copy frontend source and build static bundle to /build/app/static/dist
COPY web ./web
RUN cd /build/web && npm run build

# =========================
# Stage 2: Runtime Image
# =========================
FROM python:3.10-slim
WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends tzdata gosu && \
    rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Shanghai

COPY requirements.txt .
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY run.py .
COPY app app
COPY migrations migrations
COPY init_user_pw.py .
COPY init_login_log.py .
COPY upgrade_db.py .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Copy compiled frontend assets from builder stage
COPY --from=frontend-builder /build/app/static/dist app/static/dist

# Create non-root runtime user (UID/GID 1000) and normalize entrypoint line endings.
# Entrypoint adjusts /app/app/db ownership on bind-mounts when started as root, then drops to sublink via gosu.
RUN groupadd -r -g 1000 sublink && \
    useradd -r -u 1000 -g sublink -d /app -s /usr/sbin/nologin sublink && \
    sed -i 's/\r$//' /usr/local/bin/docker-entrypoint.sh && \
    chmod +x /usr/local/bin/docker-entrypoint.sh && \
    mkdir -p /app/app/db && \
    chown -R sublink:sublink /app

ENV PORT=5000
ENV WORKERS=4
ENV GUNICORN_TIMEOUT=120
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; opener = urllib.request.build_opener(urllib.request.ProxyHandler({})); opener.open(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"5000\")}/healthz', timeout=3)" || exit 1
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["sh", "-c", "python upgrade_db.py && exec gunicorn -w ${WORKERS:-4} --timeout ${GUNICORN_TIMEOUT:-120} -b 0.0.0.0:${PORT:-5000} run:app"]
