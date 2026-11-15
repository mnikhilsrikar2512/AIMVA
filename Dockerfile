# AIMVA: one image with the API and the built web app.
#   docker build -t aimva .
# Run it with deploy/docker-compose.yml (Postgres, HTTPS, backups). See docs/DEPLOY.md.

# --- 1. Build the React apps: the customer app (dist) and the AIMVA team app (dist-team) ---
FROM node:26-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
# --ignore-scripts: a hijacked package can't run code while installing (the build doesn't need install scripts)
RUN npm ci --no-audit --no-fund --ignore-scripts
COPY frontend/ ./
RUN npm run build && npm run build:team

# --- 2. The API server ---
FROM python:3.15-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN useradd --system --uid 10001 --home /app aimva
WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt
COPY backend/ .
COPY --from=web /web/dist /app/frontend/dist
COPY --from=web /web/dist-team /app/frontend/dist-team
# Files copied from a Mac folder can be owner-only (600); the app user only needs to read them.
RUN rm -rf tests .venv data .env && chmod -R a+rX,go-w /app && mkdir -p data && chown aimva:aimva data
ARG RELEASE=""
ENV RELEASE=${RELEASE} ENVIRONMENT=production LOG_FORMAT=json
USER aimva
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
# Several workers are safe: migrations take a lock, the scheduler a lease, and live updates go through Postgres.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY:-2} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 20"]
