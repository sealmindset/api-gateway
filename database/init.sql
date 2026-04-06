-- =============================================================================
-- Database Initialization Script
-- =============================================================================
-- This script is executed by PostgreSQL on first container start via the
-- docker-entrypoint-initdb.d mechanism. It creates databases, users, and
-- runs migrations in order.
--
-- NOTE: This script runs as the POSTGRES_USER (superuser) defined in
-- docker-compose.yml. It should only be used for local development.
-- Production databases are managed via Terraform and separate migration tools.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Create database users
-- ---------------------------------------------------------------------------

-- Kong database user (read/write to Kong's own database)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'kong') THEN
        CREATE ROLE kong WITH LOGIN PASSWORD 'kong_local_dev';
    END IF;
END
$$;

-- Admin panel database user
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'api_gateway_admin') THEN
        CREATE ROLE api_gateway_admin WITH LOGIN PASSWORD 'admin_local_dev';
    END IF;
END
$$;

-- Read-only user for monitoring/reporting
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'api_gateway_readonly') THEN
        CREATE ROLE api_gateway_readonly WITH LOGIN PASSWORD 'readonly_local_dev';
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Create databases
-- ---------------------------------------------------------------------------

-- Kong database
SELECT 'CREATE DATABASE kong OWNER kong'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'kong')\gexec

-- Admin panel database
SELECT 'CREATE DATABASE api_gateway_admin OWNER api_gateway_admin'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'api_gateway_admin')\gexec

-- ---------------------------------------------------------------------------
-- Grant permissions on Kong database
-- ---------------------------------------------------------------------------
GRANT ALL PRIVILEGES ON DATABASE kong TO kong;

-- ---------------------------------------------------------------------------
-- Grant permissions on Admin Panel database
-- ---------------------------------------------------------------------------
GRANT ALL PRIVILEGES ON DATABASE api_gateway_admin TO api_gateway_admin;
GRANT CONNECT ON DATABASE api_gateway_admin TO api_gateway_readonly;

-- ---------------------------------------------------------------------------
-- Run migrations on admin panel database
-- ---------------------------------------------------------------------------
-- Switch to the api_gateway_admin database to run migrations
\connect api_gateway_admin

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO api_gateway_admin;
GRANT USAGE ON SCHEMA public TO api_gateway_readonly;

-- Run migrations in order
\i /docker-entrypoint-initdb.d/migrations/001_initial_schema.sql
\i /docker-entrypoint-initdb.d/migrations/002_kong_sync_functions.sql

-- Grant read-only access to the readonly user on all existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO api_gateway_readonly;

-- Ensure future tables also grant read access to readonly user
ALTER DEFAULT PRIVILEGES FOR ROLE api_gateway_admin IN SCHEMA public
    GRANT SELECT ON TABLES TO api_gateway_readonly;

-- ---------------------------------------------------------------------------
-- Verification
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    -- Verify tables exist
    ASSERT (SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'users') = 1,
        'Table "users" not found';
    ASSERT (SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'subscribers') = 1,
        'Table "subscribers" not found';
    ASSERT (SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'api_keys') = 1,
        'Table "api_keys" not found';
    ASSERT (SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = 'plans') = 1,
        'Table "plans" not found';

    -- Verify default data
    ASSERT (SELECT COUNT(*) FROM roles WHERE is_system = TRUE) = 4,
        'Expected 4 system roles';
    ASSERT (SELECT COUNT(*) FROM plans WHERE is_active = TRUE) = 4,
        'Expected 4 active plans';

    RAISE NOTICE 'Database initialization completed successfully.';
END
$$;
