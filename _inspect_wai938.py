print('starting', flush=True)
from config import settings
print('loaded settings', flush=True)
from db import Database
print('loaded db', flush=True)


db = Database(settings.database_url, settings.bot_timezone, settings.allow_order_history_purge)
print('database object created', flush=True)
with db.connection() as conn:
    print('connected', flush=True)
    row = conn.execute("SELECT user_id, full_name, waiter_code, role, waiter_verified, waiter_online FROM users WHERE waiter_code=%s", ('WAI938',)).fetchone()
    print('USER', dict(row) if row else None, flush=True)
    if row:
        user_id = row['user_id']
        orders = conn.execute("SELECT id, order_ref, status, amount, accepted_at, completed_at, updated_at, waiter_id FROM orders WHERE waiter_id=%s ORDER BY id DESC", (user_id,)).fetchall()
        print('ORDERS', len(orders), flush=True)
        for o in orders[:10]:
            print(dict(o), flush=True)
        perf = conn.execute("""
            SELECT
                u.user_id,
                u.full_name,
                u.waiter_code,
                SUM(CASE WHEN o.status='completed' THEN 1 ELSE 0 END) AS completed_orders,
                SUM(CASE WHEN o.status='claimed' THEN 1 ELSE 0 END) AS active_orders,
                SUM(CASE WHEN o.status='completed' THEN 250 ELSE 0 END) AS earnings
            FROM users u
            LEFT JOIN orders o ON o.waiter_id = u.user_id
            WHERE u.waiter_code=%s
            GROUP BY u.user_id, u.full_name, u.waiter_code
        """, ('WAI938',)).fetchone()
        print('PERF', dict(perf) if perf else None, flush=True)
