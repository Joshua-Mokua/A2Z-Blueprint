# A2Z MIS 360 — Production Dockerfile
# Multi-stage build for Streamlit + FastAPI hybrid deployment
# Per Joshua doctrine Phase 3: Containerization Ready

FROM python:3.11-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Application
COPY . .

# Health probe
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

EXPOSE 8501 8000

# Default to Streamlit; override with `docker run ... uvicorn utils.api:app`
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0"]
