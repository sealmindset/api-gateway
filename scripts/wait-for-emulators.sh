#!/usr/bin/env bash
# =============================================================================
# wait-for-emulators.sh — Block until Azure emulators are ready
# =============================================================================
# Checks that Azurite and Lowkey Vault are accepting connections before the
# caller proceeds. Useful as a pre-start gate or in CI.
#
# Usage:
#   ./scripts/wait-for-emulators.sh              # check both
#   ./scripts/wait-for-emulators.sh azurite      # check Azurite only
#   ./scripts/wait-for-emulators.sh keyvault     # check Lowkey Vault only
#
# Environment variables (override defaults):
#   AZURITE_BLOB_HOST    default: localhost
#   AZURITE_BLOB_PORT    default: 10000
#   KEYVAULT_HOST        default: localhost
#   KEYVAULT_PORT        default: 8443
#   WAIT_TIMEOUT         default: 180 (seconds)
#   WAIT_INTERVAL        default: 5   (seconds between retries)
# =============================================================================

set -euo pipefail

AZURITE_HOST="${AZURITE_BLOB_HOST:-localhost}"
AZURITE_PORT="${AZURITE_BLOB_PORT:-10000}"
KEYVAULT_HOST="${KEYVAULT_HOST:-localhost}"
KEYVAULT_PORT="${KEYVAULT_PORT:-8443}"
TIMEOUT="${WAIT_TIMEOUT:-180}"
INTERVAL="${WAIT_INTERVAL:-5}"

MODE="${1:-all}"  # all | azurite | keyvault

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

wait_for() {
  local name="$1" check_cmd="$2"
  echo "Waiting for ${name} ..."
  local start=$SECONDS
  while true; do
    if eval "$check_cmd" > /dev/null 2>&1; then
      echo "  ✓ ${name} is ready ($(( SECONDS - start ))s)"
      return 0
    fi
    if (( SECONDS - start >= TIMEOUT )); then
      echo "  ✗ ${name} did not become ready within ${TIMEOUT}s"
      return 1
    fi
    sleep "$INTERVAL"
  done
}

# ---------------------------------------------------------------------------
# Azurite check -- Blob service responds to an account list request
# ---------------------------------------------------------------------------

check_azurite() {
  # Azurite returns 403 for unsigned requests, but any HTTP response means it's up
  wait_for "Azurite (Blob :${AZURITE_PORT})" \
    "curl -s --max-time 3 -o /dev/null -w '%{http_code}' http://${AZURITE_HOST}:${AZURITE_PORT}/devstoreaccount1?comp=list | grep -q '[0-9]'"
}

# ---------------------------------------------------------------------------
# Lowkey Vault check -- ping endpoint (HTTPS, skip cert verification)
# ---------------------------------------------------------------------------

check_keyvault() {
  wait_for "Lowkey Vault (:${KEYVAULT_PORT})" \
    "curl -sfk --max-time 3 https://${KEYVAULT_HOST}:${KEYVAULT_PORT}/ping"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

FAILURES=0

case "$MODE" in
  azurite)
    check_azurite || FAILURES=$((FAILURES + 1))
    ;;
  keyvault)
    check_keyvault || FAILURES=$((FAILURES + 1))
    ;;
  all|"")
    check_azurite  || FAILURES=$((FAILURES + 1))
    check_keyvault || FAILURES=$((FAILURES + 1))
    ;;
  *)
    echo "Usage: $0 [all|azurite|keyvault]"
    exit 2
    ;;
esac

if (( FAILURES > 0 )); then
  echo ""
  echo "FAIL: ${FAILURES} emulator(s) not ready."
  exit 1
fi

echo ""
echo "All emulators ready."
exit 0
