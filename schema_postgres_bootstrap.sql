-- PrimeChop PostgreSQL bootstrap schema (Railway-safe)
-- Use this first if full schema fails in console.

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

CREATE TABLE IF NOT EXISTS waiter_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    public_user_id TEXT UNIQUE,
    full_name TEXT NOT NULL,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by BIGINT,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waiter_requests_status ON waiter_requests(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_waiter_requests_public_user_id ON waiter_requests(public_user_id);

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

CREATE TABLE IF NOT EXISTS waiter_earning_adjustments (
    id BIGSERIAL PRIMARY KEY,
    waiter_user_id BIGINT NOT NULL REFERENCES users(user_id),
    amount BIGINT NOT NULL,
    reason TEXT,
    adjusted_by BIGINT NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waiter_earning_adjustments_waiter_id ON waiter_earning_adjustments(waiter_user_id);

CREATE TABLE IF NOT EXISTS customer_messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(user_id),
    user_name TEXT NOT NULL,
    message_text TEXT NOT NULL,
    message_type TEXT NOT NULL DEFAULT 'feedback',
    broadcast_context TEXT,
    admin_reply TEXT,
    admin_reply_by BIGINT REFERENCES users(user_id),
    status TEXT NOT NULL DEFAULT 'unread',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_customer_messages_user_id ON customer_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_customer_messages_status ON customer_messages(status);
CREATE INDEX IF NOT EXISTS idx_customer_messages_created_at ON customer_messages(created_at DESC);
