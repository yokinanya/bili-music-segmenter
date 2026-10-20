FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg git nodejs \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /inaseg
COPY pyproject.toml uv.lock ./
ARG DEPENDENCY_GROUP=local
RUN uv sync --frozen --group ${DEPENDENCY_GROUP}
ENV PATH="/inaseg/.venv/bin:$PATH"
COPY . .
