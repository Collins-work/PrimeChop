-- PrimeChop PostgreSQL schema
-- Paste this into Railway Postgres or run it through psql.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    full_name TEXT,
    role TEXT NOT NULL DEFAULT 'customer',
    wallet_balance BIGINT NOT NULL DEFAULT 0,
    waiter_online INTEGER NOT NULL DEFAULT 0,
    waiter_code TEXT,
    waiter_verified INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_waiter_code ON users(waiter_code);

CREATE TABLE IF NOT EXISTS waiter_registry (
    id BIGSERIAL PRIMARY KEY,
    telegram_user_id BIGINT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT,
    phone TEXT,
    gender TEXT,
    public_user_id TEXT UNIQUE,
    waiter_code TEXT UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    is_active INTEGER NOT NULL DEFAULT 1,
    waiter_online INTEGER NOT NULL DEFAULT 0,
    waiter_verified INTEGER NOT NULL DEFAULT 0,
    registration_details TEXT,
    deleted_at TIMESTAMPTZ,
    deleted_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waiter_registry_status ON waiter_registry(status);
CREATE INDEX IF NOT EXISTS idx_waiter_registry_is_active ON waiter_registry(is_active);
CREATE INDEX IF NOT EXISTS idx_waiter_registry_waiter_code ON waiter_registry(waiter_code);

CREATE TABLE IF NOT EXISTS waiter_registry_events (
    id BIGSERIAL PRIMARY KEY,
    waiter_registry_id BIGINT,
    telegram_user_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    event_note TEXT,
    snapshot JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waiter_registry_events_user_id ON waiter_registry_events(telegram_user_id);
CREATE INDEX IF NOT EXISTS idx_waiter_registry_events_created_at ON waiter_registry_events(created_at);

CREATE TABLE IF NOT EXISTS vendors (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS menu_items (
    id BIGSERIAL PRIMARY KEY,
    vendor_id BIGINT REFERENCES vendors(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    price BIGINT NOT NULL,
    meal_slot TEXT NOT NULL DEFAULT 'any',
    image_file_id TEXT,
    image_url TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    order_ref TEXT NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    item_id BIGINT NOT NULL,
    cafeteria_name TEXT NOT NULL,
    amount BIGINT NOT NULL,
    order_details TEXT,
    room_number TEXT,
    delivery_time TEXT,
    hall_name TEXT,
    status TEXT NOT NULL DEFAULT 'pending_payment',
    payment_method TEXT NOT NULL DEFAULT 'transfer',
    payment_provider TEXT NOT NULL DEFAULT 'korapay',
    payment_tx_ref TEXT,
    payment_link TEXT,
    customer_rating INTEGER,
    customer_feedback TEXT,
    rating_submitted_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    eta_minutes INTEGER,
    eta_due_at TIMESTAMPTZ,
    waiter_id BIGINT,
    service_fee_total BIGINT NOT NULL DEFAULT 0,
    waiter_share BIGINT NOT NULL DEFAULT 0,
    platform_share BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_waiter_id ON orders(waiter_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_tx_ref ON orders(payment_tx_ref);

CREATE TABLE IF NOT EXISTS order_events (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    order_ref TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_note TEXT,
    waiter_id BIGINT,
    waiter_name TEXT,
    eta_minutes INTEGER,
    eta_due_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_order_events_order_id ON order_events(order_id);
CREATE INDEX IF NOT EXISTS idx_order_events_order_ref ON order_events(order_ref);

CREATE TABLE IF NOT EXISTS wallet_transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    amount BIGINT NOT NULL,
    tx_type TEXT NOT NULL,
    tx_ref TEXT,
    payment_link TEXT,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_id ON wallet_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_tx_ref ON wallet_transactions(tx_ref);

CREATE TABLE IF NOT EXISTS waiter_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    public_user_id TEXT UNIQUE,
    full_name TEXT NOT NULL,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waiter_requests_status ON waiter_requests(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_waiter_requests_public_user_id ON waiter_requests(public_user_id);

CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION sync_waiter_registry_delete()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO waiter_registry_events (
        waiter_registry_id,
        telegram_user_id,
        event_type,
        event_note,
        snapshot,
        created_at
    ) VALUES (
        OLD.id,
        OLD.telegram_user_id,
        'deleted',
        COALESCE(OLD.deleted_reason, 'soft delete'),
        to_jsonb(OLD),
        NOW()
    );
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_users_touch_updated_at ON users;
CREATE TRIGGER trg_users_touch_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_waiter_registry_touch_updated_at ON waiter_registry;
CREATE TRIGGER trg_waiter_registry_touch_updated_at
BEFORE UPDATE ON waiter_registry
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_vendors_touch_updated_at ON vendors;
CREATE TRIGGER trg_vendors_touch_updated_at
BEFORE UPDATE ON vendors
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_menu_items_touch_updated_at ON menu_items;
CREATE TRIGGER trg_menu_items_touch_updated_at
BEFORE UPDATE ON menu_items
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_orders_touch_updated_at ON orders;
CREATE TRIGGER trg_orders_touch_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_wallet_transactions_touch_updated_at ON wallet_transactions;
CREATE TRIGGER trg_wallet_transactions_touch_updated_at
BEFORE UPDATE ON wallet_transactions
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_waiter_requests_touch_updated_at ON waiter_requests;
CREATE TRIGGER trg_waiter_requests_touch_updated_at
BEFORE UPDATE ON waiter_requests
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_waiter_registry_delete ON waiter_registry;
CREATE TRIGGER trg_waiter_registry_delete
AFTER UPDATE OF is_active, deleted_at ON waiter_registry
FOR EACH ROW
WHEN (OLD.is_active = 1 AND NEW.is_active = 0)
EXECUTE FUNCTION sync_waiter_registry_delete();

INSERT INTO waiter_registry (
    telegram_user_id,
    full_name,
    email,
    phone,
    gender,
    public_user_id,
    waiter_code,
    status,
    is_active,
    waiter_online,
    waiter_verified,
    registration_details,
    deleted_at,
    deleted_reason
)
SELECT
    wr.user_id,
    wr.full_name,
    NULL,
    NULL,
    NULL,
    wr.public_user_id,
    NULL,
    wr.status,
    FALSE,
    FALSE,
    FALSE,
    wr.details,
    CASE WHEN wr.status = 'rejected' THEN NOW() ELSE NULL END,
    CASE WHEN wr.status = 'rejected' THEN 'rejected request' ELSE NULL END
FROM waiter_requests wr
ON CONFLICT (telegram_user_id) DO NOTHING;
