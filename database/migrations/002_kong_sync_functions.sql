-- =============================================================================
-- Migration 002: Kong Sync Functions
-- =============================================================================
-- PostgreSQL functions and triggers for real-time synchronization between
-- the admin panel database and Kong Gateway. Uses NOTIFY/LISTEN for
-- event-driven updates.
--
-- Sync flow:
--   1. Admin panel creates/updates subscriber -> trigger fires
--   2. PostgreSQL NOTIFY sends event on 'kong_sync' channel
--   3. Sync worker (admin-panel or dedicated service) receives event
--   4. Worker calls Kong Admin API to apply changes
--
-- NOTE: Kong consumer/key IDs are NOT stored in the database. The application
-- layer (admin-panel/app/routers/subscribers.py) manages Kong sync via httpx
-- calls. These functions build the sync payloads that the app layer sends.
-- =============================================================================

BEGIN;

-- =============================================================================
-- Function: Sync subscriber to Kong consumer
-- =============================================================================
-- Builds the Kong consumer payload for a given subscriber.
-- The app layer uses this to create/update Kong consumers via Admin API.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sync_subscriber_to_kong_consumer(p_subscriber_id UUID)
RETURNS JSONB AS $$
DECLARE
    v_subscriber RECORD;
    v_result JSONB;
BEGIN
    SELECT
        s.id,
        s.name,
        s.organization,
        s.email,
        s.tier,
        s.status
    INTO v_subscriber
    FROM subscribers s
    WHERE s.id = p_subscriber_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Subscriber % not found', p_subscriber_id;
    END IF;

    -- Build Kong consumer payload
    -- The consumer username is derived from the subscriber for uniqueness
    v_result := jsonb_build_object(
        'action', CASE
            WHEN v_subscriber.status = 'active' THEN 'upsert'
            ELSE 'delete'
        END,
        'consumer', jsonb_build_object(
            'username', 'sub-' || v_subscriber.id::TEXT,
            'custom_id', v_subscriber.id::TEXT,
            'tags', jsonb_build_array(
                'managed-by:admin-panel',
                'org:' || COALESCE(v_subscriber.organization, 'none'),
                'tier:' || v_subscriber.tier,
                'status:' || v_subscriber.status
            )
        ),
        'subscriber_id', v_subscriber.id::TEXT
    );

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Function: Sync API key to Kong key-auth credential
-- =============================================================================
-- Generates the Kong key-auth payload for a given API key record.
-- The actual key value must be passed in (it's not stored in plaintext).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sync_api_key_to_kong(
    p_api_key_id UUID,
    p_key_value TEXT DEFAULT NULL  -- Only needed for new keys
)
RETURNS JSONB AS $$
DECLARE
    v_key RECORD;
    v_result JSONB;
BEGIN
    -- Fetch API key details
    SELECT
        ak.id,
        ak.subscriber_id,
        ak.name,
        ak.is_active,
        ak.scopes,
        ak.expires_at
    INTO v_key
    FROM api_keys ak
    WHERE ak.id = p_api_key_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'API key % not found', p_api_key_id;
    END IF;

    -- Determine action
    IF NOT v_key.is_active THEN
        -- Key is inactive: delete from Kong
        v_result := jsonb_build_object(
            'action', 'delete',
            'subscriber_id', v_key.subscriber_id::TEXT,
            'api_key_id', v_key.id::TEXT
        );
    ELSE
        -- Active key: create/update in Kong
        IF p_key_value IS NULL THEN
            -- No key value means this is a reconciliation check, not a new key
            v_result := jsonb_build_object(
                'action', 'reconcile',
                'subscriber_id', v_key.subscriber_id::TEXT,
                'api_key_id', v_key.id::TEXT,
                'name', v_key.name
            );
        ELSE
            -- New key: create in Kong
            v_result := jsonb_build_object(
                'action', 'create',
                'subscriber_id', v_key.subscriber_id::TEXT,
                'credential', jsonb_build_object(
                    'key', p_key_value,
                    'tags', jsonb_build_array(
                        'managed-by:admin-panel',
                        'api-key-id:' || v_key.id::TEXT,
                        'name:' || v_key.name
                    )
                ),
                'api_key_id', v_key.id::TEXT
            );
        END IF;
    END IF;

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Function: Sync subscription rate limits to Kong
-- =============================================================================
-- When a subscriber's plan changes, this function generates the Kong
-- rate-limiting plugin configuration to be applied to their consumer.
-- Subscription-level overrides take priority over plan defaults.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sync_subscription_rate_limits(p_subscription_id UUID)
RETURNS JSONB AS $$
DECLARE
    v_sub RECORD;
    v_result JSONB;
    v_plugin_config JSONB;
BEGIN
    -- Fetch subscription with plan and subscriber details
    -- Subscription-level rate limits override plan defaults when set
    SELECT
        sub.id AS subscription_id,
        sub.status,
        s.id AS subscriber_id,
        p.name AS plan_name,
        COALESCE(sub.rate_limit_per_second, p.rate_limit_second) AS rl_second,
        COALESCE(sub.rate_limit_per_minute, p.rate_limit_minute) AS rl_minute,
        COALESCE(sub.rate_limit_per_hour, p.rate_limit_hour) AS rl_hour
    INTO v_sub
    FROM subscriptions sub
    JOIN subscribers s ON s.id = sub.subscriber_id
    JOIN plans p ON p.id = sub.plan_id
    WHERE sub.id = p_subscription_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Subscription % not found', p_subscription_id;
    END IF;

    -- Build rate-limiting plugin config
    v_plugin_config := jsonb_build_object(
        'name', 'rate-limiting',
        'config', jsonb_strip_nulls(jsonb_build_object(
            'second', v_sub.rl_second,
            'minute', v_sub.rl_minute,
            'hour', v_sub.rl_hour,
            'policy', 'redis',
            'fault_tolerant', true,
            'hide_client_headers', false,
            'error_code', 429,
            'error_message', 'Rate limit exceeded for plan: ' || v_sub.plan_name
        ))
    );

    v_result := jsonb_build_object(
        'action', CASE
            WHEN v_sub.status = 'active' THEN 'upsert'
            ELSE 'delete'
        END,
        'subscriber_id', v_sub.subscriber_id::TEXT,
        'subscription_id', v_sub.subscription_id::TEXT,
        'plan', v_sub.plan_name,
        'plugins', jsonb_build_array(v_plugin_config)
    );

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Function: Get full Kong sync payload for a subscriber
-- =============================================================================
-- Aggregates consumer, keys, and rate limits into a single sync payload.
-- Used for initial sync or reconciliation.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION get_subscriber_kong_sync_payload(p_subscriber_id UUID)
RETURNS JSONB AS $$
DECLARE
    v_consumer JSONB;
    v_keys JSONB;
    v_rate_limits JSONB;
    v_active_sub_id UUID;
BEGIN
    -- Get consumer payload
    v_consumer := sync_subscriber_to_kong_consumer(p_subscriber_id);

    -- Get all active API keys (without plaintext values - for reconciliation only)
    SELECT COALESCE(jsonb_agg(
        jsonb_build_object(
            'api_key_id', ak.id::TEXT,
            'name', ak.name,
            'is_active', ak.is_active,
            'key_prefix', ak.key_prefix
        )
    ), '[]'::JSONB)
    INTO v_keys
    FROM api_keys ak
    WHERE ak.subscriber_id = p_subscriber_id
      AND ak.is_active = TRUE;

    -- Get active subscription rate limits
    SELECT sub.id INTO v_active_sub_id
    FROM subscriptions sub
    WHERE sub.subscriber_id = p_subscriber_id
      AND sub.status = 'active'
    LIMIT 1;

    IF v_active_sub_id IS NOT NULL THEN
        v_rate_limits := sync_subscription_rate_limits(v_active_sub_id);
    ELSE
        v_rate_limits := jsonb_build_object(
            'action', 'delete',
            'message', 'No active subscription'
        );
    END IF;

    RETURN jsonb_build_object(
        'subscriber_id', p_subscriber_id::TEXT,
        'consumer', v_consumer,
        'api_keys', v_keys,
        'rate_limits', v_rate_limits,
        'synced_at', NOW()::TEXT
    );
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Notification Triggers for Real-Time Sync
-- =============================================================================
-- These triggers send PostgreSQL NOTIFY events when data changes, allowing
-- the sync worker to react in real-time.
-- ---------------------------------------------------------------------------

-- Notify on subscriber changes
CREATE OR REPLACE FUNCTION notify_subscriber_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('kong_sync', json_build_object(
        'type', 'subscriber',
        'action', TG_OP,
        'subscriber_id', CASE
            WHEN TG_OP = 'DELETE' THEN OLD.id::TEXT
            ELSE NEW.id::TEXT
        END,
        'timestamp', NOW()::TEXT
    )::TEXT);

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_subscriber_kong_notify
    AFTER INSERT OR UPDATE OR DELETE ON subscribers
    FOR EACH ROW EXECUTE FUNCTION notify_subscriber_change();

-- Notify on API key changes
CREATE OR REPLACE FUNCTION notify_api_key_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('kong_sync', json_build_object(
        'type', 'api_key',
        'action', TG_OP,
        'api_key_id', CASE
            WHEN TG_OP = 'DELETE' THEN OLD.id::TEXT
            ELSE NEW.id::TEXT
        END,
        'subscriber_id', CASE
            WHEN TG_OP = 'DELETE' THEN OLD.subscriber_id::TEXT
            ELSE NEW.subscriber_id::TEXT
        END,
        'timestamp', NOW()::TEXT
    )::TEXT);

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_api_key_kong_notify
    AFTER INSERT OR UPDATE OR DELETE ON api_keys
    FOR EACH ROW EXECUTE FUNCTION notify_api_key_change();

-- Notify on subscription changes (plan upgrades/downgrades, cancellations)
CREATE OR REPLACE FUNCTION notify_subscription_change()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('kong_sync', json_build_object(
        'type', 'subscription',
        'action', TG_OP,
        'subscription_id', CASE
            WHEN TG_OP = 'DELETE' THEN OLD.id::TEXT
            ELSE NEW.id::TEXT
        END,
        'subscriber_id', CASE
            WHEN TG_OP = 'DELETE' THEN OLD.subscriber_id::TEXT
            ELSE NEW.subscriber_id::TEXT
        END,
        'plan_id', CASE
            WHEN TG_OP = 'DELETE' THEN OLD.plan_id::TEXT
            ELSE NEW.plan_id::TEXT
        END,
        'status', CASE
            WHEN TG_OP = 'DELETE' THEN OLD.status
            ELSE NEW.status
        END,
        'timestamp', NOW()::TEXT
    )::TEXT);

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_subscription_kong_notify
    AFTER INSERT OR UPDATE OR DELETE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION notify_subscription_change();

COMMIT;
