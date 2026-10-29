FROM ghcr.io/astral-sh/uv:0.11.17 AS uv

FROM python:3.11-slim

COPY --from=uv /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    ripgrep \
    bubblewrap \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/

RUN uv sync --locked --no-dev --no-cache

RUN useradd --create-home --uid 10001 bifang \
    && mkdir /workspace \
    && chown bifang:bifang /workspace

ENV PATH="/app/.venv/bin:$PATH"

ENV BIFANG_DEFAULT_PROVIDER=nebius
ENV BIFANG_MODE=assist
ENV BIFANG_SERVER_HOST=0.0.0.0
ENV BIFANG_MAX_STEPS=12
ENV BIFANG_TIMEOUT=180
ENV HOME=/home/bifang

USER bifang
WORKDIR /workspace

EXPOSE 8000

CMD ["bifang-server"]
