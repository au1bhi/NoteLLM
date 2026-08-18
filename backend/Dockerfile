# Base image overridable for regions where Docker Hub is unreachable (e.g.
# mainland China): compose passes PY_BASE=<mirror>/library/python:3.14-slim.
ARG PY_BASE=python:3.14-slim
FROM ${PY_BASE}

ENV PYTHONUNBUFFERED=1

# Install uv via pip (instead of copying from ghcr.io/astral-sh/uv, which is
# unreachable from some regions). PIP_INDEX_URL (optional build arg) points pip
# at a mirror, e.g. https://pypi.tuna.tsinghua.edu.cn/simple.
# Uses COPY + no BuildKit-only --mount so the image builds with the classic
# builder on any Docker.
ARG PIP_INDEX_URL
RUN pip install --no-cache-dir uv==0.9.26 ${PIP_INDEX_URL:+--index-url "$PIP_INDEX_URL"}

# Compile bytecode
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

# uv Cache
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#caching
ENV UV_LINK_MODE=copy

# Mirrors can be slow for large wheels (e.g. psycopg-binary); the 30s default
# times out on restricted networks.
ENV UV_HTTP_TIMEOUT=300

WORKDIR /app/

# Place executables in the environment at the front of the path
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#using-the-environment
ENV PATH="/app/.venv/bin:$PATH"

# Lockfile + workspace manifest first, so the dependency layer only rebuilds
# when they change (mirrors the old bind-mount cache pattern without BuildKit).
COPY uv.lock pyproject.toml /app/

# When a pip mirror is configured, rewrite the lockfile's files.pythonhosted.org
# URLs to the mirror's /packages/ path (Chinese mirrors mirror the canonical
# package layout). `uv sync --frozen` downloads from the URLs pinned in the
# lock, ignoring --default-index; without this rewrite, a mainland-China server
# hits pythonhosted's Fastly CDN directly, which is extremely slow for wheels.
RUN if [ -n "${PIP_INDEX_URL}" ]; then \
      base="$(printf '%s' "${PIP_INDEX_URL}" | sed -E 's#/simple/*$##')"; \
      sed -i "s#https://files.pythonhosted.org/packages#${base}/packages#g" uv.lock; \
    fi

# Install dependencies
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers
# The same PIP_INDEX_URL mirrors uv's package index when provided.
RUN sh -c 'uv sync --frozen --no-install-workspace --package app ${PIP_INDEX_URL:+--default-index "$PIP_INDEX_URL"}'

COPY ./backend/scripts /app/backend/scripts

COPY ./backend/pyproject.toml ./backend/alembic.ini /app/backend/

COPY ./backend/app /app/backend/app

# Sync the project
# Ref: https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers
RUN sh -c 'uv sync --frozen --package app ${PIP_INDEX_URL:+--default-index "$PIP_INDEX_URL"}'

WORKDIR /app/backend/

# Preserve the raw TCP peer. The app validates trusted proxy networks and
# resolves sanitized XFF itself before assigning rate-limit buckets.
CMD ["bash", "-c", "exec fastapi run --workers 4 --no-proxy-headers"]
