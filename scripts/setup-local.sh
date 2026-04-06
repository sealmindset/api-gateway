#!/usr/bin/env bash
# =============================================================================
# Local Development Setup Script - API Gateway
# =============================================================================
# Sets up the complete local development environment:
#   1. Checks prerequisites
#   2. Configures environment variables
#   3. Starts Docker Compose services
#   4. Waits for health checks
#   5. Seeds default data
#   6. Prints access URLs
#
# Usage:
#   ./scripts/setup-local.sh          # Full setup
#   ./scripts/setup-local.sh --reset  # Tear down and recreate everything
# =============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}   $*"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error()   { echo -e "${RED}[ERR]${NC}  $*"; }

check_command() {
    if command -v "$1" &> /dev/null; then
        log_success "$1 found: $(command -v "$1")"
        return 0
    else
        log_error "$1 is not installed. Please install it first."
        return 1
    fi
}

wait_for_healthy() {
    local service="$1"
    local max_attempts="${2:-30}"
    local attempt=1

    log_info "Waiting for $service to be healthy..."
    while [ $attempt -le $max_attempts ]; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "api-gw-${service}" 2>/dev/null || echo "not_found")
        if [ "$status" = "healthy" ]; then
            log_success "$service is healthy"
            return 0
        fi
        printf "  Attempt %d/%d (status: %s)\r" "$attempt" "$max_attempts" "$status"
        sleep 2
        attempt=$((attempt + 1))
    done
    echo ""
    log_error "$service failed to become healthy after $max_attempts attempts"
    return 1
}

# ---------------------------------------------------------------------------
# Handle --reset flag
# ---------------------------------------------------------------------------
if [ "${1:-}" = "--reset" ]; then
    log_warn "Resetting local environment (this will destroy all data)..."
    read -rp "Are you sure? (y/N): " confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        docker compose down -v --remove-orphans 2>/dev/null || true
        log_success "Environment reset complete"
    else
        log_info "Reset cancelled"
        exit 0
    fi
fi

echo ""
echo "============================================="
echo "  API Gateway - Local Development Setup"
echo "============================================="
echo ""

# ---------------------------------------------------------------------------
# Step 1: Check prerequisites
# ---------------------------------------------------------------------------
log_info "Checking prerequisites..."
MISSING=0

check_command "docker" || MISSING=1
check_command "docker" || MISSING=1  # docker compose is a subcommand now

# Verify Docker Compose v2
if docker compose version &> /dev/null; then
    log_success "docker compose v2 found"
else
    log_error "docker compose v2 not found. Please update Docker."
    MISSING=1
fi

# Terraform is optional for local dev but recommended
if command -v terraform &> /dev/null; then
    log_success "terraform found: $(terraform version -json 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["terraform_version"])' 2>/dev/null || terraform version | head -1)"
else
    log_warn "terraform not found (optional for local development)"
fi

# Check Docker is running
if docker info &> /dev/null; then
    log_success "Docker daemon is running"
else
    log_error "Docker daemon is not running. Please start Docker."
    MISSING=1
fi

if [ $MISSING -ne 0 ]; then
    echo ""
    log_error "Missing prerequisites. Please install them and try again."
    exit 1
fi
echo ""

# ---------------------------------------------------------------------------
# Step 2: Configure environment variables
# ---------------------------------------------------------------------------
log_info "Configuring environment..."

if [ ! -f ".env" ]; then
    log_info "Creating .env from .env.example..."
    cp .env.example .env

    # Generate local secrets
    log_info "Generating local secrets..."

    # Generate a random SECRET_KEY
    SECRET_KEY=$(openssl rand -hex 32)
    sed -i.bak "s|SECRET_KEY=.*|SECRET_KEY=${SECRET_KEY}|" .env

    # Generate random passwords (for local dev only)
    POSTGRES_PASSWORD=$(openssl rand -hex 16)
    REDIS_PASSWORD=$(openssl rand -hex 16)
    KONG_PG_PASSWORD=$(openssl rand -hex 16)
    ADMIN_DB_PASSWORD=$(openssl rand -hex 16)

    sed -i.bak "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=${POSTGRES_PASSWORD}|" .env
    sed -i.bak "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=${REDIS_PASSWORD}|" .env
    sed -i.bak "s|KONG_PG_PASSWORD=.*|KONG_PG_PASSWORD=${KONG_PG_PASSWORD}|" .env
    sed -i.bak "s|ADMIN_DB_PASSWORD=.*|ADMIN_DB_PASSWORD=${ADMIN_DB_PASSWORD}|" .env

    # Clean up sed backup files
    rm -f .env.bak

    log_success ".env created with generated secrets"
else
    log_success ".env already exists (keeping existing configuration)"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 3: Start Docker Compose services
# ---------------------------------------------------------------------------
log_info "Starting Docker Compose services..."

# Pull images first
docker compose pull --ignore-pull-failures 2>/dev/null || true

# Build custom images
log_info "Building custom images..."
docker compose build --parallel

# Start services
log_info "Starting services..."
docker compose up -d

echo ""

# ---------------------------------------------------------------------------
# Step 4: Wait for services to be healthy
# ---------------------------------------------------------------------------
log_info "Waiting for services to become healthy..."

wait_for_healthy "postgres" 30
wait_for_healthy "redis" 20
wait_for_healthy "kong" 45
wait_for_healthy "admin-panel" 45
wait_for_healthy "frontend" 45
wait_for_healthy "prometheus" 20
wait_for_healthy "grafana" 20

echo ""

# ---------------------------------------------------------------------------
# Step 5: Import Kong declarative config
# ---------------------------------------------------------------------------
log_info "Importing Kong declarative config..."
if docker compose exec -T kong kong config db_import /etc/kong/kong.yml 2>/dev/null; then
    log_success "Kong config imported"
else
    log_warn "Kong config import skipped (may already exist)"
fi
echo ""

# ---------------------------------------------------------------------------
# Step 6: Seed default data
# ---------------------------------------------------------------------------
log_info "Seeding default admin user..."

# Source .env for database connection details
set -a
source .env
set +a

# Create default super_admin user (password: admin - change immediately)
docker compose exec -T postgres psql \
    -U "${POSTGRES_USER:-postgres}" \
    -d api_gateway_admin \
    -c "
    DO \$\$
    DECLARE
        v_role_id UUID;
        v_user_id UUID;
    BEGIN
        -- Check if admin user already exists
        IF EXISTS (SELECT 1 FROM users WHERE email = 'admin@localhost') THEN
            RAISE NOTICE 'Default admin user already exists, skipping.';
            RETURN;
        END IF;

        -- Get super_admin role
        SELECT id INTO v_role_id FROM roles WHERE name = 'super_admin';

        -- Create admin user (password: 'admin' hashed with pgcrypto)
        INSERT INTO users (email, username, password_hash, first_name, last_name, is_active, is_verified)
        VALUES (
            'admin@localhost',
            'admin',
            crypt('admin', gen_salt('bf', 12)),
            'System',
            'Administrator',
            TRUE,
            TRUE
        )
        RETURNING id INTO v_user_id;

        -- Assign super_admin role
        INSERT INTO user_roles (user_id, role_id) VALUES (v_user_id, v_role_id);

        RAISE NOTICE 'Default admin user created successfully.';
    END
    \$\$;
    " 2>/dev/null

log_success "Default data seeded"
echo ""

# ---------------------------------------------------------------------------
# Step 7: Print access URLs
# ---------------------------------------------------------------------------
echo "============================================="
echo "  Local Development Environment Ready!"
echo "============================================="
echo ""
echo "  Service URLs:"
echo "  -------------------------------------------"
echo -e "  Admin UI:        ${GREEN}http://localhost:${FRONTEND_PORT:-3000}${NC}"
echo -e "  Admin Panel API: ${GREEN}http://localhost:${ADMIN_PANEL_PORT:-8880}${NC}"
echo -e "  Kong Proxy:      ${GREEN}http://localhost:${KONG_PROXY_PORT:-8800}${NC}"
echo -e "  Kong Admin API:  ${GREEN}http://localhost:${KONG_ADMIN_PORT:-8801}${NC}"
echo -e "  Prometheus:      ${GREEN}http://localhost:${PROMETHEUS_PORT:-9190}${NC}"
echo -e "  Grafana:         ${GREEN}http://localhost:${GRAFANA_PORT:-3200}${NC}"
echo -e "  Cribl Stream:    ${GREEN}http://localhost:${CRIBL_PORT:-9421}${NC}"
echo ""
echo "  Database:"
echo "  -------------------------------------------"
echo -e "  PostgreSQL:      ${GREEN}localhost:${POSTGRES_PORT:-5434}${NC}"
echo -e "  Redis:           ${GREEN}localhost:${REDIS_PORT:-6380}${NC}"
echo ""
echo "  AI Provider:"
echo "  -------------------------------------------"
echo -e "  Provider:        ${GREEN}${AI_PROVIDER:-anthropic_foundry}${NC}"
echo -e "  Model:           ${GREEN}${ANTHROPIC_MODEL:-cogdep-aifoundry-dev-eus2-claude-sonnet-4-5}${NC}"
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
    echo -e "  API Key:         ${GREEN}configured${NC}"
else
    echo -e "  API Key:         ${YELLOW}NOT SET -- set ANTHROPIC_API_KEY in .env${NC}"
fi
if [ "${AI_PROVIDER:-anthropic_foundry}" = "anthropic_foundry" ]; then
    if [ -n "${AZURE_AI_FOUNDRY_ENDPOINT:-}" ]; then
        echo -e "  Foundry Endpoint: ${GREEN}configured${NC}"
    else
        echo -e "  Foundry Endpoint: ${YELLOW}NOT SET -- set AZURE_AI_FOUNDRY_ENDPOINT in .env${NC}"
    fi
fi
echo -e "  Sampling Rate:   ${GREEN}${AI_SAMPLING_RATE:-0.1}${NC}"
echo -e "  Cost Ceiling:    ${GREEN}\$${AI_MAX_COST_PER_ANALYSIS:-0.50}/analysis${NC}"
echo ""
echo "  Default Credentials:"
echo "  -------------------------------------------"
echo "  Admin Panel:     admin@localhost / admin"
echo "  Grafana:         admin / admin"
echo ""
echo -e "  ${YELLOW}WARNING: Change default passwords before"
echo -e "  exposing any services externally.${NC}"
echo ""
echo "  Useful commands:"
echo "  -------------------------------------------"
echo "  docker compose logs -f frontend    # Follow frontend logs"
echo "  docker compose logs -f kong        # Follow Kong logs"
echo "  docker compose logs -f admin-panel # Follow admin panel logs"
echo "  docker compose ps                  # Check service status"
echo "  docker compose down                # Stop all services"
echo "  ./scripts/kong-sync.sh             # Sync admin panel to Kong"
echo ""
