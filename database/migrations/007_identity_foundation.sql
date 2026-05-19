-- P9.1: Identity foundation — platform users, channel identities, auth event prep.

-- Extend app_users (backward-compatible: legacy role + telegram_user_id remain)
ALTER TABLE app_users
    ADD COLUMN IF NOT EXISTS email TEXT,
    ADD COLUMN IF NOT EXISTS password_hash TEXT,
    ADD COLUMN IF NOT EXISTS display_name TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active',
    ADD COLUMN IF NOT EXISTS platform_role TEXT NOT NULL DEFAULT 'end_user',
    ADD COLUMN IF NOT EXISTS retrieval_role TEXT NOT NULL DEFAULT 'employee',
    ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

ALTER TABLE app_users
    ALTER COLUMN telegram_user_id DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'app_users_status_check'
    ) THEN
        ALTER TABLE app_users
            ADD CONSTRAINT app_users_status_check
            CHECK (status IN ('active', 'suspended', 'deleted'));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'app_users_platform_role_check'
    ) THEN
        ALTER TABLE app_users
            ADD CONSTRAINT app_users_platform_role_check
            CHECK (platform_role IN (
                'end_user', 'employee', 'operator', 'admin', 'auditor', 'superadmin'
            ));
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'app_users_retrieval_role_check'
    ) THEN
        ALTER TABLE app_users
            ADD CONSTRAINT app_users_retrieval_role_check
            CHECK (retrieval_role IN ('guest', 'employee', 'admin'));
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_app_users_email
    ON app_users (LOWER(email))
    WHERE email IS NOT NULL AND email <> '';

CREATE INDEX IF NOT EXISTS idx_app_users_platform_role
    ON app_users (platform_role);

CREATE INDEX IF NOT EXISTS idx_app_users_status
    ON app_users (status);

-- Legacy role → platform_role (idempotent)
UPDATE app_users
SET platform_role = CASE
    WHEN role = 'admin' THEN 'admin'
    ELSE COALESCE(NULLIF(platform_role, ''), 'end_user')
END
WHERE platform_role = 'end_user' AND role IS NOT NULL;

UPDATE app_users
SET retrieval_role = CASE
    WHEN role = 'admin' OR platform_role = 'admin' THEN 'admin'
    ELSE COALESCE(NULLIF(retrieval_role, ''), 'employee')
END
WHERE retrieval_role = 'employee';

-- Channel identities (Telegram ≠ platform identity)
CREATE TABLE IF NOT EXISTS user_channel_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    external_user_id TEXT NOT NULL,
    external_chat_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel, external_user_id)
);

CREATE INDEX IF NOT EXISTS idx_user_channel_identities_user_id
    ON user_channel_identities (user_id);

CREATE INDEX IF NOT EXISTS idx_user_channel_identities_channel
    ON user_channel_identities (channel);

-- Backfill Telegram links from legacy app_users.telegram_user_id
INSERT INTO user_channel_identities (user_id, channel, external_user_id, external_chat_id)
SELECT
    id,
    'telegram',
    telegram_user_id::text,
    CASE WHEN telegram_chat_id IS NOT NULL THEN telegram_chat_id::text ELSE NULL END
FROM app_users
WHERE telegram_user_id IS NOT NULL
ON CONFLICT (channel, external_user_id) DO NOTHING;

-- Auth audit foundation (append-only usage in application code)
CREATE TABLE IF NOT EXISTS auth_login_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    auth_source TEXT,
    outcome TEXT NOT NULL CHECK (outcome IN ('success', 'failure')),
    actor_role TEXT,
    ip_hash TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auth_login_events_user_id
    ON auth_login_events (user_id);

CREATE INDEX IF NOT EXISTS idx_auth_login_events_created_at
    ON auth_login_events (created_at DESC);
