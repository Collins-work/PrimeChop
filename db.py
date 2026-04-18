import csv
import re
import os
import logging
import sqlite3
from pathlib import Path
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Iterable, Optional, Any

import psycopg
from psycopg import sql


logger = logging.getLogger(__name__)


class _CompatRow:
    """Wraps psycopg Row to provide dict-like access similar to sqlite3.Row"""
    def __init__(self, cursor_description, row_data):
        self._row = row_data
        self._cols = {desc[0]: i for i, desc in enumerate(cursor_description)} if cursor_description else {}

    def __getitem__(self, key):
        if isinstance(key, str):
            idx = self._cols.get(key)
            if idx is None:
                raise KeyError(key)
            return self._row[idx]
        return self._row[key]

    def __contains__(self, key):
        return key in self._cols

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default


class _CompatCursor:
    def __init__(self, inner_cursor):
        self._inner = inner_cursor
        self._lastrowid = None

    @property
    def rowcount(self):
        return self._inner.rowcount

    @property
    def lastrowid(self):
        return self._lastrowid

    @lastrowid.setter
    def lastrowid(self, value):
        self._lastrowid = value

    def fetchone(self):
        row = self._inner.fetchone()
        if row is None:
            return None
        return _CompatRow(self._inner.description, row)

    def fetchall(self):
        rows = self._inner.fetchall()
        return [_CompatRow(self._inner.description, row) for row in rows]


class _CompatConnection:
    def __init__(self, inner_connection):
        self._inner = inner_connection

    def execute(self, sql_str: str, params: tuple | list | None = None):
        cursor = self._inner.cursor()
        values = tuple(params) if params is not None else tuple()
        # Keep existing sqlite-style SQL compatible with psycopg.
        if params is not None and "?" in sql_str:
            sql_str = sql_str.replace("?", "%s")
        cursor.execute(sql_str, values)
        return _CompatCursor(cursor)

    def commit(self):
        self._inner.commit()

    def close(self):
        self._inner.close()


class Database:
    def __init__(self, database_url: str, timezone_name: str, allow_order_history_purge: bool = False):
        """
        Initialize database connection using PostgreSQL.
        
        Args:
            database_url: PostgreSQL connection string (e.g., postgresql://user:pass@host/dbname)
            timezone_name: Timezone name for timestamp operations
        """
        self._database_url = database_url
        if not database_url or not database_url.strip():
            raise ValueError("DATABASE_URL environment variable is required for PostgreSQL")
        
        self.tz = ZoneInfo(timezone_name)
        self._allow_order_history_purge = bool(allow_order_history_purge)
        self._human_exports_enabled = (os.getenv("HUMAN_READABLE_EXPORTS_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"})
        
        # Create human_readable export directory
        base_dir = Path.cwd()
        self._human_data_dir = base_dir / "human_readable"
        self._waiter_registry_export_path = self._human_data_dir / "waiter_registry.csv"
        self._orders_users_export_path = self._human_data_dir / "orders_users_tracker.csv"

    @contextmanager
    def connection(self):
        """Context manager for database connections using PostgreSQL"""
        conn = psycopg.connect(self._database_url)
        compat_conn = _CompatConnection(conn)
        try:
            yield compat_conn
            compat_conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            compat_conn.close()

    def now_iso(self) -> str:
        return datetime.now(self.tz).isoformat()

    def _refresh_waiter_registry_export(self):
        if not self._human_exports_enabled:
            return
        with self.connection() as conn:
            waiter_users = conn.execute(
                """
                SELECT
                    user_id,
                    full_name,
                    role,
                    waiter_online,
                    waiter_code,
                    waiter_verified,
                    created_at,
                    updated_at
                FROM users
                WHERE role='waiter' OR waiter_verified=1
                ORDER BY user_id ASC
                """
            ).fetchall()
            latest_requests = conn.execute(
                """
                SELECT
                    wr.user_id,
                    wr.public_user_id,
                    wr.full_name AS request_full_name,
                    wr.details AS registration_details,
                    wr.status AS request_status,
                    wr.created_at AS request_created_at,
                    wr.updated_at AS request_updated_at
                FROM waiter_requests wr
                WHERE wr.id = (
                    SELECT wr2.id
                    FROM waiter_requests wr2
                    WHERE wr2.user_id = wr.user_id
                    ORDER BY wr2.id DESC
                    LIMIT 1
                )
                ORDER BY wr.user_id ASC
                """
            ).fetchall()

        users_by_id: dict[int, dict] = {}
        for row in waiter_users:
            user_id = int(row["user_id"] or 0)
            users_by_id[user_id] = {
                "user_id": user_id,
                "full_name": row["full_name"] or "",
                "role": row["role"] or "",
                "waiter_online": int(row["waiter_online"] or 0),
                "waiter_code": row["waiter_code"] or "",
                "waiter_verified": int(row["waiter_verified"] or 0),
                "public_user_id": "",
                "request_status": "",
                "registration_details": "",
                "created_at": row["created_at"] or "",
                "updated_at": row["updated_at"] or "",
            }

        for request in latest_requests:
            user_id = int(request["user_id"] or 0)
            existing = users_by_id.get(user_id)
            if existing:
                existing["public_user_id"] = request["public_user_id"] or ""
                existing["request_status"] = request["request_status"] or ""
                existing["registration_details"] = request["registration_details"] or ""
            else:
                users_by_id[user_id] = {
                    "user_id": user_id,
                    "full_name": request["request_full_name"] or "",
                    "role": "pending_waiter",
                    "waiter_online": 0,
                    "waiter_code": "",
                    "waiter_verified": 0,
                    "public_user_id": request["public_user_id"] or "",
                    "request_status": request["request_status"] or "",
                    "registration_details": request["registration_details"] or "",
                    "created_at": request["request_created_at"] or "",
                    "updated_at": request["request_updated_at"] or "",
                }

        rows = sorted(
            users_by_id.values(),
            key=lambda row: (
                row.get("waiter_code") or "",
                row.get("public_user_id") or "",
                int(row.get("user_id") or 0),
            ),
        )

        self._human_data_dir.mkdir(parents=True, exist_ok=True)
        with self._waiter_registry_export_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "user_id",
                    "full_name",
                    "role",
                    "waiter_online",
                    "waiter_code",
                    "waiter_verified",
                    "public_waiter_id",
                    "request_status",
                    "registration_details",
                    "created_at",
                    "updated_at",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        int(row.get("user_id") or 0),
                        row.get("full_name") or "",
                        row.get("role") or "",
                        int(row.get("waiter_online") or 0),
                        row.get("waiter_code") or "",
                        int(row.get("waiter_verified") or 0),
                        row.get("public_user_id") or "",
                        row.get("request_status") or "",
                        row.get("registration_details") or "",
                        row.get("created_at") or "",
                        row.get("updated_at") or "",
                    ]
                )

    def _mirror_waiter_request_by_user_id(self, user_id: int):
        """
        Mirror latest waiter request/user state into optional waiter_registry table.
        This keeps compatibility with deployments that bootstrap the legacy table.
        """
        with self.connection() as conn:
            latest_request = conn.execute(
                """
                SELECT user_id, public_user_id, full_name, details, status, created_at, updated_at
                FROM waiter_requests
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            user_row = conn.execute(
                "SELECT user_id, full_name, waiter_code, waiter_online, waiter_verified, created_at, updated_at FROM users WHERE user_id=?",
                (user_id,),
            ).fetchone()

            if not latest_request and not user_row:
                return

            full_name = ""
            public_user_id = ""
            registration_details = ""
            status = "pending"
            created_at = self.now_iso()
            updated_at = self.now_iso()
            waiter_code = ""
            waiter_online = 0
            waiter_verified = 0
            is_active = 1

            if latest_request:
                full_name = latest_request["full_name"] or ""
                public_user_id = latest_request["public_user_id"] or ""
                registration_details = latest_request["details"] or ""
                status = latest_request["status"] or "pending"
                created_at = latest_request["created_at"] or created_at
                updated_at = latest_request["updated_at"] or updated_at

            if user_row:
                full_name = user_row["full_name"] or full_name
                waiter_code = user_row["waiter_code"] or ""
                waiter_online = int(user_row["waiter_online"] or 0)
                waiter_verified = int(user_row["waiter_verified"] or 0)
                created_at = user_row["created_at"] or created_at
                updated_at = user_row["updated_at"] or updated_at
                if waiter_verified:
                    status = "approved"

            if status == "deleted":
                is_active = 0

            parsed_email = ""
            parsed_phone = ""
            parsed_gender = ""
            for line in registration_details.splitlines():
                lower = line.lower()
                if lower.startswith("email:"):
                    parsed_email = line.split(":", 1)[1].strip()
                elif lower.startswith("phone:"):
                    parsed_phone = line.split(":", 1)[1].strip()
                elif lower.startswith("gender:"):
                    parsed_gender = line.split(":", 1)[1].strip()

            # The waiter_registry table is optional; update it only if it exists.
            table_exists = conn.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='waiter_registry' LIMIT 1"
            ).fetchone()
            if not table_exists:
                return

            conn.execute(
                """
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
                    created_at,
                    updated_at,
                    deleted_at,
                    deleted_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CASE WHEN ?='deleted' THEN ? ELSE NULL END, CASE WHEN ?='deleted' THEN 'waiter removed by admin' ELSE NULL END)
                ON CONFLICT (telegram_user_id) DO UPDATE SET
                    full_name=EXCLUDED.full_name,
                    email=EXCLUDED.email,
                    phone=EXCLUDED.phone,
                    gender=EXCLUDED.gender,
                    public_user_id=EXCLUDED.public_user_id,
                    waiter_code=EXCLUDED.waiter_code,
                    status=EXCLUDED.status,
                    is_active=EXCLUDED.is_active,
                    waiter_online=EXCLUDED.waiter_online,
                    waiter_verified=EXCLUDED.waiter_verified,
                    registration_details=EXCLUDED.registration_details,
                    updated_at=EXCLUDED.updated_at,
                    deleted_at=EXCLUDED.deleted_at,
                    deleted_reason=EXCLUDED.deleted_reason
                """,
                (
                    user_id,
                    full_name,
                    parsed_email,
                    parsed_phone,
                    parsed_gender,
                    public_user_id or None,
                    waiter_code or None,
                    status,
                    is_active,
                    waiter_online,
                    waiter_verified,
                    registration_details,
                    created_at,
                    updated_at,
                    status,
                    updated_at,
                    status,
                ),
            )

    def _refresh_orders_users_export(self):
        if not self._human_exports_enabled:
            return
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    o.id,
                    o.order_ref,
                    o.order_details,
                    o.amount,
                    o.service_fee_total,
                    o.waiter_share,
                    o.platform_share,
                    o.status,
                    o.hall_name,
                    o.room_number,
                    o.payment_method,
                    o.payment_provider,
                    o.payment_tx_ref,
                    o.created_at,
                    o.accepted_at,
                    o.completed_at,
                    o.eta_minutes,
                    o.eta_due_at,
                    c.user_id AS customer_id,
                    c.full_name AS customer_name,
                    w.user_id AS waiter_id,
                    w.full_name AS waiter_name,
                    w.waiter_code AS waiter_code,
                    m.name AS item_name
                FROM orders o
                LEFT JOIN users c ON c.user_id = o.customer_id
                LEFT JOIN users w ON w.user_id = o.waiter_id
                LEFT JOIN menu_items m ON m.id = o.item_id
                ORDER BY o.id DESC
                """
            ).fetchall()

        self._human_data_dir.mkdir(parents=True, exist_ok=True)
        with self._orders_users_export_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "order_id",
                    "order_ref",
                    "item_name",
                    "order_details",
                    "amount",
                    "service_fee_total",
                    "waiter_share",
                    "platform_share",
                    "status",
                    "customer_id",
                    "customer_name",
                    "waiter_id",
                    "waiter_name",
                    "waiter_code",
                    "hall_name",
                    "room_number",
                    "payment_method",
                    "payment_provider",
                    "payment_tx_ref",
                    "created_at",
                    "accepted_at",
                    "completed_at",
                    "eta_minutes",
                    "eta_due_at",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        int(row["id"] or 0),
                        row["order_ref"] or "",
                        row["item_name"] or "",
                        row["order_details"] or "",
                        int(row["amount"] or 0),
                        int(row["service_fee_total"] or 0),
                        int(row["waiter_share"] or 0),
                        int(row["platform_share"] or 0),
                        row["status"] or "",
                        int(row["customer_id"] or 0),
                        row["customer_name"] or "",
                        int(row["waiter_id"] or 0) if row["waiter_id"] is not None else "",
                        row["waiter_name"] or "",
                        row["waiter_code"] or "",
                        row["hall_name"] or "",
                        row["room_number"] or "",
                        row["payment_method"] or "",
                        row["payment_provider"] or "",
                        row["payment_tx_ref"] or "",
                        row["created_at"] or "",
                        row["accepted_at"] or "",
                        row["completed_at"] or "",
                        int(row["eta_minutes"] or 0) if row["eta_minutes"] is not None else "",
                        row["eta_due_at"] or "",
                    ]
                )

    def _mirror_order_by_id(self, order_id: int):
        """Compatibility hook for legacy mirror flows.

        Some call sites expect this method to exist after creating/updating orders.
        For PostgreSQL deployments we already export order state to the human-readable
        tracker, so this hook safely refreshes that export and avoids runtime crashes.
        """
        _ = order_id
        self._refresh_orders_users_export()

    def refresh_human_readable_exports(self):
        if not self._human_exports_enabled:
            return
        self._refresh_waiter_registry_export()
        self._refresh_orders_users_export()

    def _normalize_vendor_name(self, name: str) -> str:
        text = (name or "").strip()
        if not text:
            return ""

        # Keep only the name part before first phone number-like sequence.
        first_number = re.search(r"\d{7,}", text)
        if first_number:
            text = text[:first_number.start()]

        text = re.sub(r"[\s,\-:;]+$", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _infer_meal_slot(self, item_name: str) -> str:
        name = (item_name or "").strip().lower()
        if not name:
            return "any"

        breakfast_keywords = ("egg", "bread", "tea", "coffee", "porridge", "oats", "yam", "akara", "moi moi", "sandwich")
        lunch_keywords = ("rice", "jollof", "fried rice", "pasta", "spaghetti", "beans", "soup", "plantain", "chicken", "beef", "fish")
        dinner_keywords = ("noodles", "shawarma", "burger", "pizza", "salad", "snack", "chicken", "soup", "rice")
        late_night_keywords = ("noodles", "snack", "burger", "shawarma", "pizza", "tea", "sandwich")

        if any(keyword in name for keyword in breakfast_keywords):
            return "breakfast"
        if any(keyword in name for keyword in late_night_keywords):
            return "late-night"
        if any(keyword in name for keyword in lunch_keywords):
            return "lunch"
        if any(keyword in name for keyword in dinner_keywords):
            return "dinner"
        return "any"

    def _normalize_meal_slot(self, meal_slot: str | None, item_name: str = "") -> str:
        value = (meal_slot or "").strip().lower().replace("_", "-")
        aliases = {
            "breakfast": "breakfast",
            "morning": "breakfast",
            "lunch": "lunch",
            "afternoon": "lunch",
            "dinner": "dinner",
            "evening": "dinner",
            "late-night": "late-night",
            "latenight": "late-night",
            "night": "late-night",
            "any": "any",
            "all": "any",
            "anytime": "any",
        }
        normalized = aliases.get(value)
        if normalized:
            return normalized
        return self._infer_meal_slot(item_name)

    def _normalize_existing_vendors(self, conn):
        """PostgreSQL version - no-op since schema is properly created"""
        pass

    def _ensure_order_columns(self, conn):
        """PostgreSQL version - no-op since schema is properly created"""
        pass

    def _ensure_vendor_columns(self, conn):
        """PostgreSQL version - no-op since schema is properly created"""
        pass

    def _ensure_user_columns(self, conn):
        """PostgreSQL version - no-op since schema is properly created"""
        pass

    def _ensure_waiter_request_columns(self, conn):
        """PostgreSQL version - no-op since schema is properly created"""
        pass

    def init(self):
        """Initialize PostgreSQL database schema"""
        with self.connection() as conn:
            # Create tables
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    full_name TEXT,
                    role TEXT DEFAULT 'customer',
                    wallet_balance INTEGER DEFAULT 0,
                    waiter_online INTEGER DEFAULT 0,
                    waiter_code TEXT UNIQUE,
                    waiter_verified INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vendors (
                    id SERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS menu_items (
                    id SERIAL PRIMARY KEY,
                    vendor_id INTEGER,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    meal_slot TEXT DEFAULT 'any',
                    image_file_id TEXT,
                    image_url TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (vendor_id) REFERENCES vendors(id)
                )
                """
            )
            
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    order_ref TEXT UNIQUE,
                    customer_id BIGINT NOT NULL,
                    item_id INTEGER NOT NULL,
                    cafeteria_name TEXT NOT NULL,
                    amount INTEGER NOT NULL,
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
                    rating_submitted_at TEXT,
                    accepted_at TEXT,
                    completed_at TEXT,
                    eta_minutes INTEGER,
                    eta_due_at TEXT,
                    waiter_id BIGINT,
                    service_fee_total INTEGER NOT NULL,
                    waiter_share INTEGER NOT NULL,
                    platform_share INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (customer_id) REFERENCES users(user_id),
                    FOREIGN KEY (item_id) REFERENCES menu_items(id),
                    FOREIGN KEY (waiter_id) REFERENCES users(user_id)
                )
                """
            )
            
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS wallet_transactions (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    amount INTEGER NOT NULL,
                    tx_type TEXT NOT NULL,
                    tx_ref TEXT,
                    payment_link TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
                """
            )
            
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS waiter_requests (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    public_user_id TEXT UNIQUE,
                    full_name TEXT NOT NULL,
                    details TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    reviewed_by BIGINT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (reviewed_by) REFERENCES users(user_id)
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS waiter_earning_adjustments (
                    id SERIAL PRIMARY KEY,
                    waiter_user_id BIGINT NOT NULL,
                    amount INTEGER NOT NULL,
                    reason TEXT,
                    adjusted_by BIGINT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (waiter_user_id) REFERENCES users(user_id),
                    FOREIGN KEY (adjusted_by) REFERENCES users(user_id)
                )
                """
            )
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_waiter_id ON orders(waiter_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_order_ref ON orders(order_ref)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user_id ON wallet_transactions(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_wallet_transactions_tx_ref ON wallet_transactions(tx_ref)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_waiter_requests_user_id ON waiter_requests(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_waiter_requests_status ON waiter_requests(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_waiter_earning_adjustments_waiter_id ON waiter_earning_adjustments(waiter_user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_users_waiter_code ON users(waiter_code)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_menu_items_vendor_id ON menu_items(vendor_id)")
            
        self.refresh_human_readable_exports()

    def seed_vendors(self, vendor_names: Iterable[str]):
        now = self.now_iso()
        cleaned_names = []
        for name in vendor_names:
            normalized = self._normalize_vendor_name(name)
            if normalized and normalized not in cleaned_names:
                cleaned_names.append(normalized)

        with self.connection() as conn:
            for name in cleaned_names:
                conn.execute(
                    """
                    INSERT INTO vendors (name, active, created_at, updated_at)
                    VALUES (?, 1, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        active=1,
                        updated_at=excluded.updated_at
                    """,
                    (name, now, now),
                )

    def upsert_vendor(self, name: str) -> sqlite3.Row:
        now = self.now_iso()
        cleaned = self._normalize_vendor_name(name)
        if not cleaned:
            raise ValueError("Vendor name is required")
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO vendors (name, active, created_at, updated_at)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    active=1,
                    updated_at=excluded.updated_at
                """,
                (cleaned, now, now),
            )
            return conn.execute("SELECT * FROM vendors WHERE name=?", (cleaned,)).fetchone()

    def list_vendors(self) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT * FROM vendors WHERE active=1 ORDER BY id ASC"
            ).fetchall()

    def list_vendors_with_active_items(self) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT v.*
                FROM vendors v
                WHERE v.active=1
                  AND EXISTS (
                      SELECT 1
                      FROM menu_items m
                      WHERE m.vendor_id = v.id AND m.active=1
                  )
                ORDER BY v.id ASC
                """
            ).fetchall()

    def get_vendor(self, vendor_id: int) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM vendors WHERE id=? AND active=1", (vendor_id,)).fetchone()

    def get_vendor_by_name(self, name: str) -> Optional[sqlite3.Row]:
        cleaned = self._normalize_vendor_name(name)
        if not cleaned:
            return None
        with self.connection() as conn:
            return conn.execute("SELECT * FROM vendors WHERE name=? AND active=1", (cleaned,)).fetchone()

    def upsert_user(self, user_id: int, full_name: str, role: str = "customer"):
        now = self.now_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO users (user_id, full_name, role, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name=excluded.full_name,
                    role=CASE WHEN users.role = 'admin' THEN users.role ELSE excluded.role END,
                    updated_at=excluded.updated_at
                """,
                (user_id, full_name, role, now, now),
            )
            self._refresh_waiter_registry_export()

    def set_role(self, user_id: int, role: str):
        now = self.now_iso()
        with self.connection() as conn:
            conn.execute(
                "UPDATE users SET role=?, updated_at=? WHERE user_id=?",
                (role, now, user_id),
            )
        self._refresh_waiter_registry_export()

    def set_waiter_online(self, user_id: int, online: bool):
        now = self.now_iso()
        with self.connection() as conn:
            conn.execute(
                "UPDATE users SET waiter_online=?, updated_at=? WHERE user_id=?",
                (1 if online else 0, now, user_id),
            )
        self._refresh_waiter_registry_export()

    def assign_waiter_invite(self, user_id: int, full_name: str, waiter_code: str):
        now = self.now_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    user_id, full_name, role, waiter_online, waiter_code, waiter_verified, created_at, updated_at
                ) VALUES (?, ?, 'customer', 0, ?, 1, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name=excluded.full_name,
                    waiter_code=excluded.waiter_code,
                    waiter_verified=1,
                    updated_at=excluded.updated_at
                """,
                (user_id, full_name, waiter_code, now, now),
            )
            self._refresh_waiter_registry_export()

    def list_waiters(self, limit: int = 50) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT user_id, full_name, role, waiter_online, waiter_code, waiter_verified, updated_at
                FROM users
                WHERE role='waiter' OR waiter_verified=1
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def deactivate_waiter(self, identifier: str) -> Optional[sqlite3.Row]:
        now = self.now_iso()
        with self.connection() as conn:
            if identifier.isdigit():
                row = conn.execute(
                    "SELECT * FROM users WHERE user_id=? LIMIT 1",
                    (int(identifier),),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM users WHERE waiter_code=? LIMIT 1",
                    (identifier.upper(),),
                ).fetchone()

            if not row:
                return None

            conn.execute(
                """
                INSERT INTO waiter_requests (
                    user_id, public_user_id, full_name, details, status, reviewed_by, created_at, updated_at
                )
                VALUES (?, NULL, ?, 'waiter removed by admin', 'deleted', NULL, ?, ?)
                """,
                (int(row["user_id"]), row["full_name"] or "", now, now),
            )
            conn.execute("DELETE FROM users WHERE user_id=?", (row["user_id"],))
        self._refresh_waiter_registry_export()
        self._mirror_waiter_request_by_user_id(int(row["user_id"]))
        return row

    def waiter_performance(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT
                    u.user_id,
                    u.full_name,
                    u.waiter_code,
                    SUM(CASE WHEN o.status='completed' THEN 1 ELSE 0 END) AS completed_orders,
                    SUM(CASE WHEN o.status='claimed' THEN 1 ELSE 0 END) AS active_orders,
                    COALESCE(a.adjustment_total, 0) AS manual_adjustments,
                    SUM(CASE WHEN o.status='completed' THEN 250 ELSE 0 END) + COALESCE(a.adjustment_total, 0) AS earnings
                FROM users u
                LEFT JOIN orders o ON o.waiter_id = u.user_id
                LEFT JOIN (
                    SELECT waiter_user_id, SUM(amount) AS adjustment_total
                    FROM waiter_earning_adjustments
                    GROUP BY waiter_user_id
                ) a ON a.waiter_user_id = u.user_id
                WHERE u.role='waiter' OR u.waiter_verified=1
                GROUP BY u.user_id, u.full_name, u.waiter_code, a.adjustment_total
                ORDER BY completed_orders DESC, earnings DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def add_waiter_earning_adjustment(
        self,
        waiter_user_id: int,
        amount: int,
        adjusted_by: int,
        reason: str = "manual correction",
    ) -> int:
        now = self.now_iso()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO waiter_earning_adjustments (
                    waiter_user_id, amount, reason, adjusted_by, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                RETURNING id
                """,
                (waiter_user_id, amount, reason, adjusted_by, now),
            )
            row = cursor.fetchone()
            return int(row["id"]) if row else 0

    def waiter_public_user_id_exists(self, public_user_id: str) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM waiter_requests WHERE public_user_id=? LIMIT 1",
                (public_user_id,),
            ).fetchone()
            return row is not None

    def create_or_update_waiter_request(
        self,
        user_id: int,
        public_user_id: str,
        full_name: str,
        details: str,
    ) -> sqlite3.Row:
        now = self.now_iso()
        with self.connection() as conn:
            existing = conn.execute(
                "SELECT id, public_user_id FROM waiter_requests WHERE user_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            if existing:
                resolved_public_id = existing["public_user_id"] or public_user_id
                conn.execute(
                    """
                    UPDATE waiter_requests
                    SET full_name=?, details=?, public_user_id=?, updated_at=?
                    WHERE id=?
                    """,
                    (full_name, details, resolved_public_id, now, existing["id"]),
                )
                updated = conn.execute(
                    "SELECT * FROM waiter_requests WHERE id=?",
                    (existing["id"],),
                ).fetchone()
                self._refresh_waiter_registry_export()
                self._mirror_waiter_request_by_user_id(int(user_id))
                return updated

            cursor = conn.execute(
                """
                INSERT INTO waiter_requests (
                    user_id, public_user_id, full_name, details, status, reviewed_by, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'pending', NULL, ?, ?)
                RETURNING id
                """,
                (user_id, public_user_id, full_name, details, now, now),
            )
            inserted_row = cursor.fetchone()
            created = conn.execute(
                "SELECT * FROM waiter_requests WHERE id=?",
                (int(inserted_row["id"]),),
            ).fetchone()
            self._refresh_waiter_registry_export()
            self._mirror_waiter_request_by_user_id(int(user_id))
            return created

    def list_pending_waiter_requests(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT id, user_id, public_user_id, full_name, details, status, created_at
                FROM waiter_requests
                WHERE status='pending'
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def get_latest_waiter_request(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT *
                FROM waiter_requests
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()

    def approve_waiter_request(
        self,
        request_id: int,
        admin_user_id: int,
        waiter_code: str,
    ) -> Optional[sqlite3.Row]:
        now = self.now_iso()
        with self.connection() as conn:
            request = conn.execute(
                "SELECT * FROM waiter_requests WHERE id=? AND status='pending'",
                (request_id,),
            ).fetchone()
            if not request:
                return None

            conn.execute(
                """
                UPDATE waiter_requests
                SET status='approved', reviewed_by=?, updated_at=?
                WHERE id=?
                """,
                (admin_user_id, now, request_id),
            )
            conn.execute(
                """
                INSERT INTO users (user_id, full_name, role, waiter_online, created_at, updated_at)
                VALUES (?, ?, 'customer', 0, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    full_name=excluded.full_name,
                    waiter_code=?,
                    waiter_verified=1,
                    updated_at=excluded.updated_at
                """,
                (request["user_id"], request["full_name"], now, now, waiter_code),
            )

            conn.execute(
                """
                UPDATE users
                SET waiter_code=?, waiter_verified=1, updated_at=?
                WHERE user_id=?
                """,
                (waiter_code, now, request["user_id"]),
            )

            updated = conn.execute(
                "SELECT * FROM waiter_requests WHERE id=?",
                (request_id,),
            ).fetchone()
        self._refresh_waiter_registry_export()
        self._mirror_waiter_request_by_user_id(int(request["user_id"]))
        return updated

    def reject_waiter_request(self, request_id: int, admin_user_id: int) -> Optional[sqlite3.Row]:
        now = self.now_iso()
        with self.connection() as conn:
            request = conn.execute(
                "SELECT * FROM waiter_requests WHERE id=? AND status='pending'",
                (request_id,),
            ).fetchone()
            if not request:
                return None

            conn.execute(
                """
                UPDATE waiter_requests
                SET status='rejected', reviewed_by=?, updated_at=?
                WHERE id=?
                """,
                (admin_user_id, now, request_id),
            )
            updated = conn.execute(
                "SELECT * FROM waiter_requests WHERE id=?",
                (request_id,),
            ).fetchone()
        self._refresh_waiter_registry_export()
        self._mirror_waiter_request_by_user_id(int(request["user_id"]))
        return updated

    def get_online_waiters(self, allowed_waiter_ids: set[int]) -> Iterable[sqlite3.Row]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM users WHERE waiter_online=1 AND role='waiter' AND waiter_verified=1"
            ).fetchall()
            return rows

    def get_user(self, user_id: int) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()

    def list_user_ids(self) -> list[int]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT user_id FROM users ORDER BY user_id ASC"
            ).fetchall()
        return [int(row["user_id"]) for row in rows]

    def get_user_by_waiter_code(self, waiter_code: str) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE waiter_code=?",
                (waiter_code,),
            ).fetchone()

    def waiter_code_exists(self, waiter_code: str) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM users WHERE waiter_code=? LIMIT 1",
                (waiter_code,),
            ).fetchone()
            return row is not None

    def activate_waiter_by_code(self, user_id: int, waiter_code: str) -> bool:
        now = self.now_iso()
        with self.connection() as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM users
                WHERE user_id=? AND waiter_code=? AND waiter_verified=1
                LIMIT 1
                """,
                (user_id, waiter_code),
            ).fetchone()
            if not row:
                return False

            conn.execute(
                """
                UPDATE users
                SET role='waiter', waiter_online=1, updated_at=?
                WHERE user_id=?
                """,
                (now, user_id),
            )
        self._refresh_waiter_registry_export()
        return True

    def add_menu_item(
        self,
        vendor_id: int,
        name: str,
        price: int,
        image_file_id: str | None,
        image_url: str | None,
        meal_slot: str | None = None,
    ):
        now = self.now_iso()
        normalized_slot = self._normalize_meal_slot(meal_slot, name)
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO menu_items (vendor_id, name, price, meal_slot, image_file_id, image_url, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
                """,
                (vendor_id, name, price, normalized_slot, image_file_id, image_url, now, now),
            )
            inserted = cursor.fetchone()
            return int(inserted["id"])

    def sync_vendor_menu(
        self,
        vendor_id: int,
        items: Iterable[tuple[str, int]],
        default_image_url: str | None = None,
    ):
        now = self.now_iso()

        seen: set[tuple[str, int]] = set()
        normalized_items: list[tuple[str, int]] = []
        for name, price in items:
            clean_name = (name or "").strip()
            if not clean_name:
                continue
            clean_price = int(price)
            if clean_price <= 0:
                continue
            key = (clean_name.casefold(), clean_price)
            if key in seen:
                continue
            seen.add(key)
            normalized_items.append((clean_name, clean_price))

        with self.connection() as conn:
            conn.execute(
                "UPDATE menu_items SET active=0, updated_at=? WHERE vendor_id=?",
                (now, vendor_id),
            )

            for name, price in normalized_items:
                existing = conn.execute(
                    "SELECT id, image_file_id FROM menu_items WHERE vendor_id=? AND lower(name)=lower(?) AND price=? ORDER BY id DESC LIMIT 1",
                    (vendor_id, name, price),
                ).fetchone()

                if existing:
                    inferred_slot = self._infer_meal_slot(name)
                    conn.execute(
                        """
                        UPDATE menu_items
                        SET active=1,
                            image_url=COALESCE(image_url, ?),
                            meal_slot=COALESCE(NULLIF(meal_slot, ''), ?),
                            updated_at=?
                        WHERE id=?
                        """,
                        (default_image_url, inferred_slot, now, existing["id"]),
                    )
                    continue

                inferred_slot = self._infer_meal_slot(name)
                conn.execute(
                    """
                    INSERT INTO menu_items (vendor_id, name, price, meal_slot, image_file_id, image_url, active, created_at, updated_at)
                    VALUES (?, ?, ?, ?, NULL, ?, 1, ?, ?)
                    """,
                    (vendor_id, name, price, inferred_slot, default_image_url, now, now),
                )

    def list_menu_items(self) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM menu_items WHERE active=1 ORDER BY id ASC").fetchall()

    def list_menu_items_with_vendor(self) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT m.*, COALESCE(v.name, 'Unknown') AS vendor_name
                FROM menu_items m
                LEFT JOIN vendors v ON v.id = m.vendor_id
                WHERE m.active=1
                ORDER BY m.id ASC
                """
            ).fetchall()

    def list_menu_items_by_vendor(self, vendor_id: int) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT * FROM menu_items WHERE active=1 AND vendor_id=? ORDER BY id ASC",
                (vendor_id,),
            ).fetchall()

    def count_active_items_for_vendor(self, vendor_id: int) -> int:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM menu_items WHERE active=1 AND vendor_id=?",
                (vendor_id,),
            ).fetchone()
            return int(row["count"] or 0) if row else 0

    def assign_unassigned_menu_items(self, vendor_id: int):
        now = self.now_iso()
        with self.connection() as conn:
            conn.execute(
                "UPDATE menu_items SET vendor_id=?, updated_at=? WHERE vendor_id IS NULL",
                (vendor_id, now),
            )

    def get_menu_item(self, item_id: int) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM menu_items WHERE id=?", (item_id,)).fetchone()

    def deactivate_menu_item(self, item_id: int) -> bool:
        """Soft delete a menu item (set active=0)."""
        now = self.now_iso()
        with self.connection() as conn:
            cursor = conn.execute(
                "UPDATE menu_items SET active=0, updated_at=? WHERE id=?",
                (now, item_id),
            )
            return cursor.rowcount > 0

    def delete_menu_item(self, item_id: int) -> bool:
        """Hard delete a menu item from database."""
        with self.connection() as conn:
            cursor = conn.execute("DELETE FROM menu_items WHERE id=?", (item_id,))
            return cursor.rowcount > 0

    def update_menu_item(self, item_id: int, **kwargs) -> bool:
        """Update menu item fields. Supported: name, price, meal_slot, vendor_id, image_url, image_file_id, active."""
        allowed_fields = {"name", "price", "meal_slot", "vendor_id", "image_url", "image_file_id", "active"}
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False

        if "meal_slot" in updates:
            normalized_name = str(updates.get("name") or "")
            if not normalized_name:
                existing_item = self.get_menu_item(item_id)
                normalized_name = (existing_item["name"] if existing_item else "")
            updates["meal_slot"] = self._normalize_meal_slot(str(updates.get("meal_slot") or ""), normalized_name)

        now = self.now_iso()
        updates["updated_at"] = now

        set_clause = ", ".join(f"{k}=?" for k in updates.keys())
        values = list(updates.values()) + [item_id]

        with self.connection() as conn:
            cursor = conn.execute(
                f"UPDATE menu_items SET {set_clause} WHERE id=?",
                values,
            )
            return cursor.rowcount > 0

    def rename_vendor(self, vendor_id: int, new_name: str) -> Optional[sqlite3.Row]:
        cleaned_name = self._normalize_vendor_name(new_name)
        if not cleaned_name:
            raise ValueError("Vendor name is required")

        now = self.now_iso()
        with self.connection() as conn:
            vendor = conn.execute(
                "SELECT * FROM vendors WHERE id=? AND active=1",
                (vendor_id,),
            ).fetchone()
            if not vendor:
                return None

            existing = conn.execute(
                "SELECT * FROM vendors WHERE name=? AND id<>? LIMIT 1",
                (cleaned_name, vendor_id),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE menu_items SET vendor_id=?, updated_at=? WHERE vendor_id=?",
                    (existing["id"], now, vendor_id),
                )
                conn.execute(
                    "UPDATE vendors SET active=1, updated_at=? WHERE id=?",
                    (now, existing["id"]),
                )
                conn.execute(
                    "UPDATE vendors SET active=0, updated_at=? WHERE id=?",
                    (now, vendor_id),
                )
                return conn.execute(
                    "SELECT * FROM vendors WHERE id=?",
                    (existing["id"],),
                ).fetchone()

            conn.execute(
                "UPDATE vendors SET name=?, updated_at=? WHERE id=?",
                (cleaned_name, now, vendor_id),
            )
            return conn.execute(
                "SELECT * FROM vendors WHERE id=?",
                (vendor_id,),
            ).fetchone()

    def create_order(
        self,
        order_ref: str,
        customer_id: int,
        item_id: int,
        cafeteria_name: str,
        amount: int,
        order_details: str,
        room_number: str,
        delivery_time: str,
        hall_name: str,
        status: str,
        service_fee_total: int,
        waiter_share: int,
        platform_share: int,
        payment_method: str = "transfer",
        payment_provider: str = "paystack",
        payment_tx_ref: str | None = None,
        payment_link: str | None = None,
    ) -> int:
        now = self.now_iso()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO orders (
                    order_ref, customer_id, item_id, cafeteria_name, amount,
                    order_details, room_number, delivery_time, hall_name, status, payment_method, payment_provider, payment_tx_ref, payment_link, waiter_id,
                    service_fee_total, waiter_share, platform_share, accepted_at, completed_at, eta_minutes, eta_due_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
                RETURNING id
                """,
                (
                    order_ref,
                    customer_id,
                    item_id,
                    cafeteria_name,
                    amount,
                    order_details,
                    room_number,
                    delivery_time,
                    hall_name,
                    status,
                    payment_method,
                    payment_provider,
                    payment_tx_ref,
                    payment_link,
                    service_fee_total,
                    waiter_share,
                    platform_share,
                    now,
                    now,
                ),
            )
            inserted = cursor.fetchone()
        self._refresh_orders_users_export()
        order_id = int(inserted["id"])
        self._mirror_order_by_id(order_id)
        return order_id

    def get_order(self, order_id: int) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()

    def get_order_by_ref(self, order_ref: str) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM orders WHERE order_ref=?", (order_ref,)).fetchone()

    def get_order_by_payment_ref(self, tx_ref: str) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM orders WHERE payment_tx_ref=?", (tx_ref,)).fetchone()

    def order_ref_exists(self, order_ref: str) -> bool:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM orders WHERE order_ref=? LIMIT 1",
                (order_ref,),
            ).fetchone()
            return row is not None

    def list_customer_orders(self, customer_id: int, limit: int = 10) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT
                    o.id,
                    o.order_ref,
                    o.item_id,
                    o.amount,
                    o.order_details,
                    o.room_number,
                    o.hall_name,
                    o.delivery_time,
                    o.payment_method,
                    o.payment_provider,
                    o.payment_tx_ref,
                    o.payment_link,
                    o.status,
                    m.name AS item_name,
                    o.created_at
                FROM orders o
                LEFT JOIN menu_items m ON m.id = o.item_id
                WHERE o.customer_id=?
                ORDER BY o.id DESC
                LIMIT ?
                """,
                (customer_id, limit),
            ).fetchall()

    def list_customer_active_orders(self, customer_id: int, limit: int | None = None) -> list[sqlite3.Row]:
        query = """
            SELECT
                o.id,
                o.order_ref,
                o.item_id,
                o.amount,
                o.order_details,
                o.room_number,
                o.hall_name,
                o.delivery_time,
                o.payment_method,
                o.payment_provider,
                o.payment_tx_ref,
                o.payment_link,
                o.status,
                m.name AS item_name,
                o.created_at
            FROM orders o
            LEFT JOIN menu_items m ON m.id = o.item_id
            WHERE o.customer_id=? AND o.status IN ('pending_payment', 'pending_waiter', 'claimed')
            ORDER BY o.id DESC
        """
        params: tuple[int, ...] | tuple[int, int]
        params = (customer_id,)
        if limit is not None:
            query += "\nLIMIT ?"
            params = (customer_id, limit)

        with self.connection() as conn:
            return conn.execute(query, params).fetchall()

    def clear_customer_pending_cart_orders(self, customer_id: int) -> int:
        """Cancel unpaid cart orders for a customer and return affected count."""
        now = self.now_iso()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE orders
                SET status='cancelled', updated_at=?
                WHERE customer_id=? AND status='pending_payment'
                """,
                (now, customer_id),
            )
            return int(cursor.rowcount or 0)

    def list_customer_top_picks(self, customer_id: int, limit: int = 5) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT
                    o.item_id,
                    COALESCE(m.name, 'Unknown item') AS name,
                    COALESCE(v.name, 'Unknown vendor') AS vendor_name,
                    COALESCE(m.price, 0) AS price,
                    COUNT(*) AS order_count,
                    MAX(o.created_at) AS latest_order_at
                FROM orders o
                LEFT JOIN menu_items m ON m.id = o.item_id
                LEFT JOIN vendors v ON v.id = m.vendor_id
                WHERE o.customer_id=?
                  AND COALESCE(o.status, '') NOT IN ('cancelled', 'canceled')
                GROUP BY o.item_id, m.name, v.name, m.price
                ORDER BY order_count DESC, latest_order_at DESC, name ASC
                LIMIT ?
                """,
                (customer_id, limit),
            ).fetchall()

    def list_trending_menu_items(self, limit: int = 5) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT
                    o.item_id,
                    COALESCE(m.name, 'Unknown item') AS name,
                    COALESCE(v.name, 'Unknown vendor') AS vendor_name,
                    COALESCE(m.price, 0) AS price,
                    COUNT(*) AS order_count,
                    MAX(o.created_at) AS latest_order_at
                FROM orders o
                LEFT JOIN menu_items m ON m.id = o.item_id
                LEFT JOIN vendors v ON v.id = m.vendor_id
                WHERE COALESCE(o.status, '') NOT IN ('cancelled', 'canceled')
                GROUP BY o.item_id, m.name, v.name, m.price
                ORDER BY order_count DESC, latest_order_at DESC, name ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def list_unclaimed_paid_orders(self, limit: int = 20) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT
                    o.id,
                    o.order_ref,
                    o.amount,
                    o.cafeteria_name,
                    o.hall_name,
                    o.room_number,
                    m.name AS item_name,
                    o.created_at
                FROM orders o
                LEFT JOIN menu_items m ON m.id = o.item_id
                WHERE o.status='pending_waiter' AND o.waiter_id IS NULL
                ORDER BY o.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def list_waiter_claimed_orders(self, waiter_id: int, limit: int = 20) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT
                    o.id,
                    o.order_ref,
                    o.amount,
                    o.cafeteria_name,
                    o.hall_name,
                    o.room_number,
                    m.name AS item_name,
                    o.created_at
                FROM orders o
                LEFT JOIN menu_items m ON m.id = o.item_id
                WHERE o.status='claimed' AND o.waiter_id=? AND o.completed_at IS NULL
                ORDER BY o.id DESC
                LIMIT ?
                """,
                (waiter_id, limit),
            ).fetchall()

    def list_waiter_active_orders(self, limit: int = 40) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT
                    o.id,
                    o.order_ref,
                    o.amount,
                    o.cafeteria_name,
                    o.hall_name,
                    o.room_number,
                    o.status,
                    o.waiter_id,
                    m.name AS item_name,
                    u.full_name AS waiter_name,
                    o.created_at
                FROM orders o
                LEFT JOIN menu_items m ON m.id = o.item_id
                LEFT JOIN users u ON u.user_id = o.waiter_id
                                WHERE o.status IN ('pending_waiter', 'claimed')
                                    AND o.completed_at IS NULL
                ORDER BY o.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def order_analytics(self, limit: int = 5) -> dict:
        with self.connection() as conn:
            rows = conn.execute(
                """
                SELECT amount, service_fee_total, waiter_share, platform_share, status, payment_method, created_at, cafeteria_name
                FROM orders
                ORDER BY id ASC
                """
            ).fetchall()

        now = datetime.now(self.tz)
        total_orders = len(rows)
        paid_statuses = {"pending_waiter", "claimed", "completed", "delivered"}
        delivered_statuses = {"completed", "delivered"}
        cancelled_statuses = {"cancelled", "canceled"}

        total_revenue = 0
        total_service_fees = 0
        platform_revenue = 0
        paid_orders = 0
        delivered_orders = 0
        cancelled_orders = 0
        today_orders = 0
        week_orders = 0
        payment_totals = defaultdict(int)
        vendor_totals = defaultdict(int)

        for row in rows:
            status = (row["status"] or "").strip().lower()
            amount = int(row["amount"] or 0)
            payment_method = (row["payment_method"] or "transfer").strip().lower() or "transfer"
            created_at = row["created_at"]

            created_dt = None
            if created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at)
                except ValueError:
                    created_dt = None

            if created_dt is not None:
                if created_dt.astimezone(self.tz).date() == now.date():
                    today_orders += 1
                if (now - created_dt.astimezone(self.tz)).days < 7:
                    week_orders += 1

            if status in paid_statuses:
                paid_orders += 1
                total_revenue += amount
                total_service_fees += int(row["service_fee_total"] or 0)
                platform_revenue += int(row["platform_share"] or 0)
                payment_totals[payment_method] += 1
                vendor_name = (row["cafeteria_name"] or "Unknown vendor").strip() or "Unknown vendor"
                vendor_totals[vendor_name] += amount

            if status in delivered_statuses:
                delivered_orders += 1
            elif status in cancelled_statuses:
                cancelled_orders += 1

        top_vendors = sorted(
            vendor_totals.items(),
            key=lambda item: (item[1], item[0].lower()),
            reverse=True,
        )[:limit]

        return {
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "total_service_fees": total_service_fees,
            "platform_revenue": platform_revenue,
            "paid_orders": paid_orders,
            "avg_order_value": (total_revenue / paid_orders) if paid_orders else 0,
            "today_orders": today_orders,
            "week_orders": week_orders,
            "delivered_orders": delivered_orders,
            "cancelled_orders": cancelled_orders,
            "payment_methods": {
                "wallet": payment_totals.get("wallet", 0),
                "paystack": payment_totals.get("paystack", 0),
                "transfer": payment_totals.get("transfer", 0),
            },
            "top_vendors": [
                {"name": name, "revenue": revenue}
                for name, revenue in top_vendors
            ],
        }

    def count_orders(self) -> int:
        with self.connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM orders").fetchone()
            return int(row["total"] or 0)

    def clear_order_history(self) -> int:
        if not self._allow_order_history_purge:
            raise PermissionError(
                "Order history purge is disabled by policy. "
                "Set ALLOW_ORDER_HISTORY_PURGE=true only when you intentionally need a one-time cleanup."
            )
        with self.connection() as conn:
            row = conn.execute("SELECT COUNT(*) AS total FROM orders").fetchone()
            deleted_count = int(row["total"] or 0)
            conn.execute("DELETE FROM orders")
        self._refresh_orders_users_export()
        return deleted_count

    def mark_order_payment_success(self, tx_ref: str) -> Optional[sqlite3.Row]:
        now = self.now_iso()
        with self.connection() as conn:
            order = conn.execute(
                "SELECT * FROM orders WHERE payment_tx_ref=? AND status='pending_payment'",
                (tx_ref,),
            ).fetchone()
            if not order:
                return None

            conn.execute(
                """
                UPDATE orders
                SET status='pending_waiter', updated_at=?
                WHERE id=?
                """,
                (now, order["id"]),
            )
            updated = conn.execute("SELECT * FROM orders WHERE id=?", (order["id"],)).fetchone()
        self._refresh_orders_users_export()
        self._mirror_order_by_id(int(order["id"]))
        return updated

    def mark_order_payment_success_by_order_ref(self, order_ref: str) -> Optional[sqlite3.Row]:
        now = self.now_iso()
        with self.connection() as conn:
            order = conn.execute(
                "SELECT * FROM orders WHERE order_ref=? AND status='pending_payment'",
                (order_ref,),
            ).fetchone()
            if not order:
                return None

            conn.execute(
                """
                UPDATE orders
                SET status='pending_waiter', updated_at=?
                WHERE id=?
                """,
                (now, order["id"]),
            )
            updated = conn.execute("SELECT * FROM orders WHERE id=?", (order["id"],)).fetchone()
        self._refresh_orders_users_export()
        self._mirror_order_by_id(int(order["id"]))
        return updated

    def claim_order(self, order_id: int, waiter_id: int, eta_minutes: int | None = None) -> bool:
        now = self.now_iso()
        eta = max(5, int(eta_minutes or 20))
        eta_due = (datetime.now(self.tz) + timedelta(minutes=eta)).isoformat()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE orders
                SET waiter_id=?, status='claimed', accepted_at=COALESCE(accepted_at, ?), eta_minutes=?, eta_due_at=?, updated_at=?
                                WHERE id=?
                                    AND waiter_id IS NULL
                                    AND status='pending_waiter'
                                    AND (
                                        SELECT COUNT(*)
                                        FROM orders
                                        WHERE waiter_id=? AND status='claimed'
                                    ) < 3
                """,
                                (waiter_id, now, eta, eta_due, now, order_id, waiter_id),
            )
        if cursor.rowcount == 1:
            self._refresh_orders_users_export()
            self._mirror_order_by_id(int(order_id))
            return True
        return False

    def complete_order(self, order_id: int, waiter_id: int) -> bool:
        now = self.now_iso()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE orders
                SET status='completed', completed_at=COALESCE(completed_at, ?), updated_at=?
                WHERE id=? AND waiter_id=? AND status='claimed'
                """,
                (now, now, order_id, waiter_id),
            )
        if cursor.rowcount == 1:
            self._refresh_orders_users_export()
            self._mirror_order_by_id(int(order_id))
            return True
        return False

    def abandon_order(self, order_id: int, waiter_id: int) -> bool:
        now = self.now_iso()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE orders
                SET waiter_id=NULL,
                    status='pending_waiter',
                    accepted_at=NULL,
                    eta_minutes=NULL,
                    eta_due_at=NULL,
                    updated_at=?
                WHERE id=? AND waiter_id=? AND status='claimed'
                """,
                (now, order_id, waiter_id),
            )
        if cursor.rowcount == 1:
            self._refresh_orders_users_export()
            self._mirror_order_by_id(int(order_id))
            return True
        return False

    def submit_order_rating(self, order_id: int, customer_id: int, rating: int) -> bool:
        now = self.now_iso()
        with self.connection() as conn:
            cursor = conn.execute(
                """
                UPDATE orders
                SET customer_rating=?, rating_submitted_at=?, updated_at=?
                WHERE id=?
                  AND customer_id=?
                  AND status='completed'
                  AND customer_rating IS NULL
                """,
                (rating, now, now, order_id, customer_id),
            )
            return cursor.rowcount == 1

    def list_admin_order_progress(self, limit: int = 80) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT
                    o.id,
                    o.order_ref,
                    o.status,
                    o.amount,
                    o.cafeteria_name,
                    o.order_details,
                    o.hall_name,
                    o.room_number,
                    o.customer_rating,
                    o.created_at,
                    o.updated_at,
                    o.accepted_at,
                    o.completed_at,
                    o.eta_minutes,
                    o.eta_due_at,
                    m.name AS item_name,
                    c.full_name AS customer_name,
                    w.full_name AS waiter_name,
                    w.waiter_code AS waiter_code
                FROM orders o
                LEFT JOIN menu_items m ON m.id = o.item_id
                LEFT JOIN users c ON c.user_id = o.customer_id
                LEFT JOIN users w ON w.user_id = o.waiter_id
                WHERE o.status IN ('claimed', 'completed')
                ORDER BY o.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def create_wallet_tx(
        self,
        user_id: int,
        amount: int,
        tx_type: str,
        tx_ref: str,
        payment_link: str,
        status: str,
    ):
        now = self.now_iso()
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO wallet_transactions (
                    user_id, amount, tx_type, tx_ref, payment_link, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, amount, tx_type, tx_ref, payment_link, status, now, now),
            )

    def mark_wallet_tx_success(self, tx_ref: str) -> Optional[sqlite3.Row]:
        now = self.now_iso()
        with self.connection() as conn:
            tx = conn.execute(
                "SELECT * FROM wallet_transactions WHERE tx_ref=? AND status='pending'",
                (tx_ref,),
            ).fetchone()
            if not tx:
                return None
            conn.execute(
                "UPDATE wallet_transactions SET status='success', updated_at=? WHERE id=?",
                (now, tx["id"]),
            )
            conn.execute(
                "UPDATE users SET wallet_balance=wallet_balance+?, updated_at=? WHERE user_id=?",
                (tx["amount"], now, tx["user_id"]),
            )
        self._refresh_waiter_registry_export()
        return tx

    def list_wallet_transactions(self, user_id: int, limit: int = 10) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """
                SELECT id, amount, tx_type, tx_ref, status, created_at
                FROM wallet_transactions
                WHERE user_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()

    def create_order_paid_with_wallet(
        self,
        *,
        order_ref: str,
        user_id: int,
        item_id: int,
        cafeteria_name: str,
        amount: int,
        order_details: str,
        room_number: str,
        delivery_time: str,
        hall_name: str,
        service_fee_total: int,
        waiter_share: int,
        platform_share: int,
        wallet_tx_ref: str,
    ) -> Optional[int]:
        now = self.now_iso()
        with self.connection() as conn:
            debit = conn.execute(
                """
                UPDATE users
                SET wallet_balance = wallet_balance - ?, updated_at=?
                WHERE user_id=? AND wallet_balance >= ?
                """,
                (amount, now, user_id, amount),
            )
            if debit.rowcount != 1:
                return None

            cursor = conn.execute(
                """
                INSERT INTO orders (
                    order_ref, customer_id, item_id, cafeteria_name, amount,
                    order_details, room_number, delivery_time, hall_name, status, payment_method, payment_provider, payment_tx_ref, payment_link, waiter_id,
                    service_fee_total, waiter_share, platform_share, accepted_at, completed_at, eta_minutes, eta_due_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_waiter', 'wallet', 'wallet', ?, NULL, NULL, ?, ?, ?, NULL, NULL, NULL, NULL, ?, ?)
                RETURNING id
                """,
                (
                    order_ref,
                    user_id,
                    item_id,
                    cafeteria_name,
                    amount,
                    order_details,
                    room_number,
                    delivery_time,
                    hall_name,
                    wallet_tx_ref,
                    service_fee_total,
                    waiter_share,
                    platform_share,
                    now,
                    now,
                ),
            )
            inserted = cursor.fetchone()

            conn.execute(
                """
                INSERT INTO wallet_transactions (
                    user_id, amount, tx_type, tx_ref, payment_link, status, created_at, updated_at
                ) VALUES (?, ?, 'order_payment', ?, NULL, 'success', ?, ?)
                """,
                (user_id, -amount, wallet_tx_ref, now, now),
            )
            self._refresh_orders_users_export()
            order_id = int(inserted["id"])
            self._mirror_order_by_id(order_id)
            return order_id
