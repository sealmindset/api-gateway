#!/bin/bash
# =============================================================================
# Database Initialization Script
# =============================================================================
# Executed by PostgreSQL on first container start via docker-entrypoint-initdb.d.
# Uses environment variables for passwords so they match docker-compose config.
# =============================================================================

set -e

# Passwords from environment (set by docker-compose) with fallback defaults
KONG_PW="${KONG_PG_PASSWORD:-kong_local_dev}"
ADMIN_PW="${ADMIN_DB_PASSWORD:-admin_local_dev}"
READONLY_PW="readonly_local_dev"
KONG_DB="${KONG_PG_DATABASE:-kong}"
KONG_USER="${KONG_PG_USER:-kong}"
ADMIN_DB="${ADMIN_DB_NAME:-api_gateway_admin}"
ADMIN_USER="${ADMIN_DB_USER:-api_gateway_admin}"

echo "Creating database users and databases..."

# Create users
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${KONG_USER}') THEN
            CREATE ROLE ${KONG_USER} WITH LOGIN PASSWORD '${KONG_PW}';
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = '${ADMIN_USER}') THEN
            CREATE ROLE ${ADMIN_USER} WITH LOGIN PASSWORD '${ADMIN_PW}';
        END IF;
        IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'api_gateway_readonly') THEN
            CREATE ROLE api_gateway_readonly WITH LOGIN PASSWORD '${READONLY_PW}';
        END IF;
    END
    \$\$;
EOSQL

# Create databases
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE ${KONG_DB} OWNER ${KONG_USER}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${KONG_DB}')\gexec

    SELECT 'CREATE DATABASE ${ADMIN_DB} OWNER ${ADMIN_USER}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${ADMIN_DB}')\gexec

    GRANT ALL PRIVILEGES ON DATABASE ${KONG_DB} TO ${KONG_USER};
    GRANT ALL PRIVILEGES ON DATABASE ${ADMIN_DB} TO ${ADMIN_USER};
    GRANT CONNECT ON DATABASE ${ADMIN_DB} TO api_gateway_readonly;
EOSQL

# Run migrations on admin panel database
echo "Running migrations on ${ADMIN_DB}..."
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$ADMIN_DB" <<-EOSQL
    GRANT ALL ON SCHEMA public TO ${ADMIN_USER};
    GRANT USAGE ON SCHEMA public TO api_gateway_readonly;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$ADMIN_DB" \
    -f /docker-entrypoint-initdb.d/migrations/001_initial_schema.sql

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$ADMIN_DB" \
    -f /docker-entrypoint-initdb.d/migrations/002_kong_sync_functions.sql

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$ADMIN_DB" \
    -f /docker-entrypoint-initdb.d/migrations/003_ai_layer.sql

# Grant read-only access
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$ADMIN_DB" <<-EOSQL
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_gateway_readonly;
    ALTER DEFAULT PRIVILEGES FOR ROLE ${ADMIN_USER} IN SCHEMA public
        GRANT SELECT ON TABLES TO api_gateway_readonly;
EOSQL

echo "Database initialization completed successfully."
