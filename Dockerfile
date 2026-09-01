# AI Living City — single-container production image (API + WebSocket + 3D UI)

FROM node:22-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci --omit=dev 2>/dev/null || npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    PORT=8000 \
    MAP_SIZE=80 \
    DEFAULT_SPEED=1 \
    DATABASE_URL=sqlite:////data/city.db

RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist

RUN mkdir -p /data

WORKDIR /app/backend
EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips="*"
