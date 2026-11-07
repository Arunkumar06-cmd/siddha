# Siddha — production image (build stage + slim runtime)
# syntax=docker/dockerfile:1

FROM python:3.11-slim AS build
ENV PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 HF_HOME=/opt/hf
WORKDIR /app
COPY requirements.txt .
# Resolve the CPU torch wheel explicitly (same as CI). With only --extra-index-url pip
# may pick the much larger default wheel and stall on a slow mirror.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --timeout 60 --retries 3 --index-url https://download.pytorch.org/whl/cpu "torch==2.12.1" \
    && /opt/venv/bin/pip install --timeout 60 --retries 5 -r requirements.txt
# Bake the embedding model into the image. HF_HOME points at a path that the runtime
# stage copies; without that copy the first user request would download ~2 GB.
RUN /opt/venv/bin/python -c "from sentence_transformers import SentenceTransformer; \
    SentenceTransformer('BAAI/bge-m3')"

FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH SIDDHA_HOST=0.0.0.0 \
    HF_HOME=/opt/hf HF_HUB_OFFLINE=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /usr/sbin/nologin siddha
COPY --from=build /opt/venv /opt/venv
# HF_HUB_OFFLINE=1: a missing cache fails immediately instead of downloading at request time.
COPY --from=build /opt/hf /opt/hf
COPY . .
USER siddha
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD curl -fsS http://localhost:7860/api/ready || exit 1
# HF Spaces convention: port 7860. The platform proxy is the only route in; trust
# its X-Forwarded-For so the per-visitor credit budget sees the real client IP.
# If the image is exposed directly, XFF is spoofable — the global budget remains
# the hard cost cap.
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "7860", \
     "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
