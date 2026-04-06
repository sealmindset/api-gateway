#!/usr/bin/env bash
# =============================================================================
# Kong Sync Script - API Gateway
# =============================================================================
# Synchronizes subscribers, API keys, and rate-limiting configuration from
# the admin panel database to Kong Gateway via the Kong Admin API.
#
# This script is useful for:
#   - Initial setup after Kong is deployed
#   - Reconciliation after Kong database reset
#   - Manual sync when automatic NOTIFY/LISTEN is not available
#
# Usage:
#   ./scripts/kong-sync.sh                    # Sync all active subscribers
#   ./scripts/kong-sync.sh --subscriber <id>  # Sync a specific subscriber
#   ./scripts/kong-sync.sh --dry-run          # Show what would be synced
#   ./scripts/kong-sync.sh --status           # Show sync status
# =============================================================================

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Defaults
KONG_ADMIN_URL="${KONG_ADMIN_URL:-http://localhost:8001}"
DATABASE_URL="${DATABASE_URL:-}"
DRY_RUN=false
SPECIFIC_SUBSCRIBER=""
SHOW_STATUS=false

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --subscriber)
            SPECIFIC_SUBSCRIBER="$2"
            shift 2
            ;;
        --status)
            SHOW_STATUS=true
            shift
            ;;
        --kong-url)
            KONG_ADMIN_URL="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dry-run              Show what would be synced without making changes"
            echo "  --subscriber <id>      Sync a specific subscriber by UUID"
            echo "  --status               Show sync status for all subscribers"
            echo "  --kong-url <url>       Kong Admin API URL (default: http://localhost:8001)"
            echo "  -h, --help             Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}   $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error()   { echo -e "${RED}[ERR]${NC}  $*"; }

kong_api() {
    local method="$1"
    local path="$2"
    local data="${3:-}"

    if [ -n "$data" ]; then
        curl -s -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" \
            "${KONG_ADMIN_URL}${path}"
    else
        curl -s -X "$method" "${KONG_ADMIN_URL}${path}"
    fi
}

db_query() {
    local query="$1"
    if [ -n "$DATABASE_URL" ]; then
        psql "$DATABASE_URL" -t -A -c "$query"
    else
        docker compose exec -T postgres psql \
            -U "${POSTGRES_USER:-postgres}" \
            -d api_gateway_admin \
            -t -A -c "$query"
    fi
}

# ---------------------------------------------------------------------------
# Verify connectivity
# ---------------------------------------------------------------------------
log_info "Checking Kong Admin API connectivity..."
KONG_STATUS=$(kong_api GET /status 2>/dev/null || echo "error")
if echo "$KONG_STATUS" | grep -q "database"; then
    log_success "Kong Admin API is reachable at ${KONG_ADMIN_URL}"
else
    log_error "Cannot reach Kong Admin API at ${KONG_ADMIN_URL}"
    exit 1
fi

log_info "Checking database connectivity..."
DB_CHECK=$(db_query "SELECT 1" 2>/dev/null || echo "error")
if [ "$DB_CHECK" = "1" ]; then
    log_success "Database is reachable"
else
    log_error "Cannot reach database"
    exit 1
fi

# ---------------------------------------------------------------------------
# Show sync status
# ---------------------------------------------------------------------------
if [ "$SHOW_STATUS" = true ]; then
    echo ""
    echo "============================================="
    echo "  Kong Sync Status"
    echo "============================================="
    echo ""

    # Count subscribers
    TOTAL=$(db_query "SELECT COUNT(*) FROM subscribers WHERE is_active = TRUE")
    SYNCED=$(db_query "SELECT COUNT(*) FROM subscribers WHERE is_active = TRUE AND kong_consumer_id IS NOT NULL")
    UNSYNCED=$((TOTAL - SYNCED))

    echo "  Subscribers:"
    echo "    Total active:  $TOTAL"
    echo -e "    Synced:        ${GREEN}${SYNCED}${NC}"
    if [ "$UNSYNCED" -gt 0 ]; then
        echo -e "    Unsynced:      ${RED}${UNSYNCED}${NC}"
    else
        echo -e "    Unsynced:      ${GREEN}0${NC}"
    fi

    # Count API keys
    TOTAL_KEYS=$(db_query "SELECT COUNT(*) FROM api_keys WHERE is_active = TRUE AND revoked_at IS NULL")
    SYNCED_KEYS=$(db_query "SELECT COUNT(*) FROM api_keys WHERE is_active = TRUE AND revoked_at IS NULL AND kong_key_id IS NOT NULL")
    UNSYNCED_KEYS=$((TOTAL_KEYS - SYNCED_KEYS))

    echo ""
    echo "  API Keys:"
    echo "    Total active:  $TOTAL_KEYS"
    echo -e "    Synced:        ${GREEN}${SYNCED_KEYS}${NC}"
    if [ "$UNSYNCED_KEYS" -gt 0 ]; then
        echo -e "    Unsynced:      ${RED}${UNSYNCED_KEYS}${NC}"
    else
        echo -e "    Unsynced:      ${GREEN}0${NC}"
    fi

    # Kong consumers
    KONG_CONSUMERS=$(kong_api GET /consumers 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('total', 0))" 2>/dev/null || echo "?")
    echo ""
    echo "  Kong Consumers:  $KONG_CONSUMERS"
    echo ""
    exit 0
fi

# ---------------------------------------------------------------------------
# Sync functions
# ---------------------------------------------------------------------------
sync_subscriber() {
    local sub_id="$1"
    local sub_name="$2"
    local sub_kong_id="$3"
    local sub_kong_name="$4"

    local consumer_username="${sub_kong_name:-sub-${sub_id}}"

    if [ "$DRY_RUN" = true ]; then
        if [ -n "$sub_kong_id" ]; then
            log_info "[DRY RUN] Would update Kong consumer for: $sub_name ($consumer_username)"
        else
            log_info "[DRY RUN] Would create Kong consumer for: $sub_name ($consumer_username)"
        fi
        return 0
    fi

    # Create or update Kong consumer
    local payload
    payload=$(cat <<EOF
{
    "username": "${consumer_username}",
    "custom_id": "${sub_id}",
    "tags": ["managed-by:admin-panel"]
}
EOF
    )

    local response
    if [ -n "$sub_kong_id" ]; then
        # Update existing consumer
        response=$(kong_api PUT "/consumers/${sub_kong_id}" "$payload")
    else
        # Create new consumer
        response=$(kong_api POST "/consumers" "$payload")
    fi

    # Extract consumer ID from response
    local kong_consumer_id
    kong_consumer_id=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null || echo "")

    if [ -n "$kong_consumer_id" ]; then
        # Update subscriber with Kong consumer ID
        db_query "UPDATE subscribers SET kong_consumer_id = '${kong_consumer_id}', kong_consumer_name = '${consumer_username}' WHERE id = '${sub_id}'" > /dev/null
        log_success "Synced subscriber: $sub_name -> Kong consumer: $kong_consumer_id"
    else
        log_error "Failed to sync subscriber: $sub_name"
        log_error "Response: $response"
        return 1
    fi
}

sync_rate_limits() {
    local sub_id="$1"
    local kong_consumer_id="$2"

    # Get active subscription with plan details
    local plan_data
    plan_data=$(db_query "
        SELECT json_build_object(
            'plan_name', p.name,
            'second', p.rate_limit_per_second,
            'minute', p.rate_limit_per_minute,
            'hour', p.rate_limit_per_hour,
            'day', p.rate_limit_per_day,
            'month', p.rate_limit_per_month
        )::TEXT
        FROM subscriptions sub
        JOIN plans p ON p.id = sub.plan_id
        WHERE sub.subscriber_id = '${sub_id}'
          AND sub.status = 'active'
        LIMIT 1
    " 2>/dev/null || echo "")

    if [ -z "$plan_data" ]; then
        log_warn "  No active subscription for subscriber $sub_id, skipping rate limits"
        return 0
    fi

    if [ "$DRY_RUN" = true ]; then
        log_info "  [DRY RUN] Would set rate limits: $plan_data"
        return 0
    fi

    # Apply rate-limiting plugin to consumer
    local config
    config=$(echo "$plan_data" | python3 -c "
import sys, json
data = json.load(sys.stdin)
config = {
    'name': 'rate-limiting',
    'consumer': {'id': '${kong_consumer_id}'},
    'config': {
        'policy': 'redis',
        'fault_tolerant': True,
        'hide_client_headers': False,
        'error_code': 429,
        'error_message': 'Rate limit exceeded for plan: ' + data['plan_name']
    }
}
for k in ['second', 'minute', 'hour', 'day', 'month']:
    if data.get(k):
        config['config'][k] = data[k]
print(json.dumps(config))
")

    # Upsert rate-limiting plugin (use PUT to consumer-specific plugin)
    local response
    response=$(kong_api POST "/consumers/${kong_consumer_id}/plugins" "$config" 2>/dev/null)

    if echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d.get('id')" 2>/dev/null; then
        local plan_name
        plan_name=$(echo "$plan_data" | python3 -c "import sys,json; print(json.load(sys.stdin)['plan_name'])")
        log_success "  Rate limits applied (plan: $plan_name)"
    else
        # May already exist, try to find and update
        log_warn "  Rate-limiting plugin may already exist, attempting update..."
        local existing_id
        existing_id=$(kong_api GET "/consumers/${kong_consumer_id}/plugins" 2>/dev/null | \
            python3 -c "
import sys, json
data = json.load(sys.stdin)
for p in data.get('data', []):
    if p.get('name') == 'rate-limiting':
        print(p['id'])
        break
" 2>/dev/null || echo "")

        if [ -n "$existing_id" ]; then
            response=$(kong_api PATCH "/consumers/${kong_consumer_id}/plugins/${existing_id}" "$config" 2>/dev/null)
            log_success "  Rate limits updated"
        else
            log_error "  Failed to apply rate limits"
        fi
    fi
}

# ---------------------------------------------------------------------------
# Main sync logic
# ---------------------------------------------------------------------------
echo ""
echo "============================================="
echo "  Kong Sync - $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================="
echo ""

if [ "$DRY_RUN" = true ]; then
    log_warn "DRY RUN MODE - no changes will be made"
    echo ""
fi

# Build query filter
FILTER=""
if [ -n "$SPECIFIC_SUBSCRIBER" ]; then
    FILTER="AND s.id = '${SPECIFIC_SUBSCRIBER}'"
fi

# Fetch subscribers to sync
SYNC_COUNT=0
SYNC_ERRORS=0

while IFS='|' read -r sub_id sub_name sub_kong_id sub_kong_name; do
    [ -z "$sub_id" ] && continue

    log_info "Syncing subscriber: $sub_name ($sub_id)"

    if sync_subscriber "$sub_id" "$sub_name" "$sub_kong_id" "$sub_kong_name"; then
        # Get the updated kong_consumer_id
        local_kong_id=$(db_query "SELECT kong_consumer_id FROM subscribers WHERE id = '${sub_id}'" 2>/dev/null || echo "$sub_kong_id")

        if [ -n "$local_kong_id" ]; then
            sync_rate_limits "$sub_id" "$local_kong_id"
        fi

        SYNC_COUNT=$((SYNC_COUNT + 1))
    else
        SYNC_ERRORS=$((SYNC_ERRORS + 1))
    fi
    echo ""
done < <(db_query "
    SELECT s.id, s.name, s.kong_consumer_id, s.kong_consumer_name
    FROM subscribers s
    WHERE s.is_active = TRUE
    ${FILTER}
    ORDER BY s.created_at
")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo "============================================="
echo "  Sync Complete"
echo "============================================="
echo ""
echo "  Subscribers synced:  $SYNC_COUNT"
if [ "$SYNC_ERRORS" -gt 0 ]; then
    echo -e "  Errors:              ${RED}${SYNC_ERRORS}${NC}"
else
    echo -e "  Errors:              ${GREEN}0${NC}"
fi
echo ""

if [ "$SYNC_ERRORS" -gt 0 ]; then
    exit 1
fi
