-- PrimeChop minimal PostgreSQL schema for Railway console
-- Purpose: waiter registration + order tracking only

BEGIN;

CREATE TABLE IF NOT EXISTS waiter_requests (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE,
    public_user_id TEXT UNIQUE,
    full_name TEXT NOT NULL,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewed_by BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waiter_requests_user_id ON waiter_requests(user_id);
CREATE INDEX IF NOT EXISTS idx_waiter_requests_status ON waiter_requests(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_waiter_requests_public_user_id ON waiter_requests(public_user_id);

CREATE TABLE IF NOT EXISTS orders (
    id BIGSERIAL PRIMARY KEY,
    order_ref TEXT UNIQUE,
    customer_id BIGINT NOT NULL,
    item_id BIGINT NOT NULL,
    cafeteria_name TEXT NOT NULL,
    amount BIGINT NOT NULL,
    order_details TEXT,
    room_number TEXT,
    delivery_time TEXT,
    hall_name TEXT,
    status TEXT NOT NULL,
    payment_method TEXT DEFAULT 'transfer',
    payment_provider TEXT DEFAULT 'paystack',
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

CREATE INDEX IF NOT EXISTS idx_orders_order_ref ON orders(order_ref);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_waiter_id ON orders(waiter_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_orders_payment_tx_ref ON orders(payment_tx_ref);

CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_waiter_requests_touch_updated_at ON waiter_requests;
CREATE TRIGGER trg_waiter_requests_touch_updated_at
BEFORE UPDATE ON waiter_requests
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_orders_touch_updated_at ON orders;
CREATE TRIGGER trg_orders_touch_updated_at
BEFORE UPDATE ON orders
FOR EACH ROW EXECUTE FUNCTION touch_updated_at();

COMMIT;
