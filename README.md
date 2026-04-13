# Primechop Telegram Food Delivery Bot (Python)

A Telegram bot for **Cafeteria 1** with:
- Vendor-first customer ordering flow
- Waiter assignment by **first to claim** (sent to all online waiters)
- Wallet top-up flow with Paystack integration (or mock mode)
- In-app order checkout with Paystack initialization
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
- `ADMIN_PHONE_NUMBERS` = comma-separated admin phone numbers for /admin verification (example: `+2349116002889,+2348127812333`)
- `WAITER_IDS` = comma-separated Telegram user IDs for waiters
- `DB_PATH` = SQLite file path for app data (example on Render disk: `/var/data/primechop.db`)
- `BOT_TIMEZONE=Africa/Lagos`
- `CAFETERIA_NAME=Cafeteria 1`
- `ORDER_VENDORS` = comma-separated vendor names shown during ordering
- `DELIVERY_HALLS` = comma-separated hall names shown during checkout
- `SUPER_ADMIN_SECRET` = strong admin password stored only in `.env` if you want to use the super-admin panel

Paystack:
- `PAYSTACK_MODE=mock` for simulation
- Set `PAYSTACK_MODE=live` and real keys/endpoint to integrate
- `PAYSTACK_SECRET_KEY=sk_live_...` in production (`sk_test_...` for sandbox)
- `PAYSTACK_CURRENCY=NGN`
- `PAYSTACK_CALLBACK_URL=https://<your-railway-domain>/paystack/callback`
- `PAYSTACK_INITIALIZE_URL=https://api.paystack.co/transaction/initialize`

Paystack callback note:
- This app serves `/paystack/callback` from a dedicated callback web server only when `WEBHOOK_ENABLED=false`.
- If `WEBHOOK_ENABLED=true`, the app logs a warning and does not expose `/paystack/callback` from the Telegram webhook server in the current setup.

Telegram delivery mode:
- `WEBHOOK_ENABLED=false` uses polling (good for worker deployment)
- `WEBHOOK_ENABLED=true` uses webhooks (requires public HTTPS URL)
- Webhook mode also needs the PTB webhook dependency, which is installed from `requirements.txt`

Service fee:
- `SERVICE_FEE_TOTAL=550`
- `SERVICE_FEE_SPLIT_MODE=equal` for 250/250
- `SERVICE_FEE_SPLIT_MODE=waiter300` for waiter 300 / platform 200
- `START_LOGO=assets/primechop-logo.png` (or an https URL)

Delivery tracker:
- `DEFAULT_DELIVERY_ETA_MINUTES=25` (used when a waiter accepts an order)

## 3) Run

```powershell
python app.py
```

## PostgreSQL (Railway) Setup

If you want to use Railway PostgreSQL, initialize it first with [schema_postgres.sql](schema_postgres.sql).

Quick setup:
1. In Railway, add a `PostgreSQL` service to your project.
2. Open the Postgres service, copy the connection string.
3. Connect with any SQL client (DBeaver, TablePlus, psql) and run [schema_postgres.sql](schema_postgres.sql).
4. Set `DATABASE_URL` in your app service variables to the Railway Postgres connection string.

Important:
- Runtime reads and writes still use SQLite as the primary store in [db.py](db.py).
- When `DATABASE_URL` (or `POSTGRES_MIRROR_URL`) is present, waiter requests and orders are mirrored into PostgreSQL on each write.
- If rows are not appearing in Railway Postgres, verify schema initialization and check app logs for Postgres write warnings.

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
- Keep `LIGHTWEIGHT_MODE=true` on free plans to reduce memory/CPU usage.
- Use `ALLOWED_UPDATES=message,callback_query` unless you need extra Telegram update types.
- Use `STARTUP_WAITER_SYNC_LIMIT=500` (or lower) to reduce startup work.
- Keep `WEBHOOK_ENABLED=true` on Render Web Service for best stability.

## 4) Commands

Customer:
- `/start`
- `/prime` (opens Prime, the friendly assistant for PrimeChop questions and light games)
- `/place_order`
- `/view_cart`
- `/customer_support`
- `/order_history`
- `/terms`
- `/menu`
- `/wallet`
- `/topup <amount>`
- `/cancel` (leave Prime chat mode and return to the main menu)

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
- `/broadcast <message>` (send announcement text to all users who have interacted with the bot)
- Send an image announcement by either:
  - sending a photo with caption `/broadcast <caption>`
  - replying to a photo with `/broadcast <caption>`

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
6. The bot initializes Paystack checkout and stores the order as pending payment.
7. After payment is confirmed, the order is released to waiters.

## 6) Audit Trail (SQLite, Excel, or Google Sheets)

Primechop can write operational logs to a lightweight SQLite store (recommended), a local Excel workbook, or a Google Sheet.

Environment variables:
- `EXCEL_AUDIT_ENABLED=true`
- `EXCEL_AUDIT_BACKEND=sqlite` (recommended), `excel`, or `google`
- `EXCEL_AUDIT_SQLITE_DB=primechop.db` (used when backend is `sqlite`)
- `EXCEL_AUDIT_ASYNC_WRITES=true` (recommended for faster bot replies)
- `EXCEL_AUDIT_FLUSH_INTERVAL_SECONDS=1.0` (lower = more frequent flushes, higher = fewer I/O calls)
- `EXCEL_AUDIT_BATCH_SIZE=25` (higher = better throughput under load)

Lightweight runtime tuning:
- `LIGHTWEIGHT_MODE=true` enables lean startup and polling behavior for constrained hosts.
- `ALLOWED_UPDATES=message,callback_query` limits Telegram update traffic.
- `STARTUP_WAITER_SYNC_LIMIT=500` caps waiter sync rows loaded at boot.

SQLite mode:
- Writes order audit events to `audit_orders` and waiter snapshots to `audit_waiters`.
- Uses append/upsert SQL operations and avoids repeated Excel workbook load/save overhead.

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

Prime assistant AI fallback (answer broader/general questions):
- `PRIME_AI_ENABLED=true`
- `PRIME_AI_API_KEY=<your-api-key>`
- `PRIME_AI_CHAT_URL=https://openrouter.ai/api/v1/chat/completions` (or any OpenAI-compatible chat completions endpoint)
- `PRIME_AI_MODEL=openai/gpt-4o-mini` (or another model from your provider)
- `PRIME_AI_TIMEOUT_SECONDS=20`

Prime AI behavior notes:
- Prime now uses a stronger system prompt and short chat memory so responses feel more like a normal general AI assistant (less rigid keyword replies).
- Prime includes approved PrimeChop background context (origin story and mission) for history-style user questions.
- If the AI endpoint fails, Prime falls back to local/service replies so users still get help.

Human-readable live data exports:
- `human_readable/waiter_registry.csv`
  - Waiter roster, waiter code, verification state, online/offline state, and latest registration details.
- `human_readable/orders_users_tracker.csv`
  - Order id/ref, order details, customer + waiter, accepted timestamp, completed timestamp, ETA minutes, ETA due time, and payment references.

How to open these files:
- They open directly in Excel/Google Sheets.
- In VS Code, install an extension like **Rainbow CSV** for easier filtering/sorting inside the editor.

How to "train" or customize Prime AI:
1. Prompt tuning (fastest): edit the system prompt in [app.py](app.py) to add behavior rules, tone, and trusted facts.
2. Knowledge tuning (safe): add short factual context blocks (company history, policies, FAQs) and keep them updated.
3. Retrieval style (best for growth): store FAQs/policies in a small local data file or DB table, then inject only relevant facts into each AI request.
4. Fine-tuning (advanced): useful when you have a large, high-quality dataset and stable use-cases; most bots perform well with prompt + retrieval first.

Suggested model/endpoints for OpenAI direct usage:
- `PRIME_AI_CHAT_URL=https://api.openai.com/v1/chat/completions`
- `PRIME_AI_MODEL=gpt-4o-mini` (balanced) or `gpt-4.1-mini` (if available on your account)

If `PRIME_AI_API_KEY` is empty, Prime first tries a lightweight web fact lookup and then falls back to scripted local replies.

Tracked sheets and data:
- `OrdersAudit`
  - Appends a new row for each event: `order_created`, `payment_confirmed`, `order_claimed`, `order_completed`.
  - Captures: timestamp, order ref, customer id/name, waiter id/name, item, amount, hall/room, order status, payment status, payment provider, and payment tx reference.
- `WaiterRegistry`
  - Upserts waiter records when invited, approved, logged in, or switched online/offline.
  - Removes waiter records when deactivated/deleted.
  - Syncs existing waiters at app startup.

## 5) Notes

- Waiter assignment policy is **show to all online waiters; first claim wins**.
- New waiters register via `/become_waiter`; after admin approval they receive a code like `WAI123` and must login from the waiter portal.
- Prime is a user-facing assistant persona for PrimeChop guidance, cute chat, and mini games; it should not reveal internal bot creation or operating details.
- Food images support:
  - admin photo upload (stored as Telegram `file_id`)
  - image URL
  - placeholder fallback
- Default timezone is WAT (`Africa/Lagos`).
