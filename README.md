# Primechop Telegram Food Delivery Bot (Python)

A Telegram bot for **Cafeteria 1** with:
- Vendor-first customer ordering flow
- Waiter assignment by **first to claim** (sent to all online waiters)
- Wallet top-up flow with KoraPay integration (or mock mode)
- In-app order checkout with KoraPay initialization
- Admin menu management with real image upload support
- Service fee split logic
- Nigerian timezone (WAT)

## 1) Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Then edit `.env`.

## 2) Required `.env` values

- `TELEGRAM_BOT_TOKEN` = your BotFather token
- `ADMIN_IDS` = comma-separated Telegram user IDs
- `WAITER_IDS` = comma-separated Telegram user IDs for waiters
- `BOT_TIMEZONE=Africa/Lagos`
- `CAFETERIA_NAME=Cafeteria 1`
- `ORDER_VENDORS` = comma-separated vendor names shown during ordering
- `DELIVERY_HALLS` = comma-separated hall names shown during checkout
- `SUPER_ADMIN_SECRET` = strong admin password stored only in `.env` if you want to use the super-admin panel

KoraPay:
- `KORAPAY_MODE=mock` for simulation
- Set `KORAPAY_MODE=live` and real keys/endpoint to integrate

Telegram delivery mode:
- `WEBHOOK_ENABLED=false` uses polling (good for worker deployment)
- `WEBHOOK_ENABLED=true` uses webhooks (requires public HTTPS URL)

Service fee:
- `SERVICE_FEE_TOTAL=500`
- `SERVICE_FEE_SPLIT_MODE=equal` for 250/250
- `SERVICE_FEE_SPLIT_MODE=waiter300` for waiter 300 / platform 200
- `START_LOGO=assets/primechop-logo.png` (or an https URL)

## 3) Run

```powershell
python app.py
```

### Webhook Mode (Render Web Service)

To switch from polling to Telegram webhooks:

- `WEBHOOK_ENABLED=true`
- `WEBHOOK_BASE_URL=https://<your-render-service>.onrender.com`
- `WEBHOOK_PATH=/telegram/webhook` (or any path you prefer)
- `WEBHOOK_PORT` should match Render `PORT` (the app auto-falls back to `PORT` when set)

Render notes:
- Deploy as a **Web Service**.
- Start command stays `python app.py`.
- Keep `WEBHOOK_BASE_URL` set to your public HTTPS service URL.

## 4) Commands

Customer:
- `/start`
- `/place_order`
- `/view_cart`
- `/customer_support`
- `/order_history`
- `/terms`
- `/menu`
- `/wallet`
- `/topup <amount>`

Waiter:
- `/become_waiter` (opens waiter portal: register or login with code)
- `/waiter_online`
- `/waiter_offline`
- `/complete <order_id>`

Admin (secret/super):
- `/admin` (password prompt for waiter management panel)
- `/admin_secret <password>` (opens superior admin panel)
  - pending waiter approvals (approve/reject)
  - invite waiter by Telegram user id
  - list waiters
- `/confirm_order <payment_tx_ref>` (mark a paid order as confirmed and dispatch it)

Never commit `.env` or put secrets directly in the code. Use environment variables or a secret manager for all passwords and API keys.

Admin:
- `/additem` (name → vendor → price → photo/url/skip)
- `/confirm_topup <tx_ref>` (useful in mock mode)

Ordering flow:
1. Customer taps Place an Order.
2. Customer selects a vendor.
3. Customer selects a food item under that vendor.
4. Customer selects a delivery hall.
5. Customer enters the room number.
6. The bot initializes Korapay checkout and stores the order as pending payment.
7. After payment is confirmed, the order is released to waiters.

## 6) Audit Trail (Excel or Google Sheets)

Primechop can write operational logs either to a local Excel workbook or to a Google Sheet.

Environment variables:
- `EXCEL_AUDIT_ENABLED=true`
- `EXCEL_AUDIT_BACKEND=excel` or `EXCEL_AUDIT_BACKEND=google`
- `EXCEL_AUDIT_ASYNC_WRITES=true` (recommended for faster bot replies)
- `EXCEL_AUDIT_FLUSH_INTERVAL_SECONDS=1.0` (lower = more frequent flushes, higher = fewer I/O calls)
- `EXCEL_AUDIT_BATCH_SIZE=25` (higher = better throughput under load)

Excel mode:
- `EXCEL_AUDIT_FILE=primechop_audit.xlsx`

Google Sheets mode:
- `GOOGLE_SHEETS_SPREADSHEET_ID=<your-sheet-id>`
- `GOOGLE_SHEETS_CREDENTIALS_FILE=<path-to-service-account-json>`
- `GOOGLE_SHEETS_ORDER_SHEET=OrdersAudit`
- `GOOGLE_SHEETS_WAITER_SHEET=WaiterRegistry`

Google setup notes:
1. Create a Google Cloud service account and download its JSON key file.
2. Share your target Google Sheet with the service account email as Editor.
3. Put the JSON key path in `GOOGLE_SHEETS_CREDENTIALS_FILE`.
4. Put the sheet id (from the URL) in `GOOGLE_SHEETS_SPREADSHEET_ID`.

Tracked sheets and data:
- `OrdersAudit`
  - Appends a new row for each event: `order_created`, `payment_confirmed`, `order_completed`.
  - Captures: timestamp, order ref, customer id/name, item, amount, hall/room, order status, payment status, payment provider, and payment tx reference.
- `WaiterRegistry`
  - Upserts waiter records when invited, approved, logged in, or switched online/offline.
  - Removes waiter records when deactivated/deleted.
  - Syncs existing waiters at app startup.

## 5) Notes

- Waiter assignment policy is **show to all online waiters; first claim wins**.
- New waiters register via `/become_waiter`; after admin approval they receive a code like `WAI123` and must login from the waiter portal.
- Food images support:
  - admin photo upload (stored as Telegram `file_id`)
  - image URL
  - placeholder fallback
- Default timezone is WAT (`Africa/Lagos`).
