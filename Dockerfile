FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY openapi.json /build/openapi.json
COPY frontend/ ./
RUN pnpm run build

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 AS runtime
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TMPDIR=/runtime/tmp
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3.10 python3-pip python3.10-dev build-essential ffmpeg libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY requirements-app.lock research_engine/requirements.txt research_engine/requirements-gpu.txt /tmp/requirements/
RUN python3.10 -m pip install --upgrade pip setuptools wheel \
    && python3.10 -m pip install --index-url https://download.pytorch.org/whl/cu124 torch==2.5.1 torchvision==0.20.1 \
    && python3.10 -m pip install -r /tmp/requirements/requirements-gpu.txt \
    && python3.10 -m pip uninstall -y opencv-python opencv-contrib-python opencv-contrib-python-headless opencv-python-headless \
    && python3.10 -m pip install --require-hashes -r /tmp/requirements/requirements-app.lock
COPY app/ ./app/
COPY research_engine/ ./research_engine/
COPY migrations/ ./migrations/
COPY alembic.ini ./alembic.ini
COPY --from=frontend-build /build/app/frontend ./app/frontend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=360s --retries=3 CMD curl --fail http://127.0.0.1:8000/readyz || exit 1
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1"]
