FROM python:3.11-slim

# Install system deps: ffmpeg (gives ffmpeg + ffprobe) and curl (for healthcheck)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

WORKDIR /app

# Install Python dependencies (as root, before switching user)
# Copy pyproject.toml for dependency extraction only
COPY pyproject.toml ./

# Install all runtime + dev deps without editable mode
# (the app package itself is added via PYTHONPATH=/app)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
        "fastapi==0.115.5" \
        "uvicorn[standard]==0.32.1" \
        "sqlmodel==0.0.22" \
        "psycopg[binary]==3.2.3" \
        "pgvector==0.3.6" \
        "redis==5.2.0" \
        "rq==2.0.0" \
        "faster-whisper==1.1.0" \
        "sentence-transformers==3.3.1" \
        "python-multipart==0.0.18" \
        "pydantic-settings==2.6.1" \
        "pytest==8.3.4" \
        "httpx==0.28.1" \
        "pytest-asyncio==0.24.0"

# Copy application source
COPY app/ ./app/
COPY tests/ ./tests/

# Scripts are mounted at /app/scripts via docker compose volume at runtime,
# so `python scripts/<name>.py` resolves from WORKDIR /app.

# Ensure the app package is importable (no editable install needed)
ENV PYTHONPATH=/app

# Pre-create the model-cache and storage mount points owned by the non-root
# user. Docker seeds an empty named volume from the image directory, so these
# volumes initialize writable by appuser (avoids root-owned-volume EACCES when
# warming models or streaming uploads to disk).
RUN mkdir -p /model_cache /storage && \
    chown -R appuser:appgroup /model_cache /storage

# Switch to non-root user
USER appuser

# Default: run the API server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
