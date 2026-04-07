"""
ZAP Exporter -- bridges OWASP ZAP with Prometheus metrics and Cribl Stream.

Periodically:
  1. Triggers ZAP spider against target URLs (Kong proxy endpoints)
  2. Waits for passive scan (or active scan if enabled) to complete
  3. Polls ZAP alerts API for findings
  4. Updates Prometheus metrics
  5. Forwards new alerts to Cribl Stream HTTP input

Exposes /metrics (Prometheus), /health, and /api/scan (manual trigger).
"""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import PlainTextResponse, JSONResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ZAP_API_URL = os.getenv("ZAP_API_URL", "http://zap:8090")
ZAP_SCAN_MODE = os.getenv("ZAP_SCAN_MODE", "passive")  # passive | active
ZAP_SCAN_INTERVAL_MINUTES = int(os.getenv("ZAP_SCAN_INTERVAL_MINUTES", "5"))
ZAP_TARGET_URLS = os.getenv(
    "ZAP_TARGET_URLS",
    "http://kong:8000/health,http://admin-panel:8080/health,http://admin-panel:8080/docs",
).split(",")
CRIBL_STREAM_URL = os.getenv("CRIBL_STREAM_URL", "")
CRIBL_STREAM_TOKEN = os.getenv("CRIBL_STREAM_TOKEN", "")
KONG_ADMIN_URL = os.getenv("KONG_ADMIN_URL", "http://kong:8001")

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("zap-exporter")

# ---------------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------------
registry = CollectorRegistry()

alerts_total = Counter(
    "zap_alerts_total",
    "Total ZAP alerts detected",
    ["severity", "alert_name", "owasp_category"],
    registry=registry,
)

alerts_active = Gauge(
    "zap_alerts_active",
    "Currently active ZAP alerts by severity",
    ["severity"],
    registry=registry,
)

alerts_by_confidence = Gauge(
    "zap_alerts_by_confidence",
    "Active alerts by confidence level",
    ["confidence"],
    registry=registry,
)

scan_duration_seconds = Histogram(
    "zap_scan_duration_seconds",
    "Duration of ZAP scan cycles",
    ["scan_type"],
    buckets=[10, 30, 60, 120, 300, 600, 1200],
    registry=registry,
)

scan_status = Gauge(
    "zap_scan_status",
    "Current scan status (0=idle, 1=running, 2=completed, 3=error)",
    ["scan_type"],
    registry=registry,
)

last_scan_timestamp = Gauge(
    "zap_last_scan_timestamp",
    "Unix timestamp of last completed scan",
    ["scan_type"],
    registry=registry,
)

scan_urls_total = Gauge(
    "zap_scan_urls_total",
    "Number of URLs discovered and scanned",
    registry=registry,
)

zap_up = Gauge(
    "zap_up",
    "Whether ZAP daemon is reachable (1=up, 0=down)",
    registry=registry,
)

# OWASP Top 10 mapping for alerts
OWASP_CATEGORIES = {
    "Broken Access Control": "A01",
    "Cryptographic Failures": "A02",
    "Injection": "A03",
    "Insecure Design": "A04",
    "Security Misconfiguration": "A05",
    "Vulnerable Components": "A06",
    "Auth Failures": "A07",
    "Data Integrity Failures": "A08",
    "Logging Failures": "A09",
    "SSRF": "A10",
}

# Map ZAP alert names to OWASP categories
ZAP_TO_OWASP = {
    "sql injection": "A03",
    "cross site scripting": "A03",
    "xss": "A03",
    "injection": "A03",
    "broken access": "A01",
    "access control": "A01",
    "open redirect": "A01",
    "csrf": "A01",
    "cryptographic": "A02",
    "ssl": "A02",
    "tls": "A02",
    "hsts": "A02",
    "cookie": "A05",
    "header": "A05",
    "misconfiguration": "A05",
    "csp": "A05",
    "x-frame": "A05",
    "x-content-type": "A05",
    "server leak": "A05",
    "pii": "A07",
    "authentication": "A07",
    "session": "A07",
    "ssrf": "A10",
    "proxy disclosure": "A10",
    "information disclosure": "A09",
    "debug": "A09",
}

# Track seen alert IDs to only forward new ones to Cribl
_seen_alert_ids: set[str] = set()
_http_client: httpx.AsyncClient | None = None


def classify_owasp(alert_name: str) -> str:
    """Map a ZAP alert name to an OWASP Top 10 category."""
    name_lower = alert_name.lower()
    for keyword, category in ZAP_TO_OWASP.items():
        if keyword in name_lower:
            return category
    return "unknown"


# ---------------------------------------------------------------------------
# ZAP API Client
# ---------------------------------------------------------------------------
async def client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=30.0)
    return _http_client


async def zap_get(path: str, params: dict | None = None) -> dict:
    """Call ZAP REST API."""
    c = await client()
    url = f"{ZAP_API_URL}{path}"
    resp = await c.get(url, params=params or {})
    resp.raise_for_status()
    return resp.json()


async def check_zap_health() -> bool:
    """Check if ZAP daemon is reachable."""
    try:
        data = await zap_get("/JSON/core/view/version/")
        version = data.get("version", "unknown")
        logger.debug(f"ZAP version: {version}")
        zap_up.set(1)
        return True
    except Exception as e:
        logger.warning(f"ZAP health check failed: {e}")
        zap_up.set(0)
        return False


async def discover_kong_routes() -> list[str]:
    """Discover API routes from Kong Admin API to add as scan targets."""
    urls = list(ZAP_TARGET_URLS)  # start with configured targets
    try:
        c = await client()
        resp = await c.get(f"{KONG_ADMIN_URL}/routes", timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            for route in data.get("data", []):
                paths = route.get("paths", [])
                for path in paths:
                    target = f"http://kong:8000{path}"
                    if target not in urls:
                        urls.append(target)
            logger.info(f"Discovered {len(urls)} scan targets from Kong routes")
    except Exception as e:
        logger.warning(f"Could not discover Kong routes: {e}")
    return urls


# ---------------------------------------------------------------------------
# Scan Orchestration
# ---------------------------------------------------------------------------
async def run_spider(target_url: str) -> None:
    """Run ZAP spider against a target URL."""
    logger.info(f"Spidering: {target_url}")
    try:
        data = await zap_get(
            "/JSON/spider/action/scan/",
            {"url": target_url, "maxChildren": "10", "recurse": "true"},
        )
        scan_id = data.get("scan")
        if scan_id is None:
            return

        # Wait for spider to complete (timeout 120s)
        for _ in range(60):
            status = await zap_get(
                "/JSON/spider/view/status/", {"scanId": str(scan_id)}
            )
            progress = int(status.get("status", "0"))
            if progress >= 100:
                break
            await asyncio.sleep(2)

        results = await zap_get("/JSON/spider/view/results/", {"scanId": str(scan_id)})
        url_count = len(results.get("results", []))
        scan_urls_total.set(url_count)
        logger.info(f"Spider found {url_count} URLs for {target_url}")

    except Exception as e:
        logger.error(f"Spider failed for {target_url}: {e}")


async def run_active_scan(target_url: str) -> None:
    """Run ZAP active scanner against a target URL (only in active mode)."""
    if ZAP_SCAN_MODE != "active":
        return

    logger.info(f"Active scanning: {target_url}")
    try:
        data = await zap_get(
            "/JSON/ascan/action/scan/",
            {"url": target_url, "recurse": "true", "scanPolicyName": ""},
        )
        scan_id = data.get("scan")
        if scan_id is None:
            return

        # Wait for active scan (timeout 600s)
        for _ in range(120):
            status = await zap_get(
                "/JSON/ascan/view/status/", {"scanId": str(scan_id)}
            )
            progress = int(status.get("status", "0"))
            if progress >= 100:
                break
            await asyncio.sleep(5)

        logger.info(f"Active scan completed for {target_url}")

    except Exception as e:
        logger.error(f"Active scan failed for {target_url}: {e}")


async def fetch_alerts() -> list[dict]:
    """Fetch all alerts from ZAP."""
    try:
        data = await zap_get(
            "/JSON/alert/view/alerts/", {"start": "0", "count": "500"}
        )
        return data.get("alerts", [])
    except Exception as e:
        logger.error(f"Failed to fetch alerts: {e}")
        return []


async def get_alert_summary() -> dict:
    """Get alert counts by risk level."""
    try:
        data = await zap_get("/JSON/alert/view/alertsSummary/")
        return data.get("alertsSummary", {})
    except Exception:
        return {}


async def update_metrics(alerts: list[dict]) -> None:
    """Update Prometheus metrics from ZAP alerts."""
    severity_counts = {"High": 0, "Medium": 0, "Low": 0, "Informational": 0}
    confidence_counts = {"High": 0, "Medium": 0, "Low": 0, "Confirmed": 0}

    for alert in alerts:
        risk = alert.get("risk", "Informational")
        confidence = alert.get("confidence", "Low")
        name = alert.get("alert", "unknown")
        owasp = classify_owasp(name)

        severity_counts[risk] = severity_counts.get(risk, 0) + 1
        confidence_counts[confidence] = confidence_counts.get(confidence, 0) + 1

        # Increment total counter for new alerts
        alert_id = alert.get("id", "")
        if alert_id and alert_id not in _seen_alert_ids:
            _seen_alert_ids.add(alert_id)
            alerts_total.labels(
                severity=risk, alert_name=name, owasp_category=owasp
            ).inc()

    for severity, count in severity_counts.items():
        alerts_active.labels(severity=severity).set(count)

    for confidence, count in confidence_counts.items():
        alerts_by_confidence.labels(confidence=confidence).set(count)


async def forward_to_cribl(alerts: list[dict]) -> None:
    """Send new alerts to Cribl Stream HTTP input."""
    if not CRIBL_STREAM_URL:
        return

    new_alerts = [a for a in alerts if a.get("id", "") not in _seen_alert_ids]
    if not new_alerts:
        return

    headers = {"Content-Type": "application/json"}
    if CRIBL_STREAM_TOKEN:
        headers["Authorization"] = f"Bearer {CRIBL_STREAM_TOKEN}"

    events = []
    for alert in new_alerts:
        events.append(
            {
                "source": "owasp-zap",
                "sourcetype": "zap:alert",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "severity": alert.get("risk", "Informational"),
                "confidence": alert.get("confidence", "Low"),
                "alert_name": alert.get("alert", ""),
                "alert_id": alert.get("pluginId", ""),
                "owasp_category": classify_owasp(alert.get("alert", "")),
                "url": alert.get("url", ""),
                "method": alert.get("method", ""),
                "param": alert.get("param", ""),
                "evidence": (alert.get("evidence", "") or "")[:500],
                "description": (alert.get("description", "") or "")[:1000],
                "solution": (alert.get("solution", "") or "")[:1000],
                "cwe_id": alert.get("cweid", ""),
                "wasc_id": alert.get("wascid", ""),
                "scan_mode": ZAP_SCAN_MODE,
            }
        )

    if not events:
        return

    try:
        c = await client()
        resp = await c.post(CRIBL_STREAM_URL, json=events, headers=headers, timeout=10)
        if resp.status_code < 300:
            logger.info(f"Forwarded {len(events)} alerts to Cribl Stream")
        else:
            logger.warning(f"Cribl Stream returned {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        logger.error(f"Failed to forward to Cribl: {e}")


# ---------------------------------------------------------------------------
# Main Scan Cycle
# ---------------------------------------------------------------------------
async def scan_cycle() -> None:
    """Execute one full scan cycle: spider -> (active scan) -> collect alerts."""
    if not await check_zap_health():
        scan_status.labels(scan_type=ZAP_SCAN_MODE).set(3)  # error
        return

    scan_type = ZAP_SCAN_MODE
    scan_status.labels(scan_type=scan_type).set(1)  # running
    start = time.time()

    try:
        targets = await discover_kong_routes()

        for target in targets:
            await run_spider(target)

        # Wait for passive scan to finish processing
        logger.info("Waiting for passive scan to complete...")
        for _ in range(30):
            data = await zap_get("/JSON/pscan/view/recordsToScan/")
            remaining = int(data.get("recordsToScan", "0"))
            if remaining == 0:
                break
            await asyncio.sleep(2)

        if ZAP_SCAN_MODE == "active":
            for target in targets:
                await run_active_scan(target)

        # Collect and process alerts
        alerts = await fetch_alerts()
        await forward_to_cribl(alerts)
        await update_metrics(alerts)

        duration = time.time() - start
        scan_duration_seconds.labels(scan_type=scan_type).observe(duration)
        scan_status.labels(scan_type=scan_type).set(2)  # completed
        last_scan_timestamp.labels(scan_type=scan_type).set(time.time())

        logger.info(
            f"Scan cycle complete: {len(alerts)} alerts, "
            f"{duration:.1f}s, mode={scan_type}"
        )

    except Exception as e:
        scan_status.labels(scan_type=scan_type).set(3)  # error
        logger.error(f"Scan cycle failed: {e}")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info(
        f"ZAP Exporter starting: mode={ZAP_SCAN_MODE}, "
        f"interval={ZAP_SCAN_INTERVAL_MINUTES}m, "
        f"targets={len(ZAP_TARGET_URLS)}"
    )

    # Wait for ZAP to start up
    for attempt in range(30):
        if await check_zap_health():
            break
        logger.info(f"Waiting for ZAP daemon... (attempt {attempt + 1}/30)")
        await asyncio.sleep(5)

    scheduler.add_job(
        scan_cycle,
        "interval",
        minutes=ZAP_SCAN_INTERVAL_MINUTES,
        id="scan_cycle",
        max_instances=1,
    )
    scheduler.start()

    # Run initial scan after a brief startup delay
    await asyncio.sleep(10)
    asyncio.create_task(scan_cycle())

    yield

    scheduler.shutdown()
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()


app = FastAPI(title="ZAP Exporter", lifespan=lifespan)


@app.get("/health")
async def health():
    is_healthy = await check_zap_health()
    return JSONResponse(
        status_code=200 if is_healthy else 503,
        content={"status": "healthy" if is_healthy else "zap_unreachable"},
    )


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(
        generate_latest(registry), media_type="text/plain; charset=utf-8"
    )


@app.get("/api/alerts")
async def get_alerts():
    """Return current ZAP alerts as JSON."""
    alerts = await fetch_alerts()
    summary = await get_alert_summary()
    return {
        "scan_mode": ZAP_SCAN_MODE,
        "summary": summary,
        "alert_count": len(alerts),
        "alerts": alerts[:100],  # limit response size
    }


@app.post("/api/scan")
async def trigger_scan():
    """Manually trigger a scan cycle."""
    asyncio.create_task(scan_cycle())
    return {"status": "scan_triggered", "mode": ZAP_SCAN_MODE}


@app.get("/api/status")
async def scan_status_endpoint():
    """Return current scanner status."""
    is_up = await check_zap_health()
    summary = await get_alert_summary() if is_up else {}
    return {
        "zap_reachable": is_up,
        "scan_mode": ZAP_SCAN_MODE,
        "scan_interval_minutes": ZAP_SCAN_INTERVAL_MINUTES,
        "target_count": len(ZAP_TARGET_URLS),
        "alert_summary": summary,
    }
