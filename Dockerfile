# One image: the built frontend is served by the same process that serves the
# API, so there is one service to deploy, no CORS to configure and no base URL
# that differs between a laptop and the host.

FROM node:22-slim AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependencies first, so a code change does not reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ src/
COPY api/ api/
COPY migrations/ migrations/
COPY anchors/ anchors/
COPY docs/ docs/
COPY --from=web /web/dist web/dist
RUN uv sync --frozen --no-dev

# The host picks the port and expects the app on 0.0.0.0.
ENV PORT=8000
CMD ["sh", "-c", "uv run r3m migrate && uv run uvicorn api.main:app --host 0.0.0.0 --port ${PORT}"]
