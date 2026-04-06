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
-- =============================================================================

BEGIN;

-- =============================================================================
-- Function: Sync subscriber to Kong consumer
-- =============================================================================
-- Creates or updates a Kong consumer when a subscriber is created/modified.
-- Returns the Kong consumer data as JSON for the caller to apply via Admin API.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sync_subscriber_to_kong_consumer(p_subscriber_id UUID)
RETURNS JSONB AS $$
DECLARE
    v_subscriber RECORD;
    v_result JSONB;
BEGIN
    -- Fetch subscriber details
    SELECT
        s.id,
        s.name,
        s.organization,
        s.email,
        s.is_active,
        s.kong_consumer_id,
        s.kong_consumer_name,
        s.metadata
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
            WHEN v_subscriber.kong_consumer_id IS NOT NULL THEN 'update'
            ELSE 'create'
        END,
        'consumer', jsonb_build_object(
            'username', COALESCE(
                v_subscriber.kong_consumer_name,
                'sub-' || v_subscriber.id::TEXT
            ),
            'custom_id', v_subscriber.id::TEXT,
            'tags', jsonb_build_array(
                'managed-by:admin-panel',
                'org:' || COALESCE(v_subscriber.organization, 'none'),
                CASE WHEN v_subscriber.is_active THEN 'status:active' ELSE 'status:inactive' END
            )
        ),
        'subscriber_id', v_subscriber.id::TEXT,
        'kong_consumer_id', v_subscriber.kong_consumer_id
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
    v_subscriber RECORD;
    v_result JSONB;
BEGIN
    -- Fetch API key with subscriber info
    SELECT
        ak.id,
        ak.subscriber_id,
        ak.name,
        ak.is_active,
        ak.scopes,
        ak.allowed_ips,
        ak.kong_key_id,
        ak.revoked_at,
        ak.expires_at,
        s.kong_consumer_id,
        s.kong_consumer_name
    INTO v_key
    FROM api_keys ak
    JOIN subscribers s ON s.id = ak.subscriber_id
    WHERE ak.id = p_api_key_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'API key % not found', p_api_key_id;
    END IF;

    IF v_key.kong_consumer_id IS NULL THEN
        RAISE EXCEPTION 'Subscriber % has no Kong consumer. Sync subscriber first.',
            v_key.subscriber_id;
    END IF;

    -- Determine action
    IF v_key.revoked_at IS NOT NULL OR NOT v_key.is_active THEN
        -- Key is revoked or inactive: delete from Kong
        v_result := jsonb_build_object(
            'action', 'delete',
            'kong_consumer_id', v_key.kong_consumer_id,
            'kong_key_id', v_key.kong_key_id,
            'api_key_id', v_key.id::TEXT
        );
    ELSIF v_key.kong_key_id IS NOT NULL THEN
        -- Key exists in Kong: no update needed (keys are immutable)
        v_result := jsonb_build_object(
            'action', 'noop',
            'message', 'Key already synced to Kong',
            'api_key_id', v_key.id::TEXT
        );
    ELSE
        -- New key: create in Kong
        IF p_key_value IS NULL THEN
            RAISE EXCEPTION 'Key value required for new key creation';
        END IF;

        v_result := jsonb_build_object(
            'action', 'create',
            'kong_consumer_id', v_key.kong_consumer_id,
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

    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- Function: Update Kong rate-limiting config for a subscription change
-- =============================================================================
-- When a subscriber's plan changes, this function generates the Kong
-- rate-limiting plugin configuration to be applied to their consumer.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION sync_subscription_rate_limits(p_subscription_id UUID)
RETURNS JSONB AS $$
DECLARE
    v_sub RECORD;
    v_result JSONB;
    v_plugin_config JSONB;
BEGIN
    -- Fetch subscription with plan and subscriber details
    SELECT
        sub.id AS subscription_id,
        sub.status,
        s.id AS subscriber_id,
        s.kong_consumer_id,
        p.name AS plan_name,
        p.rate_limit_per_second,
        p.rate_limit_per_minute,
        p.rate_limit_per_hour,
        p.rate_limit_per_day,
        p.rate_limit_per_month,
        p.monthly_quota,
        p.max_request_size_kb
    INTO v_sub
    FROM subscriptions sub
    JOIN subscribers s ON s.id = sub.subscriber_id
    JOIN plans p ON p.id = sub.plan_id
    WHERE sub.id = p_subscription_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Subscription % not found', p_subscription_id;
    END IF;

    IF v_sub.kong_consumer_id IS NULL THEN
        RAISE EXCEPTION 'Subscriber % has no Kong consumer', v_sub.subscriber_id;
    END IF;

    -- Build rate-limiting plugin config
    v_plugin_config := jsonb_build_object(
        'name', 'rate-limiting',
        'consumer', jsonb_build_object('id', v_sub.kong_consumer_id),
        'config', jsonb_strip_nulls(jsonb_build_object(
            'second', v_sub.rate_limit_per_second,
            'minute', v_sub.rate_limit_per_minute,
            'hour', v_sub.rate_limit_per_hour,
            'day', v_sub.rate_limit_per_day,
            'month', v_sub.rate_limit_per_month,
            'policy', 'redis',
            'fault_tolerant', true,
            'hide_client_headers', false,
            'error_code', 429,
            'error_message', 'Rate limit exceeded for plan: ' || v_sub.plan_name
        ))
    );

    -- Build request-size-limiting plugin config
    v_result := jsonb_build_object(
        'action', CASE
            WHEN v_sub.status = 'active' THEN 'upsert'
            ELSE 'delete'
        END,
        'kong_consumer_id', v_sub.kong_consumer_id,
        'subscriber_id', v_sub.subscriber_id::TEXT,
        'subscription_id', v_sub.subscription_id::TEXT,
        'plan', v_sub.plan_name,
        'plugins', jsonb_build_array(
            v_plugin_config,
            jsonb_build_object(
                'name', 'request-size-limiting',
                'consumer', jsonb_build_object('id', v_sub.kong_consumer_id),
                'config', jsonb_build_object(
                    'allowed_payload_size', v_sub.max_request_size_kb,
                    'size_unit', 'kilobytes'
                )
            )
        )
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
            'kong_key_id', ak.kong_key_id,
            'is_active', ak.is_active,
            'synced', ak.kong_key_id IS NOT NULL
        )
    ), '[]'::JSONB)
    INTO v_keys
    FROM api_keys ak
    WHERE ak.subscriber_id = p_subscriber_id
      AND ak.is_active = TRUE
      AND ak.revoked_at IS NULL;

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
