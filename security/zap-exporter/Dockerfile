# ---------------------------------------------------------------------------
# ZAP Exporter - Polls ZAP API, exports Prometheus metrics, sends to Cribl
# ---------------------------------------------------------------------------
FROM python:3.12-alpine

WORKDIR /app

RUN addgroup --system --gid 1001 appgroup && \
    adduser --system --uid 1001 --ingroup appgroup appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY exporter.py .

USER appuser

EXPOSE 9290

CMD ["uvicorn", "exporter:app", "--host", "0.0.0.0", "--port", "9290"]
