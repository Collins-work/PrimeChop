"""Repair paid orders stuck in pending_payment and re-mirror them."""
import os
import sys
import argparse
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from config import settings
from db import Database

parser = argparse.ArgumentParser(description="Repair paid orders stuck in pending_payment.")
parser.add_argument("--order-ids", nargs="*", type=int, help="Order IDs to repair")
parser.add_argument("--order-refs", nargs="*", help="Order refs to repair")
parser.add_argument("--db-url", help="PostgreSQL DATABASE_URL connection string")
parser.add_argument("--skip-mirror", action="store_true", help="Update DB status without attempting Telegram mirror")
parser.add_argument("--limit", type=int, default=100, help="Maximum orders to repair from pending_payment if no IDs or refs are provided")
args = parser.parse_args()

if args.db_url:
    settings = settings.__class__(
        telegram_bot_token=settings.telegram_bot_token,
        database_url=args.db_url,
        webhook_enabled=settings.webhook_enabled,
        webhook_base_url=settings.webhook_base_url,
        webhook_path=settings.webhook_path,
        webhook_listen_host=settings.webhook_listen_host,
        webhook_port=settings.webhook_port,
        admin_ids=settings.admin_ids,
        admin_phone_numbers=settings.admin_phone_numbers,
        waiter_ids=settings.waiter_ids,
        order_log_group_chat_id=settings.order_log_group_chat_id,
        bot_timezone=settings.bot_timezone,
        cafeteria_name=settings.cafeteria_name,
        order_vendors=settings.order_vendors,
        delivery_halls=settings.delivery_halls,
        paystack_mode=settings.paystack_mode,
        paystack_secret_key=settings.paystack_secret_key,
        paystack_public_key=settings.paystack_public_key,
        paystack_currency=settings.paystack_currency,
        paystack_callback_url=settings.paystack_callback_url,
        paystack_initialize_url=settings.paystack_initialize_url,
        paystack_verify_url=settings.paystack_verify_url,
        paystack_web_host=settings.paystack_web_host,
        paystack_web_port=settings.paystack_web_port,
        service_fee_total=settings.service_fee_total,
        service_fee_split_mode=settings.service_fee_split_mode,
        placeholder_image_url=settings.placeholder_image_url,
        start_logo=settings.start_logo,
        super_admin_secret=settings.super_admin_secret,
        excel_audit_enabled=settings.excel_audit_enabled,
        excel_audit_backend=settings.excel_audit_backend,
        excel_audit_file=settings.excel_audit_file,
        excel_audit_sqlite_db=settings.excel_audit_sqlite_db,
        google_sheets_spreadsheet_id=settings.google_sheets_spreadsheet_id,
        google_sheets_credentials_file=settings.google_sheets_credentials_file,
        google_sheets_order_sheet=settings.google_sheets_order_sheet,
        google_sheets_waiter_sheet=settings.google_sheets_waiter_sheet,
        excel_audit_async_writes=settings.excel_audit_async_writes,
        excel_audit_flush_interval_seconds=settings.excel_audit_flush_interval_seconds,
        excel_audit_batch_size=settings.excel_audit_batch_size,
        lightweight_mode=settings.lightweight_mode,
        allowed_updates=settings.allowed_updates,
        startup_waiter_sync_limit=settings.startup_waiter_sync_limit,
        prime_ai_enabled=settings.prime_ai_enabled,
        prime_ai_api_key=settings.prime_ai_api_key,
        prime_ai_chat_url=settings.prime_ai_chat_url,
        prime_ai_model=settings.prime_ai_model,
        prime_ai_timeout_seconds=settings.prime_ai_timeout_seconds,
        default_delivery_eta_minutes=settings.default_delivery_eta_minutes,
        customer_cart_max_age_hours=settings.customer_cart_max_age_hours,
        waiter_available_orders_max_age_hours=settings.waiter_available_orders_max_age_hours,
        waiter_available_orders_rollover_hours=settings.waiter_available_orders_rollover_hours,
        waiter_active_orders_max_age_hours=settings.waiter_active_orders_max_age_hours,
        allow_order_history_purge=settings.allow_order_history_purge,
    )

if not settings.database_url:
    raise RuntimeError("DATABASE_URL is required in environment or .env or via --db-url")

if not (args.order_ids or args.order_refs):
    raise RuntimeError("Specify --order-ids or --order-refs to repair orders")


def repair_order_by_id(db: Database, order_id: int, mirror: bool = True) -> bool:
    now = db.now_iso()
    with db.connection() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
        if not order:
            print(f"Order id={order_id} not found")
            return False
        if str(order.get("status") or "").strip().lower() == "pending_waiter":
            print(f"Order id={order_id} is already pending_waiter")
            return False
        conn.execute(
            """
            UPDATE orders
            SET status='pending_waiter', waiter_id=NULL, accepted_at=NULL, completed_at=NULL, updated_at=?
            WHERE id=?
            """,
            (now, order_id),
        )
        updated = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    db._refresh_orders_users_export()
    if mirror:
        db._mirror_order_by_id(order_id)
    print(f"Repaired order id={order_id} ref={updated.get('order_ref')} status={updated.get('status')}")
    return True


def repair_order_by_ref(db: Database, order_ref: str, mirror: bool = True) -> bool:
    now = db.now_iso()
    with db.connection() as conn:
        order = conn.execute("SELECT * FROM orders WHERE order_ref=?", (order_ref,)).fetchone()
        if not order:
            print(f"Order ref={order_ref} not found")
            return False
        order_id = int(order["id"])
        if str(order.get("status") or "").strip().lower() == "pending_waiter":
            print(f"Order ref={order_ref} is already pending_waiter")
            return False
        conn.execute(
            """
            UPDATE orders
            SET status='pending_waiter', waiter_id=NULL, accepted_at=NULL, completed_at=NULL, updated_at=?
            WHERE id=?
            """,
            (now, order_id),
        )
        updated = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    db._refresh_orders_users_export()
    if mirror:
        db._mirror_order_by_id(order_id)
    print(f"Repaired order id={order_id} ref={updated.get('order_ref')} status={updated.get('status')}")
    return True


def main():
    db = Database(settings.database_url, settings.bot_timezone)
    repaired = 0
    skip_mirror = args.skip_mirror or not bool(settings.telegram_bot_token)
    if skip_mirror:
        print("Skipping Telegram mirror because --skip-mirror is set or TELEGRAM_BOT_TOKEN is not configured.")

    if args.order_ids:
        for order_id in args.order_ids:
            if repair_order_by_id(db, order_id, mirror=not skip_mirror):
                repaired += 1
    if args.order_refs:
        for order_ref in args.order_refs:
            if repair_order_by_ref(db, order_ref, mirror=not skip_mirror):
                repaired += 1
    print(f"Done. Repaired {repaired} orders.")


if __name__ == "__main__":
    main()
