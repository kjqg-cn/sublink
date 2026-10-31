# =========================
# Stage 1: Build Frontends
# =========================
FROM node:18-alpine AS frontend-builder
WORKDIR /build

# Build Vue 2 (Legacy frontend)
COPY web/package*.json ./web/
RUN cd web && npm install --registry=https://registry.npmmirror.com
COPY web ./web
RUN cd web && npm run build -- --no-clean

# Build Vue 3 (Next frontend)
COPY web/next/package*.json ./web/next/
RUN cd web/next && npm install --registry=https://registry.npmmirror.com
COPY web/next ./web/next
RUN cd web/next && npm run build

# =========================
# Stage 2: Runtime Image
# =========================
FROM python:3.8.13-slim
WORKDIR /app

RUN apt-get update && apt-get install -y tzdata gcc && rm -rf /var/lib/apt/lists/*
ENV TZ=Asia/Shanghai

COPY requirements.txt .
RUN pip3 install --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY run.py .
COPY app app
COPY migrations migrations
COPY init_user_pw.py .
COPY init_login_log.py .
COPY upgrade_db.py .
COPY docker-compose.yml .

# Copy compiled frontend assets from builder stage
COPY --from=frontend-builder /build/app/static app/static
COPY --from=frontend-builder /build/app/templates app/templates

ENV PORT=5000
CMD python upgrade_db.py && gunicorn -w 4 -b 0.0.0.0:${PORT} run:app
EXPOSE ${PORT}
