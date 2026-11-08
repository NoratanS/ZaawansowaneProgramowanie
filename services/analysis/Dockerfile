# syntax=docker/dockerfile:1
# Build with the repo root as context:
#   docker build -f services/analysis/Dockerfile .
FROM ghcr.io/astral-sh/uv:python3.15-trixie-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

# Keep in step with BAKED_MODEL_PATH in analysis_service/settings.py.
ARG MODEL_PATH=/opt/models/object_detection_yolox_2022nov.onnx

# YOLOX-S from the OpenCV Model Zoo (Apache-2.0), pinned by hash, so every
# replica starts with the same model and needs no network.
ADD --checksum=sha256:c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063 \
    https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx \
    ${MODEL_PATH}

WORKDIR /app

# Dependencies first, so code changes don't reinstall them. uv needs every
# workspace member's pyproject.toml to read the lockfile.
COPY pyproject.toml uv.lock ./
COPY services/analysis/pyproject.toml services/analysis/
COPY services/results/pyproject.toml services/results/
RUN uv sync --frozen --no-install-workspace --package analysis-service

COPY services/analysis services/analysis
RUN uv sync --frozen --package analysis-service

ENV PATH="/app/.venv/bin:$PATH" \
    MODEL_PATH=${MODEL_PATH}

CMD ["python", "-m", "analysis_service.worker"]
