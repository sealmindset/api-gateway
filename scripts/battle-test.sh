#!/usr/bin/env bash
# --------------------------------------------------------------------------
# Battle Test Runner
# --------------------------------------------------------------------------
# Orchestrates all five battle-test suites against the live Docker stack
# and produces a JSON summary + optional attestation.
#
# Usage:
#   ./scripts/battle-test.sh              # run all suites
#   ./scripts/battle-test.sh --suite 13   # run only test_13_load
#   ./scripts/battle-test.sh --skip 15    # skip test_15_chaos
#   ./scripts/battle-test.sh --attest     # auto-generate attestation doc
# --------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEST_DIR="$REPO_ROOT/tests"
RESULTS_DIR="$REPO_ROOT/docs/attestations"
TIMESTAMP=$(date +%Y-%m-%d_%H%M%S)
DATE_ONLY=$(date +%Y-%m-%d)
JSON_REPORT="$RESULTS_DIR/battle-test-results-${TIMESTAMP}.json"

mkdir -p "$RESULTS_DIR"

# ---------- arg parsing ---------------------------------------------------
SUITES=(13 14 15 16 17)
SKIP=()
GENERATE_ATTEST=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --suite)  SUITES=("$2"); shift 2 ;;
    --skip)   SKIP+=("$2");  shift 2 ;;
    --attest) GENERATE_ATTEST=true; shift ;;
    -h|--help)
      echo "Usage: $0 [--suite N] [--skip N] [--attest]"
      exit 0 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

# Remove skipped suites
for s in "${SKIP[@]+"${SKIP[@]}"}"; do
  SUITES=("${SUITES[@]/$s/}")
done

# ---------- preflight checks ---------------------------------------------
echo "============================================="
echo " API Gateway — Battle Test Runner"
echo " $(date)"
echo "============================================="
echo ""

# Verify Docker stack is running
REQUIRED_CONTAINERS=("api-gw-kong" "api-gw-postgres" "api-gw-redis" "api-gw-admin-panel")
ALL_UP=true
for c in "${REQUIRED_CONTAINERS[@]}"; do
  if docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null | grep -q true; then
    echo "  [OK] $c"
  else
    echo "  [!!] $c is NOT running"
    ALL_UP=false
  fi
done

if ! $ALL_UP; then
  echo ""
  echo "ERROR: Not all required containers are running."
  echo "Run:  docker compose up -d"
  exit 1
fi

echo ""
echo "All containers healthy. Starting battle tests..."
echo ""

# ---------- suite metadata ------------------------------------------------
declare -A SUITE_NAMES=(
  [13]="Load & Stress"
  [14]="E2E Subscriber Lifecycle"
  [15]="Chaos & Resilience"
  [16]="Data Scale"
  [17]="Security Adversarial"
)

declare -A SUITE_FILES=(
  [13]="integration/test_13_load.py"
  [14]="integration/test_14_e2e_subscriber.py"
  [15]="integration/test_15_chaos.py"
  [16]="integration/test_16_scale.py"
  [17]="integration/test_17_adversarial.py"
)

# ---------- run suites ----------------------------------------------------
OVERALL_PASS=0
OVERALL_FAIL=0
OVERALL_SKIP=0
OVERALL_ERROR=0
SUITE_RESULTS=""
SUITE_EXIT_CODES=()

for num in "${SUITES[@]}"; do
  [[ -z "$num" ]] && continue
  name="${SUITE_NAMES[$num]}"
  file="${SUITE_FILES[$num]}"

  echo "---------------------------------------------"
  echo " Suite $num: $name"
  echo "---------------------------------------------"

  JUNIT_FILE="$RESULTS_DIR/battle-test-${num}-${TIMESTAMP}.xml"
  SUITE_START=$(date +%s)

  set +e
  cd "$TEST_DIR" && python3 -m pytest "$file" \
    -v --tb=short \
    --junitxml="$JUNIT_FILE" \
    -q 2>&1 | tee "/tmp/battle-test-${num}.log"
  EXIT_CODE=${PIPESTATUS[0]}
  set -e

  SUITE_END=$(date +%s)
  SUITE_DURATION=$((SUITE_END - SUITE_START))

  # Parse pytest summary line: "X passed, Y failed, Z skipped, W error"
  SUMMARY_LINE=$(tail -5 "/tmp/battle-test-${num}.log" | grep -E "passed|failed|error|no tests" | tail -1 || echo "")
  PASSED=$(echo "$SUMMARY_LINE" | grep -oP '\d+ passed' | grep -oP '\d+' || echo 0)
  FAILED=$(echo "$SUMMARY_LINE" | grep -oP '\d+ failed' | grep -oP '\d+' || echo 0)
  SKIPPED=$(echo "$SUMMARY_LINE" | grep -oP '\d+ skipped' | grep -oP '\d+' || echo 0)
  ERRORS=$(echo "$SUMMARY_LINE" | grep -oP '\d+ error' | grep -oP '\d+' || echo 0)

  PASSED=${PASSED:-0}
  FAILED=${FAILED:-0}
  SKIPPED=${SKIPPED:-0}
  ERRORS=${ERRORS:-0}

  OVERALL_PASS=$((OVERALL_PASS + PASSED))
  OVERALL_FAIL=$((OVERALL_FAIL + FAILED))
  OVERALL_SKIP=$((OVERALL_SKIP + SKIPPED))
  OVERALL_ERROR=$((OVERALL_ERROR + ERRORS))
  SUITE_EXIT_CODES+=("$EXIT_CODE")

  STATUS="PASS"
  [[ $EXIT_CODE -ne 0 ]] && STATUS="FAIL"

  echo ""
  echo "  Result: $STATUS  |  Passed=$PASSED  Failed=$FAILED  Skipped=$SKIPPED  Errors=$ERRORS  Duration=${SUITE_DURATION}s"
  echo ""

  # Build JSON fragment
  SUITE_RESULTS="${SUITE_RESULTS}$(cat <<EOJSON
    {
      "suite": $num,
      "name": "$name",
      "file": "$file",
      "status": "$STATUS",
      "exit_code": $EXIT_CODE,
      "passed": $PASSED,
      "failed": $FAILED,
      "skipped": $SKIPPED,
      "errors": $ERRORS,
      "duration_seconds": $SUITE_DURATION,
      "junit_xml": "$JUNIT_FILE"
    },
EOJSON
)"
done

# ---------- aggregate results ---------------------------------------------
TOTAL_TESTS=$((OVERALL_PASS + OVERALL_FAIL + OVERALL_SKIP + OVERALL_ERROR))
OVERALL_STATUS="PASS"
for ec in "${SUITE_EXIT_CODES[@]}"; do
  [[ $ec -ne 0 ]] && OVERALL_STATUS="FAIL" && break
done

# Trim trailing comma from SUITE_RESULTS
SUITE_RESULTS="${SUITE_RESULTS%,}"

cat > "$JSON_REPORT" <<EOJSON
{
  "battle_test_report": {
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "overall_status": "$OVERALL_STATUS",
    "total_tests": $TOTAL_TESTS,
    "total_passed": $OVERALL_PASS,
    "total_failed": $OVERALL_FAIL,
    "total_skipped": $OVERALL_SKIP,
    "total_errors": $OVERALL_ERROR,
    "pass_rate": "$(echo "scale=1; $OVERALL_PASS * 100 / ($TOTAL_TESTS)" | bc 2>/dev/null || echo "N/A")%",
    "suites": [
${SUITE_RESULTS}
    ],
    "environment": {
      "docker_compose": true,
      "kong_version": "$(docker exec api-gw-kong kong version 2>/dev/null || echo 'unknown')",
      "admin_panel": "FastAPI",
      "database": "PostgreSQL",
      "cache": "Redis"
    }
  }
}
EOJSON

echo ""
echo "============================================="
echo " Battle Test Summary"
echo "============================================="
echo " Status:   $OVERALL_STATUS"
echo " Total:    $TOTAL_TESTS tests"
echo " Passed:   $OVERALL_PASS"
echo " Failed:   $OVERALL_FAIL"
echo " Skipped:  $OVERALL_SKIP"
echo " Errors:   $OVERALL_ERROR"
echo ""
echo " JSON report: $JSON_REPORT"
echo "============================================="

# ---------- exit ----------------------------------------------------------
if [[ "$OVERALL_STATUS" == "FAIL" ]]; then
  exit 1
fi
exit 0
