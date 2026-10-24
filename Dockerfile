# Allow using a registry mirror without editing the Dockerfile.
ARG PYTHON_IMAGE=python:3.12-slim

# ------------------------------------------------------------------ builder
FROM ${PYTHON_IMAGE} AS builder

ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore

WORKDIR /build

# Build a wheel and all runtime dependency wheels. Keeping this in a separate
# stage means the runtime image needs no compiler or build cache.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip wheel --index-url "${PIP_INDEX_URL}" --wheel-dir /wheels .

# ------------------------------------------------------------------ runtime
FROM ${PYTHON_IMAGE} AS runtime

LABEL org.opencontainers.image.title="mcmod-mcp" \
      org.opencontainers.image.description="REST API, MCP server and CLI for mcmod.cn" \
      org.opencontainers.image.licenses="MIT"

# Bind to all interfaces inside the container; publish the port with docker run -p.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    MCMOD_API_HOST=0.0.0.0 \
    MCMOD_API_PORT=8000 \
    MCMOD_DATABASE_URL=sqlite:////data/mcmod.db

RUN groupadd --gid 10001 mcmod \
    && useradd --uid 10001 --gid mcmod --create-home --shell /usr/sbin/nologin mcmod \
    && mkdir -p /app /data \
    && chown mcmod:mcmod /app /data

COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels --no-cache-dir mcmod-mcp \
    && rm -rf /wheels

WORKDIR /app
USER mcmod

VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('MCMOD_API_PORT', '8000') + '/health', timeout=3)"

CMD ["mcmod-api"]
