# Single-service image: the API also serves the built web app. Used by render.yaml.
# (backend/ and frontend/ keep their own Dockerfiles for the two-service docker-compose stack.)
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PATH=/app/.venv/bin:$PATH MATT_STATIC_DIR=/app/web
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ .
RUN uv sync --frozen --no-dev
COPY --from=web /web/dist /app/web

RUN useradd --system --uid 10001 matt && chown -R matt /app
USER matt
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && matt seed-registry && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
