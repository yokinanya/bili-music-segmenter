FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git nodejs npm \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /inaseg
COPY pyproject.toml uv.lock ./
ARG DEPENDENCY_GROUP=local
RUN uv sync --frozen --group ${DEPENDENCY_GROUP}
ENV PATH="/inaseg/.venv/bin:$PATH"
COPY . .
# Build the WebUI bundle at image build time so the container never needs Node at runtime.
RUN cd webui && npm ci --no-audit --no-fund && npm run release && rm -rf node_modules .next out
