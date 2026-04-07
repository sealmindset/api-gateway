#!/usr/bin/env bash
# =============================================================================
# validate-secrets.sh — Reject default credentials in non-dev environments
# =============================================================================
# Run this at startup (e.g., in entrypoint or CI) to ensure no default
# passwords survive into staging or production.
#
# Usage:
#   ENVIRONMENT=staging ./scripts/validate-secrets.sh
#
# In development (ENVIRONMENT=development or unset), this script only warns.
# In any other environment, default values cause a fatal exit.
# =============================================================================

set -euo pipefail

# Known default/placeholder values that must be overridden
DEFAULTS=(
  "postgres_local_dev"
  "kong_local_dev"
  "admin_local_dev"
  "redis_local_dev"
  "local-dev-secret-key-change-in-production"
  "mock-client-secret"
  "change_me_postgres"
  "change_me_kong"
  "change_me_admin"
  "change_me_redis"
  "change_me_secret_key"
)

# Variables to check (env var name -> description)
declare -A SECRETS=(
  [POSTGRES_PASSWORD]="PostgreSQL superuser password"
  [KONG_PG_PASSWORD]="Kong database password"
  [ADMIN_DB_PASSWORD]="Admin panel database password"
  [REDIS_PASSWORD]="Redis password"
  [SECRET_KEY]="Application secret key"
  [ENTRA_CLIENT_SECRET]="OIDC client secret"
  [GRAFANA_ADMIN_PASSWORD]="Grafana admin password"
)

ENV="${ENVIRONMENT:-development}"
FATAL=false
WARNINGS=0
ERRORS=0

is_default() {
  local value="$1"
  for default in "${DEFAULTS[@]}"; do
    if [ "$value" = "$default" ]; then
      return 0
    fi
  done
  # Also flag "admin" as default for Grafana password
  if [ "$value" = "admin" ]; then
    return 0
  fi
  return 1
}

echo "=== Secret Validation (environment: ${ENV}) ==="

for var in "${!SECRETS[@]}"; do
  desc="${SECRETS[$var]}"
  value="${!var:-}"

  if [ -z "$value" ]; then
    if [ "$ENV" = "development" ]; then
      echo "  WARN: ${var} is not set (${desc})"
      WARNINGS=$((WARNINGS + 1))
    else
      echo "  FAIL: ${var} is not set (${desc})"
      ERRORS=$((ERRORS + 1))
      FATAL=true
    fi
  elif is_default "$value"; then
    if [ "$ENV" = "development" ]; then
      echo "  WARN: ${var} is using a default value (${desc})"
      WARNINGS=$((WARNINGS + 1))
    else
      echo "  FAIL: ${var} is using a default value — must be overridden (${desc})"
      ERRORS=$((ERRORS + 1))
      FATAL=true
    fi
  else
    echo "  OK:   ${var} (${desc})"
  fi
done

echo ""
echo "Results: ${ERRORS} error(s), ${WARNINGS} warning(s)"

if [ "$FATAL" = true ]; then
  echo ""
  echo "FATAL: Default credentials detected in '${ENV}' environment."
  echo "       Override all secrets in .env before deploying to ${ENV}."
  exit 1
fi

echo "Secret validation passed."
exit 0
