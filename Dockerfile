FROM node:24-alpine AS webui-build
WORKDIR /app/webui
COPY webui/package.json webui/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY webui/ ./
RUN npm run build

FROM python:3.12-slim AS python-base

FROM python-base AS python-deps
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM python-base AS runtime
# NetEase fingerprinting uses Node; the frontend only needs its static export.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH"
COPY --from=python-deps /app/.venv ./.venv
COPY segment/ ./segment/
COPY vendor/ncm-afp/ ./vendor/ncm-afp/
COPY --from=webui-build /app/webui/out ./segment/webui_dist/

CMD ["python", "-m", "segment.webui", "--host", "0.0.0.0"]
