"""
Resend mirrors for orders that may not have been mirrored.
Usage:
  Set DATABASE_URL and TELEGRAM_BOT_TOKEN via environment or .env, then run:
    python scripts/resend_mirrors.py --days 7 --limit 200

This script finds orders with status != 'pending_payment' created within the
last `days` days and calls Database._mirror_order_by_id(order_id) for each.
It is best-effort and will skip orders that are too old or already recent.
"""
import argparse
from datetime import datetime, timedelta
from config import settings
from db import Database

parser = argparse.ArgumentParser()
parser.add_argument("--days", type=int, default=7, help="Lookback window in days")
parser.add_argument("--limit", type=int, default=500, help="Max orders to process")
args = parser.parse_args()

if not settings.database_url:
    raise RuntimeError("DATABASE_URL is required in env or .env")

db = Database(settings.database_url, settings.bot_timezone)
cutoff = datetime.now(db.tz) - timedelta(days=args.days)
cutoff_iso = cutoff.isoformat()

with db.connection() as conn:
    rows = conn.execute(
        """
        SELECT id, order_ref, status, created_at, updated_at
        FROM orders
        WHERE COALESCE(status, '') NOT IN ('pending_payment')
          AND COALESCE(created_at, '') >= ?
        ORDER BY id ASC
        LIMIT ?
        """,
        (cutoff_iso, args.limit),
    ).fetchall()

print(f"Found {len(rows)} orders to mirror (cutoff {cutoff_iso})")
count = 0
for r in rows:
    oid = int(r["id"])
    print(f"Mirroring order id={oid} ref={r['order_ref']} status={r['status']}")
    try:
        db._mirror_order_by_id(oid)
        count += 1
    except Exception as e:
        print("Error mirroring order", oid, e)

print(f"Mirrored {count}/{len(rows)} orders")
