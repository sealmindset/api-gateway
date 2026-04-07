FROM python:3.12-alpine AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create non-root user
RUN addgroup -g 1000 appuser && \
    adduser -u 1000 -G appuser -s /bin/sh -D appuser

# Install curl for healthchecks and build deps for compiled Python packages
RUN apk add --no-cache curl build-base libffi-dev

WORKDIR /app

# Install dependencies in a separate layer for caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Ensure static dir exists (mount or bake in at build time)
RUN mkdir -p app/static

# ---------------------------------------------------------------------------
# Development stage - hot reload with uvicorn
# ---------------------------------------------------------------------------
FROM base AS development

USER appuser
EXPOSE 8080

CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--reload", \
     "--reload-dir", "app", \
     "--no-server-header"]

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD ["curl", "-f", "http://localhost:8080/health"]

# ---------------------------------------------------------------------------
# Production stage - gunicorn with uvicorn workers
# ---------------------------------------------------------------------------
FROM base AS production

USER appuser
EXPOSE 8080

CMD ["gunicorn", "app.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["curl", "-f", "http://localhost:8080/health"]
