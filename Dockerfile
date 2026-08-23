# syntax=docker/dockerfile:1.7@sha256:a57df69d0ea827fb7266491f2813635de6f17269be881f696fbfdf2d83dda33e
FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv
FROM python:3.13.15-slim@sha256:ffb752e139c0a19692a43af8d8523b274222dd68eebad5d583b45c2201c6e30a AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-install-project && uv sync --frozen --no-dev

RUN useradd --create-home --uid 10001 quantforge
USER quantforge

ENV PATH="/app/.venv/bin:$PATH" \
    QF_TRADING_MODE=paper \
    QF_ALLOW_ORDER_SUBMISSION=false

EXPOSE 8000
CMD ["uvicorn", "quantforge.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
