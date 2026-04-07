#!/usr/bin/env bash
# =============================================================================
# Seed Mock OIDC Users into the Admin Panel Database
# =============================================================================
# Pre-creates user records and assigns RBAC roles so that when mock OIDC
# users log in, they already have the correct permissions.
#
# This script is idempotent -- safe to run multiple times.
#
# Test accounts:
#   admin@sleepnumber.local    → super_admin (full platform access)
#   operator@sleepnumber.local → operator (day-to-day ops, cannot approve APIs)
#   teamlead@sleepnumber.local → operator (+ will be team owner after login)
#   developer@sleepnumber.local → (no platform role, team member only)
#   viewer@sleepnumber.local   → viewer (read-only)
#   newuser@sleepnumber.local  → (no roles -- tests auto-provisioning)
# =============================================================================

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
log_success() { echo -e "${GREEN}[OK]${NC}   $*"; }

# Source .env for database credentials
if [ -f .env ]; then
    set -a; source .env; set +a
fi

DB_USER="${POSTGRES_USER:-postgres}"
DB_NAME="${ADMIN_DB_NAME:-api_gateway_admin}"

log_info "Seeding mock OIDC users and role assignments..."

docker compose exec -T postgres psql -U "$DB_USER" -d "$DB_NAME" <<'SQL'
-- ==========================================================================
-- Step 1: Ensure default roles exist (should already be seeded by app startup)
-- ==========================================================================
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM roles WHERE name = 'super_admin') THEN
        RAISE NOTICE 'Roles not yet seeded. Start the admin-panel first, then re-run this script.';
        RETURN;
    END IF;
END $$;

-- ==========================================================================
-- Step 2: Insert mock users (idempotent via ON CONFLICT)
-- ==========================================================================
INSERT INTO users (email, name, entra_oid, roles)
VALUES
    ('admin@sleepnumber.local',     'Platform Admin',   'admin-oid-001',     '{}'),
    ('operator@sleepnumber.local',  'DevOps Operator',  'operator-oid-002',  '{}'),
    ('teamlead@sleepnumber.local',  'API Team Lead',    'teamlead-oid-003',  '{}'),
    ('developer@sleepnumber.local', 'Team Developer',   'developer-oid-004', '{}'),
    ('viewer@sleepnumber.local',    'Read Only User',   'viewer-oid-005',    '{}')
ON CONFLICT (entra_oid) DO UPDATE SET
    email = EXCLUDED.email,
    name = EXCLUDED.name;

-- newuser@sleepnumber.local is intentionally NOT pre-created.
-- They test the auto-provisioning flow (first OIDC login creates the record).

-- ==========================================================================
-- Step 3: Assign platform RBAC roles
-- ==========================================================================

-- admin@sleepnumber.local → super_admin
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.entra_oid = 'admin-oid-001' AND r.name = 'super_admin'
ON CONFLICT DO NOTHING;

-- operator@sleepnumber.local → operator
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.entra_oid = 'operator-oid-002' AND r.name = 'operator'
ON CONFLICT DO NOTHING;

-- teamlead@sleepnumber.local → operator
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.entra_oid = 'teamlead-oid-003' AND r.name = 'operator'
ON CONFLICT DO NOTHING;

-- developer@sleepnumber.local → (no platform role, team member only)
-- This user has no platform RBAC role. They can only access resources
-- through team membership once a team admin adds them.

-- viewer@sleepnumber.local → viewer
INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u, roles r
WHERE u.entra_oid = 'viewer-oid-005' AND r.name = 'viewer'
ON CONFLICT DO NOTHING;

-- ==========================================================================
-- Step 4: Create a sample team for testing self-service workflows
-- ==========================================================================
INSERT INTO teams (name, slug, description, contact_email, is_active)
VALUES (
    'Payments API Team',
    'payments-api',
    'Team responsible for the payments processing APIs',
    'payments-team@sleepnumber.local',
    TRUE
)
ON CONFLICT (slug) DO NOTHING;

-- Add team members
INSERT INTO team_members (team_id, user_id, role)
SELECT t.id, u.id, 'owner'
FROM teams t, users u
WHERE t.slug = 'payments-api' AND u.entra_oid = 'teamlead-oid-003'
ON CONFLICT (team_id, user_id) DO NOTHING;

INSERT INTO team_members (team_id, user_id, role)
SELECT t.id, u.id, 'member'
FROM teams t, users u
WHERE t.slug = 'payments-api' AND u.entra_oid = 'developer-oid-004'
ON CONFLICT (team_id, user_id) DO NOTHING;

-- Create a second team to test cross-team isolation
INSERT INTO teams (name, slug, description, contact_email, is_active)
VALUES (
    'Inventory Services Team',
    'inventory-svc',
    'Team responsible for inventory and warehouse APIs',
    'inventory-team@sleepnumber.local',
    TRUE
)
ON CONFLICT (slug) DO NOTHING;

-- ==========================================================================
-- Summary
-- ==========================================================================
SELECT
    u.email,
    u.name,
    COALESCE(string_agg(r.name, ', '), '(no roles)') AS platform_roles,
    COALESCE(
        (SELECT string_agg(t.slug || ':' || tm.role, ', ')
         FROM team_members tm
         JOIN teams t ON t.id = tm.team_id
         WHERE tm.user_id = u.id),
        '(no teams)'
    ) AS team_memberships
FROM users u
LEFT JOIN user_roles ur ON ur.user_id = u.id
LEFT JOIN roles r ON r.id = ur.role_id
WHERE u.email LIKE '%sleepnumber.local'
GROUP BY u.id, u.email, u.name
ORDER BY u.email;
SQL

log_success "Mock users seeded successfully"
echo ""
echo "  Test Accounts (login at http://localhost:8180):"
echo "  ─────────────────────────────────────────────────────────────"
echo "  admin    / admin      → super_admin (full access)"
echo "  operator / operator   → operator (ops, no API approval)"
echo "  teamlead / teamlead   → operator + payments-api team owner"
echo "  developer / developer → no platform role, payments-api member"
echo "  viewer   / viewer     → viewer (read-only)"
echo "  newuser  / newuser    → no roles (tests auto-provisioning)"
echo ""
