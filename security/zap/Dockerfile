# ---------------------------------------------------------------------------
# OWASP ZAP - Security Scanner (Daemon Mode)
# ---------------------------------------------------------------------------
# Runs ZAP in daemon mode with the API exposed for programmatic scanning.
# Passive mode (default): spider + passive scan rules only.
# Active mode: enables active scanner for attack-pattern testing.
# ---------------------------------------------------------------------------
FROM ghcr.io/zaproxy/zaproxy:stable

USER root

# Create writable directories for ZAP data
RUN mkdir -p /zap/wrk /zap/reports /home/zap/.ZAP/policies && \
    chown -R zap:zap /zap/wrk /zap/reports /home/zap/.ZAP

COPY zap-baseline.conf /zap/wrk/zap-baseline.conf

USER zap

EXPOSE 8090

# Start ZAP in daemon mode:
#   -daemon          : headless mode (no GUI)
#   -host 0.0.0.0    : bind to all interfaces
#   -port 8090       : proxy listener port
#   -config api.addrs.addr.name=.* : allow API access from any IP
#   -config api.addrs.addr.regex=true
#   -config api.disablekey=true : disable API key (internal network only)
CMD ["zap.sh", "-daemon", \
     "-host", "0.0.0.0", \
     "-port", "8090", \
     "-config", "api.addrs.addr.name=.*", \
     "-config", "api.addrs.addr.regex=true", \
     "-config", "api.disablekey=true", \
     "-config", "connection.timeoutInSecs=120", \
     "-config", "spider.maxDuration=5", \
     "-config", "spider.threadCount=3"]
