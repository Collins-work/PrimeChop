import asyncio
import logging
import random
import re
import string
import warnings
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict

from aiohttp import web
from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import NetworkError, TelegramError
from telegram.request import HTTPXRequest
from telegram.warnings import PTBUserWarning
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import settings
from db import Database
from services.excel_audit import ExcelAuditTrail
from services.payment import KoraPayClient
from ui import (
    BTN_ADMIN_ADDITEM,
    BTN_BECOME_WAITER,
    BTN_CUSTOMER_SUPPORT,
    BTN_MENU,
    BTN_ORDER_HISTORY,
    BTN_PLACE_ORDER,
    BTN_VIEW_ORDERS,
    BTN_WALLET,
    BTN_TERMS,
    BTN_VIEW_CART,
    BTN_WAITER_OFFLINE,
    BTN_WAITER_ONLINE,
    format_admin_additem_image,
    format_admin_additem_price,
    format_admin_additem_start,
    format_admin_additem_success,
    format_become_waiter_success,
        format_catalog_items_list,
        format_catalog_management_menu,
        format_item_management_options,
        format_item_removed_success,
        format_item_removal_confirmation,
    format_customer_support,
    format_empty_cart,
    format_empty_order_history,
    format_error_message,
    format_help_message,
    format_invalid_amount,
    format_menu_empty,
    format_menu_vendor_caption,
    format_menu_item_caption,
    format_hall_prompt,
    format_order_payment_pending,
    format_order_payment_ready,
    format_order_claimed,
    format_order_completed,
    format_order_completed_waiter,
    format_order_confirmed,
    format_order_created_no_waiter,
    format_order_history,
    format_order_submitted,
    format_room_prompt_with_hall,
    format_room_invalid,
    format_room_prompt,
    format_start_message,
    format_terms_and_conditions,
    format_topup_amount_prompt,
    format_topup_created,
    format_topup_info,
    format_topup_success,
    format_unauthorized,
    format_waiter_offline_success,
    format_waiter_online_success,
    format_waiter_order_alert,
    format_view_cart,
    format_wallet_info,
    home_keyboard,
    hall_selection_keyboard,
    menu_item_keyboard,
    order_claim_keyboard,
    order_post_actions_keyboard,
    pay_now_keyboard,
    start_place_order_keyboard,
    vendor_items_keyboard,
    vendor_selection_keyboard,
    topup_presets_keyboard,
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# This conversation mixes callback queries and text input by design (room entry).
# Keep per_message at default and silence the advisory warning.
warnings.filterwarnings(
    "ignore",
    message=r"If 'per_message=False', 'CallbackQueryHandler' will not be tracked for every message.*",
    category=PTBUserWarning,
)

(
    ADD_ITEM_NAME,
    ADD_ITEM_VENDOR,
    ADD_ITEM_PRICE,
    ADD_ITEM_IMAGE,
    ORDER_VENDOR,
    ORDER_ITEM,
    ORDER_HALL,
    ORDER_ROOM,
    ADMIN_INVITE_USER_ID,
    WAITER_REGISTER_DETAILS,
    WAITER_LOGIN_CODE,
    ADMIN_LOGIN_PASSWORD,
    ADMIN_DEACTIVATE_INPUT,
    TOPUP_AMOUNT,
) = range(14)


@dataclass
class RuntimeState:
    add_item_draft: Dict[int, dict] = field(default_factory=dict)


db = Database(path="primechop.db", timezone_name=settings.bot_timezone)
audit_trail = ExcelAuditTrail(
    file_path=settings.excel_audit_file,
    enabled=settings.excel_audit_enabled,
    backend=settings.excel_audit_backend,
    google_spreadsheet_id=settings.google_sheets_spreadsheet_id,
    google_credentials_file=settings.google_sheets_credentials_file,
    order_sheet_name=settings.google_sheets_order_sheet,
    waiter_sheet_name=settings.google_sheets_waiter_sheet,
    async_writes=settings.excel_audit_async_writes,
    flush_interval_seconds=settings.excel_audit_flush_interval_seconds,
    max_batch_size=settings.excel_audit_batch_size,
)
if settings.excel_audit_enabled and settings.excel_audit_backend == "google":
    sheet_url = audit_trail.get_google_sheet_url()
    if sheet_url:
        logger.info("Google Sheets audit enabled: %s", sheet_url)
payments = KoraPayClient(
    mode=settings.korapay_mode,
    secret_key=settings.korapay_secret_key,
    currency=settings.korapay_currency,
    callback_url=settings.korapay_callback_url,
    initialize_url=settings.korapay_initialize_url,
)
runtime = RuntimeState()


def _audit_order_event(order_row, event: str, payment_status: str):
    if not order_row:
        return
    try:
        customer = db.get_user(order_row["customer_id"])
        item = db.get_menu_item(order_row["item_id"])
        audit_trail.log_order(
            event=event,
            timestamp=order_row["updated_at"] or order_row["created_at"] or db.now_iso(),
            order_ref=order_row["order_ref"] or str(order_row["id"]),
            customer_id=int(order_row["customer_id"]),
            customer_name=(customer["full_name"] if customer else "Unknown customer"),
            item=(item["name"] if item else f"Item #{order_row['item_id']}"),
            amount=int(order_row["amount"] or 0),
            hall=order_row["hall_name"] or "",
            room=order_row["room_number"] or "",
            order_status=(order_row["status"] or "").strip(),
            payment_status=payment_status,
            payment_provider=(order_row["payment_provider"] or "").strip(),
            payment_tx_ref=(order_row["payment_tx_ref"] or "").strip(),
        )
    except Exception:
        logger.exception("Failed to write order audit event")


def _audit_waiter_upsert_by_user_id(user_id: int):
    row = db.get_user(user_id)
    if not row:
        return
    audit_trail.upsert_waiter(
        user_id=int(row["user_id"]),
        full_name=row["full_name"] or "",
        waiter_code=row["waiter_code"] or "",
        role=row["role"] or "customer",
        verified=bool(row["waiter_verified"]),
        online=bool(row["waiter_online"]),
        updated_at=row["updated_at"] or db.now_iso(),
    )


def _audit_waiter_remove(user_id: int):
    audit_trail.remove_waiter(user_id)


def _extract_korapay_reference(payload: dict, query: dict) -> str:
    for source in (payload, query):
        for key in ("reference", "tx_ref", "trx_ref", "transaction_reference", "transactionReference"):
            value = source.get(key)
            if value:
                return str(value).strip()
        data_node = source.get("data")
        if isinstance(data_node, dict):
            for key in ("reference", "tx_ref", "trx_ref", "transaction_reference", "transactionReference"):
                value = data_node.get(key)
                if value:
                    return str(value).strip()
    return ""


def _is_korapay_success(payload: dict, query: dict) -> bool:
    status = ""
    for source in (payload, query):
        for key in ("status", "payment_status", "event"):
            value = source.get(key)
            if value:
                status = str(value).strip().lower()
                break
        if status:
            break
        data_node = source.get("data")
        if isinstance(data_node, dict):
            for key in ("status", "payment_status", "event"):
                value = data_node.get(key)
                if value:
                    status = str(value).strip().lower()
                    break
            if status:
                break
    return status in {"success", "successful", "completed", "paid", "payment_successful", "charge.success"}


async def korapay_wallet_callback(request: web.Request) -> web.Response:
    payload = {}
    try:
        if request.can_read_body:
            if request.content_type == "application/json":
                payload = await request.json()
            else:
                form_data = await request.post()
                payload = dict(form_data)
    except Exception:
        payload = {}

    query = dict(request.query)
    reference = _extract_korapay_reference(payload if isinstance(payload, dict) else {}, query)
    if not reference:
        return web.Response(text="Missing payment reference", status=400)

    if not _is_korapay_success(payload if isinstance(payload, dict) else {}, query):
        return web.Response(text="Payment callback received", status=202)

    tx = db.mark_wallet_tx_success(reference)
    if not tx:
        return web.Response(text="Top-up already processed or not found", status=200)

    return web.Response(text=f"Wallet top-up credited for reference {reference}", status=200)


def start_korapay_callback_server():
    if not settings.korapay_callback_url:
        return

    async def _run_server():
        app = web.Application()
        app.router.add_get("/korapay/callback", korapay_wallet_callback)
        app.router.add_post("/korapay/callback", korapay_wallet_callback)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, settings.korapay_web_host, settings.korapay_web_port)
        await site.start()

        while True:
            await asyncio.sleep(3600)

    def _thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_server())

    thread = threading.Thread(target=_thread_target, daemon=True)
    thread.start()


FIXED_VENDOR_PRODUCTS: dict[str, list[tuple[str, int]]] = {
    "D4fries": [
        ("Chicken and chips", 3200),
    ],
    "Emabuop": [
        ("Bole (potatoes and yam) - from", 1300),
        ("Egg", 300),
        ("Sausage", 300),
        ("Beef", 200),
        ("Pomo", 100),
        ("Round fish", 500),
        ("Sliced fish", 200),
        ("Egg sauce", 500),
        ("Fish sauce", 400),
        ("Pepper sauce", 300),
        ("Normal sauce", 200),
    ],
    "DGG Grills": [
        ("Bole (starting price)", 1700),
        ("Pepper sauce", 400),
        ("Normal sauce", 300),
        ("Egg sauce", 1000),
        ("Sausage", 300),
        ("Fish (small)", 300),
        ("Fish (large)", 500),
        ("Beef", 200),
        ("Pomo", 100),
    ],
    "Suya Academy": [
        ("Regular suya (small)", 500),
        ("Regular suya (large)", 1000),
        ("Chicken suya", 3000),
        ("Special suya", 500),
    ],
    "Spicy Igbo delicacy": [
        ("Regular suya (small)", 500),
        ("Regular suya (large)", 1000),
        ("Chicken suya", 3000),
    ],
    "Dekoen amazing fruits": [
        ("Pineapple juice", 1400),
        ("Watermelon juice", 1400),
        ("Lemonade", 1200),
        ("Zobo", 1200),
        ("Tiger-nut juice", 1500),
        ("Smoothie", 1000),
        ("Banana bunch", 1500),
        ("Watermelon", 500),
        ("Pineapple", 500),
        ("Orange", 200),
    ],
    "Yam and fish": [
        ("Half fish", 1200),
        ("Full fish", 3000),
        ("Half fish with potatoes", 2200),
        ("Full fish with small potato portions", 3500),
        ("Full fish with large potatoes portion", 4500),
        ("Just potatoes", 1500),
    ],
}


def user_role(user_id: int) -> str:
    if user_id in settings.admin_ids:
        return "admin"
    row = db.get_user(user_id)
    if row and row["role"] == "waiter":
        return "waiter"
    return "customer"


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def is_waiter(user_id: int) -> bool:
    row = db.get_user(user_id)
    return bool(row and row["role"] == "waiter" and row["waiter_verified"] == 1)


def service_fee_split(total: int, mode: str) -> tuple[int, int]:
    if mode == "waiter300":
        return 300, max(0, total - 300)
    if mode == "platform300":
        return max(0, total - 300), 300
    return total // 2, total - (total // 2)


def normalize_room(room_text: str) -> str | None:
    room = (room_text or "").strip().upper().replace(" ", "")
    if re.fullmatch(r"[A-H]\d{3}", room):
        return room
    return None


def generate_order_ref() -> str:
    alphabet = string.ascii_lowercase + string.digits
    for _ in range(20):
        order_ref = "".join(random.choice(alphabet) for _ in range(7))
        if not db.order_ref_exists(order_ref):
            return order_ref
    raise RuntimeError("Unable to generate a unique order reference.")


def generate_waiter_code() -> str:
    for _ in range(100):
        code = f"WAI{random.randint(100, 999)}"
        if not db.waiter_code_exists(code):
            return code
    raise RuntimeError("Unable to generate unique waiter code.")


def generate_waiter_user_id() -> str:
    for _ in range(200):
        public_user_id = f"WAI{random.randint(100, 999)}"
        if not db.waiter_public_user_id_exists(public_user_id):
            return public_user_id
    raise RuntimeError("Unable to generate waiter user id.")


def has_super_admin_access(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    return bool(context.user_data.get("super_admin"))


def super_admin_access_enabled() -> bool:
    return bool(settings.super_admin_secret)


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👨‍🍳 Waiter Management", callback_data="admin:menu_waiters")],
            [InlineKeyboardButton("📈 Order Analysis", callback_data="admin:menu_analytics")],
            [InlineKeyboardButton("📊 Waiter Analysis", callback_data="admin:waiter_analytics")],
            [InlineKeyboardButton("🍽️ Catalog Management", callback_data="admin:menu_catalog")],
            [InlineKeyboardButton("⚡ Quick Actions", callback_data="admin:menu_quick")],
            [InlineKeyboardButton("🔒 Exit Admin Panel", callback_data="admin:logout")],
        ]
    )


def admin_analytics_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Refresh Analytics", callback_data="admin:order_analytics")],
            [InlineKeyboardButton("🔙 Back to Admin Home", callback_data="admin:menu")],
        ]
    )



def admin_catalog_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add Menu Item", callback_data="admin:catalog_additem_start")],
            [InlineKeyboardButton("🍽️ View All Items", callback_data="admin:catalog_view_items")],
            [InlineKeyboardButton("🏪 List Vendors", callback_data="admin:catalog_list_vendors")],
            [InlineKeyboardButton("📦 Catalog Summary", callback_data="admin:catalog_summary")],
            [InlineKeyboardButton("🔙 Back to Admin Home", callback_data="admin:menu")],
        ]
    )


def admin_catalog_detail_keyboard(item_id: int) -> InlineKeyboardMarkup:
    """Keyboard for managing a specific menu item."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(f"🗑️ Delete Item #{item_id}", callback_data=f"admin:catalog_remove:{item_id}")],
            [InlineKeyboardButton("📋 Back to Items List", callback_data="admin:catalog_view_items")],
            [InlineKeyboardButton("🔙 Back to Catalog Menu", callback_data="admin:menu_catalog")],
        ]
    )


def admin_catalog_items_keyboard(items: list) -> InlineKeyboardMarkup:
    """Keyboard for selecting and managing menu items."""
    rows = []
    for item in items:
        rows.append([InlineKeyboardButton(f"#{item['id']} - {item['name']}", callback_data=f"admin:catalog_item:{item['id']}")])
    rows.append([InlineKeyboardButton("🔙 Back to Catalog", callback_data="admin:menu_catalog")])
    return InlineKeyboardMarkup(rows)

def admin_quick_actions_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Pending Approvals", callback_data="adminwm:approve_waiters")],
            [InlineKeyboardButton("✉️ Invite Waiter", callback_data="admin:invite_waiter")],
            [InlineKeyboardButton("📊 Open Analytics", callback_data="admin:order_analytics")],
            [InlineKeyboardButton("🔙 Back to Admin Home", callback_data="admin:menu")],
        ]
    )


def format_admin_home() -> str:
    return (
        "🔧 <b>Admin Control Center</b>\n\n"
        "Welcome to the Primechop admin panel.\n"
        "Choose a section below to manage operations."
    )


def format_admin_quick_actions() -> str:
    return (
        "⚡ <b>Quick Actions</b>\n\n"
        "Use shortcuts for common admin tasks:\n"
        "• Pending waiter approvals\n"
        "• Invite waiter\n"
        "• Open analytics dashboard"
    )


def format_catalog_summary(vendors: list, items: list) -> str:
    return (
        "🍽️ <b>Catalog Summary</b>\n\n"
        f"🏪 Active Vendors: <b>{len(vendors)}</b>\n"
        f"📦 Total Menu Items: <b>{len(items)}</b>\n\n"
        "Use Add Menu Item to update the catalog."
    )


def format_catalog_vendors(vendors: list) -> str:
    if not vendors:
        return "🏪 <b>Vendors</b>\n\nNo active vendors found."

    lines = ["🏪 <b>Active Vendors</b>", ""]
    for index, vendor in enumerate(vendors, start=1):
        lines.append(f"{index}. {vendor['name']}")
    return "\n".join(lines)


def format_catalog_menu() -> str:
    return (
        "🍽️ <b>Catalog Management</b>\n\n"
        "Manage vendor/menu setup from this section.\n"
        "You can add new items, view active vendors, and check catalog totals."
    )


def order_analytics_keyboard() -> InlineKeyboardMarkup:
    return admin_analytics_keyboard()


def format_waiter_management_menu() -> str:
    return (
        "👨‍🍳 <b>Waiter Management</b>\n\n"
        "Manage approvals, performance, and waiter status from this menu."
    )


def format_admin_invite_prompt() -> str:
    return (
        "✉️ <b>Invite Waiter</b>\n\n"
        "Send the Telegram user ID to invite as waiter.\n"
        "Example: <code>123456789</code>"
    )


def format_admin_additem_help() -> str:
    return (
        "➕ <b>Add Menu Item</b>\n\n"
        "Use <code>/additem</code> to add a new menu item with vendor and price."
    )


def _get_order_vendor_rows():
    if settings.order_vendors:
        preferred_vendors = []
        for name in settings.order_vendors:
            preferred_vendors.append(db.upsert_vendor(name))
        if preferred_vendors:
            return preferred_vendors

    vendors = db.list_vendors()
    if vendors:
        return vendors
    fallback = db.upsert_vendor(settings.cafeteria_name)
    return [fallback]


def _ensure_order_draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    draft = context.user_data.get("order_draft")
    if not isinstance(draft, dict):
        draft = {}
        context.user_data["order_draft"] = draft
    return draft


def _order_checkout_email(user) -> str:
    return f"user{user.id}@primechop.local"


async def _send_vendor_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vendors = _get_order_vendor_rows()
    if not vendors:
        await update.effective_message.reply_text(format_menu_empty(), parse_mode="HTML")
        return

    await update.effective_message.reply_text(
        "🏪 <b>Choose a Vendor</b>\n\nSelect who you want to order from.",
        parse_mode="HTML",
        reply_markup=vendor_selection_keyboard(vendors),
    )


async def _send_vendor_items(update: Update, context: ContextTypes.DEFAULT_TYPE, vendor_id: int):
    vendor = db.get_vendor(vendor_id)
    if not vendor:
        await context.bot.send_message(chat_id=update.effective_user.id, text="Vendor not found.")
        return ConversationHandler.END

    items = db.list_menu_items_by_vendor(vendor_id)
    if not items:
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text=f"{vendor['name']} has no available items yet.",
            reply_markup=vendor_selection_keyboard(_get_order_vendor_rows()),
        )
        return ORDER_VENDOR

    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=format_menu_vendor_caption(vendor["name"]),
        parse_mode="HTML",
        reply_markup=vendor_items_keyboard(items, vendor_id),
    )
    return ORDER_ITEM


async def _send_hall_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = _ensure_order_draft(context)
    item_name = draft.get("item_name", "Selected item")
    vendor_name = draft.get("vendor_name", settings.cafeteria_name)
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=format_hall_prompt(item_name, vendor_name),
        parse_mode="HTML",
        reply_markup=hall_selection_keyboard(settings.delivery_halls),
    )
    return ORDER_HALL


async def _finalize_order_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get("order_draft", {})
    if not draft:
        await update.effective_message.reply_text("Order session expired. Tap Place an Order and try again.")
        return ConversationHandler.END

    user = update.effective_user
    order_ref = generate_order_ref()
    vendor_name = draft["vendor_name"]
    item_name = draft["item_name"]
    hall_name = draft["hall_name"]
    room_number = draft["room_number"]
    amount = int(draft["amount"])

    try:
        payment_result = await payments.initialize_order_checkout(
            amount=amount,
            email=_order_checkout_email(user),
            full_name=user.full_name,
            user_id=user.id,
            order_ref=order_ref,
        )
    except Exception as exc:
        logger.exception("Order payment initialization failed")
        await update.effective_message.reply_text(
            format_error_message(f"Unable to start payment right now: {exc}"),
            parse_mode="HTML",
        )
        return ConversationHandler.END

    waiter_share, platform_share = service_fee_split(
        settings.service_fee_total,
        settings.service_fee_split_mode,
    )
    order_id = db.create_order(
        order_ref=order_ref,
        customer_id=user.id,
        item_id=draft["item_id"],
        cafeteria_name=vendor_name,
        amount=amount,
        order_details=draft.get("order_details", ""),
        room_number=room_number,
        delivery_time="",
        hall_name=hall_name,
        status="pending_payment",
        payment_method=payments.provider_name(),
        payment_provider=payments.provider_name(),
        payment_tx_ref=payment_result.tx_ref,
        payment_link=payment_result.checkout_url,
        service_fee_total=settings.service_fee_total,
        waiter_share=waiter_share,
        platform_share=platform_share,
    )
    _audit_order_event(db.get_order(order_id), event="order_created", payment_status="pending")

    await update.effective_message.reply_text(
        format_order_payment_ready(
            order_ref=order_ref,
            vendor_name=vendor_name,
            item_name=item_name,
            hall_name=hall_name,
            room_number=room_number,
            amount=amount,
            payment_provider=payments.provider_name(),
        ),
        parse_mode="HTML",
        reply_markup=pay_now_keyboard(payment_result.checkout_url, label="💳 Pay with Korapay"),
    )

    if settings.korapay_mode == "mock":
        await update.effective_message.reply_text(
            f"Mock mode is active. Admin can confirm this payment with /confirm_order {payment_result.tx_ref}.",
        )

    context.user_data.pop("order_draft", None)
    return ConversationHandler.END


async def _dispatch_paid_order(order_row, context: ContextTypes.DEFAULT_TYPE):
    order = db.get_order(order_row["id"])
    if not order:
        return

    item = db.get_menu_item(order["item_id"])
    item_name = item["name"] if item else f"Item #{order['item_id']}"
    vendor_name = order["cafeteria_name"]
    hall_name = order["hall_name"] or "Unknown hall"
    room_number = order["room_number"] or "N/A"

    confirmation_text = format_order_confirmed(
        order_ref=order["order_ref"] or str(order["id"]),
        amount=order["amount"],
        vendor_name=vendor_name,
        hall_name=hall_name,
        room_number=room_number,
        item_name=item_name,
    )
    await context.bot.send_message(
        chat_id=order["customer_id"],
        text=confirmation_text,
        parse_mode="HTML",
        reply_markup=order_post_actions_keyboard(),
    )

    online_waiters = db.get_online_waiters(settings.waiter_ids)
    if not online_waiters:
        return

    waiter_text = format_waiter_order_alert(
        order_ref=order["order_ref"] or str(order["id"]),
        item_name=item_name,
        price=order["amount"],
        vendor_name=vendor_name,
        hall_name=hall_name,
        room_number=room_number,
    )
    keyboard = order_claim_keyboard(order["id"])

    for waiter in online_waiters:
        await context.bot.send_message(
            chat_id=waiter["user_id"],
            text=waiter_text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


async def confirm_order_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.effective_message.reply_text(format_unauthorized(), parse_mode="HTML")
        return

    if not context.args:
        await update.effective_message.reply_text("Usage: /confirm_order <payment_tx_ref>")
        return

    tx_ref = context.args[0].strip()
    order = db.mark_order_payment_success(tx_ref)
    if not order:
        await update.effective_message.reply_text("Pending order payment not found for that reference.")
        return
    _audit_order_event(order, event="payment_confirmed", payment_status="confirmed")

    await update.effective_message.reply_text(
        f"✅ Order payment confirmed for {order['order_ref'] or order['id']}.",
    )
    await _dispatch_paid_order(order, context)


async def order_catalog_navigation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split(":", 1)[1]
    if action == "back_vendors":
        await query.edit_message_text(
            "🏪 <b>Choose a Vendor</b>\n\nSelect where you want to order from.",
            parse_mode="HTML",
            reply_markup=vendor_selection_keyboard(_get_order_vendor_rows()),
        )
        return

    if action == "back_items":
        draft = context.user_data.get("order_draft", {})
        vendor_id = draft.get("vendor_id")
        if not vendor_id:
            await query.edit_message_text(
                "🏪 <b>Choose a Vendor</b>\n\nSelect where you want to order from.",
                parse_mode="HTML",
                reply_markup=vendor_selection_keyboard(_get_order_vendor_rows()),
            )
            return
        vendor = db.get_vendor(vendor_id)
        if not vendor:
            await query.edit_message_text("Vendor not found.")
            return
        items = db.list_menu_items_by_vendor(vendor_id)
        if not items:
            await query.edit_message_text(f"{vendor['name']} has no available items yet.")
            return
        await query.edit_message_text(
            format_menu_vendor_caption(vendor["name"]),
            parse_mode="HTML",
            reply_markup=vendor_items_keyboard(items, vendor_id),
        )
        return


def waiter_request_actions_keyboard(request_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"admin:approve_waiter:{request_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"admin:reject_waiter:{request_id}"),
            ]
        ]
    )


def waiter_portal_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔑 Login with Code", callback_data="waiter_portal:login")],
            [InlineKeyboardButton("📝 Register as Waiter", callback_data="waiter_portal:register")],
        ]
    )


def admin_waiter_management_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ Approve Waiters", callback_data="adminwm:approve_waiters")],
            [InlineKeyboardButton("❌ Deactivate Waiter", callback_data="adminwm:deactivate_waiter")],
            [InlineKeyboardButton("📊 Waiter Performance", callback_data="adminwm:performance")],
            [InlineKeyboardButton("👥 All Waiters", callback_data="adminwm:all_waiters")],
            [InlineKeyboardButton("🔙 Back to Admin Home", callback_data="admin:menu")],
        ]
    )


def _is_new_this_week(iso_text: str | None) -> bool:
    if not iso_text:
        return False
    try:
        dt = datetime.fromisoformat(iso_text)
    except ValueError:
        return False
    return (datetime.now(dt.tzinfo) - dt).days < 7


def build_waiter_management_stats() -> str:
    waiters = db.list_waiters(limit=100)
    total = len(waiters)
    active = sum(1 for w in waiters if w["role"] == "waiter" and w["waiter_online"])
    new_week = sum(1 for w in waiters if _is_new_this_week(w["updated_at"]))

    lines = [
        "👨‍🍳 <b>Waiter Management</b>",
        "",
        "📊 <b>Stats:</b>",
        f"Total waiters: {total}",
        f"Active: {active}",
        f"New this week: {new_week}",
        "",
        "Recent waiters:",
    ]
    for row in waiters[:6]:
        code = row["waiter_code"] or f"UID{row['user_id']}"
        status = "✅" if row["role"] == "waiter" else "❌"
        lines.append(f"{status} {code} - {row['full_name']}")
    if not waiters:
        lines.append("No waiter records yet.")
    return "\n".join(lines)


def format_order_analytics_dashboard(report: dict) -> str:
    payment_methods = report.get("payment_methods", {}) or {}
    top_vendors = report.get("top_vendors", []) or []

    lines = ["📈 <b>Order Analytics</b>", "", "📁 <b>Overview:</b>"]
    lines.append(f"Total Orders: {int(report.get('total_orders', 0))}")
    lines.append(f"Total Revenue: ₦{float(report.get('total_revenue', 0)):,.2f}")
    lines.append(f"Avg Order Value: ₦{float(report.get('avg_order_value', 0)):,.2f}")
    lines.extend(["", "📅 <b>Time-based:</b>"])
    lines.append(f"Today: {int(report.get('today_orders', 0))} orders")
    lines.append(f"This Week: {int(report.get('week_orders', 0))} orders")
    lines.extend(["", "📊 <b>Status Breakdown:</b>"])
    lines.append(f"Delivered: {int(report.get('delivered_orders', 0))}")
    lines.append(f"Cancelled: {int(report.get('cancelled_orders', 0))}")
    lines.extend(["", "💳 <b>Payment Methods:</b>"])
    lines.append(f"Wallet: {int(payment_methods.get('wallet', 0))}")
    lines.append(f"Transfer: {int(payment_methods.get('transfer', 0))}")
    lines.extend(["", "🏆 <b>Top Vendors by Revenue:</b>"])

    if top_vendors:
        for index, vendor in enumerate(top_vendors, start=1):
            lines.append(f"{index}. {vendor['name']}: ₦{float(vendor['revenue']):,.2f}")
    else:
        lines.append("No delivered orders yet.")

    return "\n".join(lines)


def format_waiter_analytics_dashboard(rows: list) -> str:
    if not rows:
        return "📊 <b>Waiter Analysis</b>\n\nNo waiter performance data yet."

    total_completed = sum(int(row["completed_orders"] or 0) for row in rows)
    total_earnings = sum(int(row["earnings"] or 0) for row in rows)

    lines = ["📊 <b>Waiter Analysis</b>", ""]
    lines.append(f"Total Waiters Tracked: {len(rows)}")
    lines.append(f"Completed Orders: {total_completed}")
    lines.append(f"Total Waiter Earnings: ₦{total_earnings:,}")
    lines.extend(["", "Top Waiters:"])

    for index, row in enumerate(rows[:10], start=1):
        code = row["waiter_code"] or f"UID{row['user_id']}"
        completed = int(row["completed_orders"] or 0)
        active = int(row["active_orders"] or 0)
        earnings = int(row["earnings"] or 0)
        lines.append(
            f"{index}. {code} | Completed: {completed} | Active: {active} | Earnings: ₦{earnings:,}"
        )

    return "\n".join(lines)


def format_waiter_order_book(available_rows: list) -> str:
    if not available_rows:
        return "📦 <b>Available Orders</b>\n\nNo open paid orders right now."

    lines = ["📦 <b>Available Orders</b>", "First waiter to claim gets the delivery payout after completion."]
    for row in available_rows:
        order_ref = row["order_ref"] or str(row["id"])
        item_name = row["item_name"] or f"Item #{row['id']}"
        hall_name = row["hall_name"] or "Unknown hall"
        room_number = row["room_number"] or "N/A"
        lines.append(
            f"#{order_ref} - {item_name} - ₦{int(row['amount'] or 0):,} - {hall_name} Room {room_number}"
        )
    return "\n".join(lines)


def waiter_claim_list_keyboard(orders: list) -> InlineKeyboardMarkup:
    rows = []
    for row in orders[:15]:
        order_ref = row["order_ref"] or str(row["id"])
        rows.append([InlineKeyboardButton(f"✅ Claim #{order_ref}", callback_data=f"claim:{row['id']}")])
    return InlineKeyboardMarkup(rows)


def _resolve_logo_source() -> tuple[bool, str]:
    logo = (settings.start_logo or "").strip()
    if not logo:
        return False, ""

    if logo.startswith("http://") or logo.startswith("https://"):
        return True, logo

    logo_path = Path(logo)
    if not logo_path.is_absolute():
        logo_path = Path(__file__).resolve().parent / logo_path

    if logo_path.exists() and logo_path.is_file():
        return True, str(logo_path)

    return False, ""


async def send_start_banner(update: Update, role: str):
    message = update.effective_message
    welcome_text = format_start_message(settings.cafeteria_name)
    cta_keyboard = start_place_order_keyboard()
    has_logo, logo_source = _resolve_logo_source()
    sent_banner = False

    if has_logo:
        try:
            if logo_source.startswith("http://") or logo_source.startswith("https://"):
                await message.reply_photo(
                    photo=logo_source,
                    caption=welcome_text,
                    parse_mode="HTML",
                    reply_markup=cta_keyboard,
                )
                sent_banner = True

            if not sent_banner:
                with open(logo_source, "rb") as logo_file:
                    await message.reply_photo(
                        photo=logo_file,
                        caption=welcome_text,
                        parse_mode="HTML",
                        reply_markup=cta_keyboard,
                    )
                    sent_banner = True
        except Exception:
            logger.exception("Unable to send logo on /start; falling back to text")

    if not sent_banner:
        await message.reply_text(welcome_text, parse_mode="HTML", reply_markup=cta_keyboard)

    await message.reply_text("Choose an option below.", reply_markup=home_keyboard(role))


async def start_place_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await menu(update, context)


async def order_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split(":", 1)[1]
    if action == "my_orders":
        await order_history(update, context)
        return

    if action == "main_menu":
        role = user_role(query.from_user.id)
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="🏠 Main menu ready.",
            reply_markup=home_keyboard(role),
        )


async def start_topup_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("topup_mode", None)
    await update.effective_message.reply_text(
        format_topup_info(),
        reply_markup=topup_presets_keyboard(),
        parse_mode="HTML",
    )


async def start_custom_topup_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["topup_mode"] = "await_amount"
    await update.effective_message.reply_text(
        format_topup_amount_prompt(),
        parse_mode="HTML",
    )


async def initialize_topup_for_user(
    user,
    chat_id: int,
    amount: int,
    context: ContextTypes.DEFAULT_TYPE,
):
    email = f"user{user.id}@primechop.local"
    try:
        result = await payments.initialize_wallet_topup(
            amount=amount,
            email=email,
            full_name=user.full_name,
            user_id=user.id,
        )
    except Exception as exc:
        logger.exception("Top-up initialization failed")
        await context.bot.send_message(
            chat_id=chat_id,
            text=format_error_message(f"Unable to initialize top-up now: {exc}"),
            parse_mode="HTML",
        )
        return

    db.create_wallet_tx(
        user_id=user.id,
        amount=amount,
        tx_type="topup",
        tx_ref=result.tx_ref,
        payment_link=result.checkout_url,
        status="pending",
    )

    keyboard = pay_now_keyboard(result.checkout_url)
    text = format_topup_created(amount, result.tx_ref, settings.korapay_mode)
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard, parse_mode="HTML")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = user_role(user.id)
    db.upsert_user(user.id, user.full_name, role=role)
    await send_start_banner(update, role)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    role = user_role(update.effective_user.id)
    text = format_help_message()
    await update.effective_message.reply_text(text, reply_markup=home_keyboard(role), parse_mode="HTML")


async def place_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await menu(update, context)


async def view_cart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = db.list_customer_orders(user.id, limit=10)
    if not rows:
        await update.effective_message.reply_text(format_empty_cart(), parse_mode="HTML")
        return
    await update.effective_message.reply_text(format_view_cart(rows), parse_mode="HTML")


async def become_waiter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if is_waiter(user.id):
        await update.effective_message.reply_text(
            "You're already registered as a waiter and can start deliveries.",
            reply_markup=home_keyboard("waiter"),
        )
        return
    portal_text = (
        "👨‍🍳 <b>Waiter Portal</b>\n\n"
        "Join our delivery team and start earning!\n\n"
        "🚀 <b>Benefits:</b>\n"
        "• Flexible working hours\n"
        "• Competitive earnings\n"
        "• Campus-based deliveries\n"
        "• Performance bonuses\n\n"
        "Choose an option below:"
    )
    await update.effective_message.reply_text(
        portal_text,
        parse_mode="HTML",
        reply_markup=waiter_portal_keyboard(),
    )


async def waiter_portal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split(":", 1)[1]
    if action == "register":
        context.user_data["waiter_register_mode"] = True
        context.user_data.pop("waiter_login_mode", None)
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=(
                "📝 <b>Waiter Registration</b>\n\n"
                "Please provide your details in this format:\n\n"
                "Name: Your Full Name\n"
                "Email: your.email@example.com\n"
                "Phone: 08012345678\n"
                "Gender: Male/Female"
            ),
            parse_mode="HTML",
        )
        return

    if action == "login":
        context.user_data["waiter_login_mode"] = True
        context.user_data.pop("waiter_register_mode", None)
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="🔑 Waiter Login\n\nPlease enter your waiter code (example: WAI123).",
        )


async def waiter_register_details_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiter_register_mode"):
        return

    user = update.effective_user
    details = (update.effective_message.text or "").strip()
    if len(details) < 20:
        await update.effective_message.reply_text("Please send complete registration details.")
        return

    waiter_request = db.create_or_update_waiter_request(
        user_id=user.id,
        public_user_id=generate_waiter_user_id(),
        full_name=user.full_name,
        details=details,
    )
    request_id = waiter_request["id"]
    waiter_user_id = waiter_request["public_user_id"] or f"WAI{request_id:03d}"
    context.user_data.pop("waiter_register_mode", None)
    await update.effective_message.reply_text(
        (
            "✅ Waiter registration submitted successfully.\n\n"
            f"User ID: {waiter_user_id}\n"
            "You will receive your waiter code once admin approves your request."
        )
    )

    admin_notice = (
        "👨‍🍳 <b>Pending Waiter Approval</b>\n\n"
        f"<b>User ID:</b> {waiter_user_id}\n"
        f"<b>Request ID:</b> {request_id}\n"
        f"<b>Telegram ID:</b> {user.id}\n"
        f"<b>Name:</b> {user.full_name}\n"
        f"<b>Details:</b> {details}"
    )
    for admin_id in settings.admin_ids:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_notice,
                parse_mode="HTML",
                reply_markup=waiter_request_actions_keyboard(request_id),
            )
        except Exception:
            logger.exception("Failed to send waiter request notification to admin %s", admin_id)


async def waiter_login_code_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiter_login_mode"):
        return

    user = update.effective_user
    code = (update.effective_message.text or "").strip().upper()
    if not re.fullmatch(r"WAI\d{3,6}", code):
        await update.effective_message.reply_text("Invalid code format. Example: WAI123")
        return

    activated = db.activate_waiter_by_code(user.id, code)
    if not activated:
        await update.effective_message.reply_text(
            "Waiter code not valid for your account yet. Complete registration or wait for admin approval.",
        )
        return

    _audit_waiter_upsert_by_user_id(user.id)

    context.user_data.pop("waiter_login_mode", None)
    await update.effective_message.reply_text(
        "✅ Waiter login successful. You are now online and can receive delivery orders.",
        reply_markup=home_keyboard("waiter"),
    )


async def waiter_portal_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("waiter_register_mode"):
        await waiter_register_details_step(update, context)
        return
    if context.user_data.get("waiter_login_mode"):
        await waiter_login_code_step(update, context)
        return


async def admin_secret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.effective_message.reply_text(format_unauthorized(), parse_mode="HTML")
        return

    if not super_admin_access_enabled():
        await update.effective_message.reply_text(
            "Super admin access is not configured on this server. Set SUPER_ADMIN_SECRET to enable it.",
        )
        return

    if not context.args:
        await update.effective_message.reply_text("Usage: /admin_secret <password>")
        return

    if context.args[0].strip() != settings.super_admin_secret:
        await update.effective_message.reply_text("Invalid admin secret.")
        return

    context.user_data["super_admin"] = True
    await update.effective_message.reply_text(
        f"🔐 Superior admin access granted.\n\n{format_admin_home()}",
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )


async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not super_admin_access_enabled():
        await update.effective_message.reply_text(
            "Super admin access is not configured on this server. Set SUPER_ADMIN_SECRET to enable it.",
        )
        return

    context.user_data["admin_login_mode"] = True
    await update.effective_message.reply_text(
        "🔐 <b>Admin Login</b>\n\nPlease enter the admin password.\nAfter login, use /order_analysis and /waiter_analysis for quick analytics.",
        parse_mode="HTML",
    )


async def admin_login_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("admin_login_mode"):
        return

    if not super_admin_access_enabled():
        context.user_data.pop("admin_login_mode", None)
        await update.effective_message.reply_text(
            "Super admin access is not configured on this server. Set SUPER_ADMIN_SECRET to enable it.",
        )
        return

    password = (update.effective_message.text or "").strip()
    if password != settings.super_admin_secret:
        await update.effective_message.reply_text("Invalid admin password.")
        return

    context.user_data.pop("admin_login_mode", None)
    context.user_data["super_admin"] = True
    await update.effective_message.reply_text(
        format_admin_home(),
        parse_mode="HTML",
        reply_markup=admin_panel_keyboard(),
    )


async def admin_waiter_management_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user

    if not has_super_admin_access(user.id, context):
        await query.answer("Please login via /admin first.", show_alert=True)
        return

    action = query.data.split(":", 1)[1]
    if action == "menu":
        await context.bot.send_message(
            chat_id=user.id,
            text=f"{format_waiter_management_menu()}\n\n{build_waiter_management_stats()}",
            parse_mode="HTML",
            reply_markup=admin_waiter_management_keyboard(),
        )
        return

    if action == "approve_waiters":
        pending = db.list_pending_waiter_requests(limit=20)
        if not pending:
            await context.bot.send_message(chat_id=user.id, text="✅ No pending waiter approvals.")
        else:
            for row in pending:
                public_id = row["public_user_id"] or f"WAI{row['id']:03d}"
                text = (
                    "👨‍🍳 <b>Pending Waiter Approval</b>\n\n"
                    f"<b>User ID:</b> {public_id}\n"
                    f"<b>Request ID:</b> {row['id']}\n"
                    f"<b>Telegram ID:</b> {row['user_id']}\n"
                    f"<b>Name:</b> {row['full_name']}\n"
                    f"<b>Details:</b> {row['details'] or 'N/A'}"
                )
                await context.bot.send_message(
                    chat_id=user.id,
                    text=text,
                    parse_mode="HTML",
                    reply_markup=waiter_request_actions_keyboard(row["id"]),
                )
        await context.bot.send_message(
            chat_id=user.id,
            text="🔙 Back to Waiter Management",
            reply_markup=admin_waiter_management_keyboard(),
        )
        return

    if action == "all_waiters":
        waiters = db.list_waiters(limit=100)
        if not waiters:
            await context.bot.send_message(chat_id=user.id, text="No waiters found.")
        else:
            lines = ["👥 <b>All Waiters</b>"]
            for row in waiters:
                code = row["waiter_code"] or "N/A"
                status = "Active" if row["role"] == "waiter" and row["waiter_online"] else "Inactive"
                lines.append(f"• {code} - {row['full_name']} ({status})")
            await context.bot.send_message(chat_id=user.id, text="\n".join(lines), parse_mode="HTML")
        await context.bot.send_message(
            chat_id=user.id,
            text="🔙 Back to Waiter Management",
            reply_markup=admin_waiter_management_keyboard(),
        )
        return

    if action == "performance":
        rows = db.waiter_performance(limit=30)
        if not rows:
            await context.bot.send_message(chat_id=user.id, text="No waiter performance data yet.")
        else:
            lines = ["📊 <b>Waiter Performance</b>"]
            for row in rows:
                code = row["waiter_code"] or f"UID{row['user_id']}"
                completed = row["completed_orders"] or 0
                active = row["active_orders"] or 0
                earnings = row["earnings"] or 0
                lines.append(f"• {code} | Completed: {completed} | Active: {active} | Earnings: ₦{earnings:,}")
            await context.bot.send_message(chat_id=user.id, text="\n".join(lines), parse_mode="HTML")
        await context.bot.send_message(
            chat_id=user.id,
            text="🔙 Back to Waiter Management",
            reply_markup=admin_waiter_management_keyboard(),
        )
        return

    if action == "deactivate_waiter":
        context.user_data["admin_deactivate_mode"] = True
        await context.bot.send_message(
            chat_id=user.id,
            text="Send waiter code or user ID to delete from the database. Example: WAI123 or 123456789",
        )


async def waiters_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not has_super_admin_access(user.id, context):
        await update.effective_message.reply_text("Run /admin first and log in.")
        return

    waiters = db.list_waiters(limit=100)
    if not waiters:
        await update.effective_message.reply_text("No waiters found in the database.")
        return

    lines = ["👥 <b>Waiters Database</b>"]
    for row in waiters:
        code = row["waiter_code"] or "N/A"
        status = "Active" if row["role"] == "waiter" and row["waiter_online"] else "Inactive"
        verified = "verified" if row["waiter_verified"] else "unverified"
        lines.append(f"• {code} - {row['full_name']} (ID: {row['user_id']}) - {status}, {verified}")

    await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


async def admin_deactivate_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("admin_deactivate_mode"):
        return

    user = update.effective_user
    if not has_super_admin_access(user.id, context):
        context.user_data.pop("admin_deactivate_mode", None)
        return

    identifier = (update.effective_message.text or "").strip().upper()
    row = db.deactivate_waiter(identifier)
    if not row:
        await update.effective_message.reply_text("Waiter not found. Send a valid waiter code or user ID.")
        return

    _audit_waiter_remove(int(row["user_id"]))

    context.user_data.pop("admin_deactivate_mode", None)
    await update.effective_message.reply_text(
        f"❌ Waiter deleted from database: {row['full_name']} (ID: {row['user_id']})",
        reply_markup=admin_waiter_management_keyboard(),
    )


async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("admin_login_mode"):
        await admin_login_router(update, context)
        return
    if context.user_data.get("topup_mode") == "await_amount":
        await topup_amount_step(update, context)
        return
    if context.user_data.get("admin_deactivate_mode"):
        await admin_deactivate_router(update, context)
        return
    if context.user_data.get("waiter_register_mode") or context.user_data.get("waiter_login_mode"):
        await waiter_portal_router(update, context)
        return
    if context.user_data.get("admin_invite_mode"):
        await admin_invite_router(update, context)
        return
    await home_button_router(update, context)


async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    if not has_super_admin_access(user.id, context):
        await query.answer("Run /admin_secret first.", show_alert=True)
        return

    data = query.data
    if data == "admin:menu":
        await context.bot.send_message(
            chat_id=user.id,
            text=format_admin_home(),
            parse_mode="HTML",
            reply_markup=admin_panel_keyboard(),
        )
        return

    if data == "admin:menu_waiters":
        await context.bot.send_message(
            chat_id=user.id,
            text=f"{format_waiter_management_menu()}\n\n{build_waiter_management_stats()}",
            parse_mode="HTML",
            reply_markup=admin_waiter_management_keyboard(),
        )
        return

    if data == "admin:menu_analytics" or data == "admin:order_analytics":
        report = db.order_analytics(limit=5)
        await context.bot.send_message(
            chat_id=user.id,
            text=format_order_analytics_dashboard(report),
            parse_mode="HTML",
            reply_markup=admin_analytics_keyboard(),
        )
        return

    if data == "admin:waiter_analytics":
        rows = db.waiter_performance(limit=30)
        await context.bot.send_message(
            chat_id=user.id,
            text=format_waiter_analytics_dashboard(rows),
            parse_mode="HTML",
            reply_markup=admin_panel_keyboard(),
        )
        return

    if data == "admin:menu_catalog":
        vendors = db.list_vendors()
        items = db.list_menu_items()
        await context.bot.send_message(
            chat_id=user.id,
            text=f"{format_catalog_menu()}\n\n{format_catalog_summary(vendors, items)}",
            parse_mode="HTML",
            reply_markup=admin_catalog_keyboard(),
        )
        return

    if data == "admin:catalog_list_vendors":
        vendors = db.list_vendors()
        await context.bot.send_message(
            chat_id=user.id,
            text=format_catalog_vendors(vendors),
            parse_mode="HTML",
            reply_markup=admin_catalog_keyboard(),
        )
        return

    if data == "admin:catalog_summary":
        vendors = db.list_vendors()
        items = db.list_menu_items()
        await context.bot.send_message(
            chat_id=user.id,
            text=format_catalog_summary(vendors, items),
            parse_mode="HTML",
            reply_markup=admin_catalog_keyboard(),
        )
        return

    if data == "admin:catalog_additem_help":
        await context.bot.send_message(
            chat_id=user.id,
            text=format_admin_additem_help(),
            parse_mode="HTML",
            reply_markup=admin_catalog_keyboard(),
        )
        return

    if data == "admin:catalog_view_items":
        items = db.list_menu_items()
        vendors_map = {v["id"]: v["name"] for v in db.list_vendors()}
        
        items_with_vendors = []
        for item in items:
            item_copy = dict(item)
            item_copy["vendor_name"] = vendors_map.get(item["vendor_id"], "Unknown")
            items_with_vendors.append(item_copy)
        
        text = format_catalog_items_list(items_with_vendors)
        await context.bot.send_message(
            chat_id=user.id,
            text=text,
            parse_mode="HTML",
            reply_markup=admin_catalog_keyboard(),
        )
        return

    if data.startswith("admin:catalog_remove:"):
        try:
            item_id = int(data.split(":")[-1])
        except (ValueError, IndexError):
            await query.answer("Invalid item ID.", show_alert=True)
            return
        
        item = db.get_menu_item(item_id)
        if not item:
            await query.answer("Item not found.", show_alert=True)
            return
        
        vendor = db.get_vendor(item["vendor_id"])
        vendor_name = vendor["name"] if vendor else "Unknown"
        
        # Delete the item
        db.delete_menu_item(item_id)
        
        text = format_item_removed_success(item["name"])
        await context.bot.send_message(
            chat_id=user.id,
            text=text,
            parse_mode="HTML",
            reply_markup=admin_catalog_keyboard(),
        )
        return

    if data.startswith("admin:catalog_item:"):
        try:
            item_id = int(data.split(":")[-1])
        except (ValueError, IndexError):
            await query.answer("Invalid item ID.", show_alert=True)
            return
        
        item = db.get_menu_item(item_id)
        if not item:
            await query.answer("Item not found.", show_alert=True)
            return
        
        text = format_item_management_options(item_id, item["name"])
        await context.bot.edit_message_text(
            chat_id=user.id,
            message_id=query.message.message_id,
            text=text,
            parse_mode="HTML",
            reply_markup=admin_catalog_detail_keyboard(item_id),
        )
        return

    if data == "admin:menu_quick":
        await context.bot.send_message(
            chat_id=user.id,
            text=format_admin_quick_actions(),
            parse_mode="HTML",
            reply_markup=admin_quick_actions_keyboard(),
        )
        return

    if data == "admin:pending_waiters":
        pending = db.list_pending_waiter_requests(limit=20)
        if not pending:
            await context.bot.send_message(chat_id=user.id, text="✅ No pending waiter approvals.")
            return

        for row in pending:
            public_id = row["public_user_id"] or f"WAI{row['id']:03d}"
            text = (
                "👨‍🍳 <b>Pending Waiter Approval</b>\n\n"
                f"<b>User ID:</b> {public_id}\n"
                f"<b>Request ID:</b> {row['id']}\n"
                f"<b>Telegram ID:</b> {row['user_id']}\n"
                f"<b>Name:</b> {row['full_name']}\n"
                f"<b>Details:</b> {row['details'] or 'N/A'}"
            )
            await context.bot.send_message(
                chat_id=user.id,
                text=text,
                parse_mode="HTML",
                reply_markup=waiter_request_actions_keyboard(row["id"]),
            )
        return

    if data == "admin:list_waiters":
        waiters = db.list_waiters(limit=50)
        if not waiters:
            await context.bot.send_message(chat_id=user.id, text="No registered waiters yet.")
            return
        lines = ["👨‍🍳 <b>Registered Waiters</b>"]
        for waiter in waiters:
            status = "online" if waiter["waiter_online"] else "offline"
            lines.append(f"• {waiter['full_name']} (ID: {waiter['user_id']}) - {status}")
        await context.bot.send_message(chat_id=user.id, text="\n".join(lines), parse_mode="HTML")
        return

    if data == "admin:invite_waiter":
        context.user_data["admin_invite_mode"] = True
        await context.bot.send_message(
            chat_id=user.id,
            text=format_admin_invite_prompt(),
            parse_mode="HTML",
        )
        return

    if data == "admin:logout":
        context.user_data.pop("super_admin", None)
        context.user_data.pop("admin_invite_mode", None)
        await context.bot.send_message(chat_id=user.id, text="🔒 Superior admin session closed.")
        return

    parts = data.split(":")
    if len(parts) == 3 and parts[1] in {"approve_waiter", "reject_waiter"}:
        try:
            request_id = int(parts[2])
        except ValueError:
            await query.answer("Invalid request id", show_alert=True)
            return

        if parts[1] == "approve_waiter":
            waiter_code = generate_waiter_code()
            result = db.approve_waiter_request(request_id, user.id, waiter_code)
            if not result:
                await context.bot.send_message(chat_id=user.id, text="Request already processed or not found.")
                return
            _audit_waiter_upsert_by_user_id(int(result["user_id"]))
            await context.bot.send_message(
                chat_id=user.id,
                text=f"✅ Waiter request {request_id} approved with code {waiter_code}.",
            )
            try:
                await context.bot.send_message(
                    chat_id=result["user_id"],
                    text=(
                        "✅ Your waiter registration has been approved.\n\n"
                        f"Your waiter code: {waiter_code}\n"
                        "Use Become a Waiter > Login with Code to activate your waiter account."
                    ),
                )
            except Exception:
                logger.exception("Failed to notify waiter approval for user %s", result["user_id"])
            return

        result = db.reject_waiter_request(request_id, user.id)
        if not result:
            await context.bot.send_message(chat_id=user.id, text="Request already processed or not found.")
            return
        await context.bot.send_message(chat_id=user.id, text=f"❌ Waiter request {request_id} rejected.")
        try:
            await context.bot.send_message(
                chat_id=result["user_id"],
                text="Your waiter request was not approved this time. Contact support for details.",
            )
        except Exception:
            logger.exception("Failed to notify waiter rejection for user %s", result["user_id"])


async def admin_invite_user_id_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not has_super_admin_access(user.id, context) or not context.user_data.get("admin_invite_mode"):
        return ConversationHandler.END

    text = (update.effective_message.text or "").strip()
    try:
        invited_user_id = int(text)
    except ValueError:
        await update.effective_message.reply_text("Enter a numeric Telegram user ID.")
        return ADMIN_INVITE_USER_ID

    waiter_code = generate_waiter_code()
    db.assign_waiter_invite(invited_user_id, f"Invited Waiter {invited_user_id}", waiter_code)
    _audit_waiter_upsert_by_user_id(invited_user_id)
    context.user_data.pop("admin_invite_mode", None)

    await update.effective_message.reply_text(
        f"✅ Waiter invited for user ID {invited_user_id}. Code: {waiter_code}",
        reply_markup=admin_panel_keyboard(),
    )
    try:
        await context.bot.send_message(
            chat_id=invited_user_id,
            text=(
                "✅ You have been invited as a PrimeChop waiter.\n\n"
                f"Your waiter code: {waiter_code}\n"
                "Tap Become a Waiter > Login with Code to activate your waiter access."
            ),
        )
    except Exception:
        logger.exception("Unable to notify invited waiter user %s", invited_user_id)
    return ConversationHandler.END


async def admin_invite_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not has_super_admin_access(user.id, context):
        return
    if not context.user_data.get("admin_invite_mode"):
        return
    await admin_invite_user_id_step(update, context)


async def customer_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(format_customer_support(), parse_mode="HTML")


async def view_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_waiter(user.id):
        await update.effective_message.reply_text(format_unauthorized(), parse_mode="HTML")
        return

    available_orders = db.list_unclaimed_paid_orders(limit=20)
    await update.effective_message.reply_text(
        format_waiter_order_book(available_orders),
        parse_mode="HTML",
        reply_markup=waiter_claim_list_keyboard(available_orders) if available_orders else None,
    )

    claimed_orders = db.list_waiter_claimed_orders(user.id, limit=10)
    if claimed_orders:
        lines = ["🧾 <b>Your Claimed Orders</b>", "Use /complete <order_id> after successful delivery."]
        for row in claimed_orders:
            order_ref = row["order_ref"] or str(row["id"])
            lines.append(f"#{order_ref} (ID: {row['id']}) - ₦{int(row['amount'] or 0):,}")
        await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")


def _can_view_admin_analytics(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not is_admin(user_id):
        return False
    if super_admin_access_enabled() and not has_super_admin_access(user_id, context):
        return False
    return True


async def order_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _can_view_admin_analytics(user.id, context):
        await update.effective_message.reply_text("Run /admin and login first.")
        return
    report = db.order_analytics(limit=5)
    await update.effective_message.reply_text(format_order_analytics_dashboard(report), parse_mode="HTML")


async def waiter_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not _can_view_admin_analytics(user.id, context):
        await update.effective_message.reply_text("Run /admin and login first.")
        return
    rows = db.waiter_performance(limit=30)
    await update.effective_message.reply_text(format_waiter_analytics_dashboard(rows), parse_mode="HTML")


async def order_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    rows = db.list_customer_orders(user.id, limit=10)
    if not rows:
        await update.effective_message.reply_text(format_empty_order_history(), parse_mode="HTML")
        return
    await update.effective_message.reply_text(format_order_history(rows), parse_mode="HTML")


async def terms(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(format_terms_and_conditions(), parse_mode="HTML")


async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete recent messages in the current chat where permitted by Telegram."""
    message = update.effective_message
    chat_id = update.effective_chat.id

    deleted_count = 0
    # Attempt to remove the latest 60 messages around the command point.
    for msg_id in range(message.message_id, max(0, message.message_id - 60), -1):
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            deleted_count += 1
        except Exception:
            continue

    if deleted_count == 0:
        await context.bot.send_message(
            chat_id=chat_id,
            text="I couldn't clear recent messages here due to Telegram permissions.",
        )


async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    role = user_role(user.id)
    db.upsert_user(user.id, user.full_name, role=role)

    row = db.get_user(user.id)
    balance = row["wallet_balance"] if row else 0
    text = format_wallet_info(balance, user.full_name)
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.upsert_user(user.id, user.full_name, role=user_role(user.id))

    if not context.args:
        await start_topup_flow(update, context)
        return

    try:
        amount = int(context.args[0])
        if amount <= 0:
            raise ValueError
    except ValueError:
        text = format_invalid_amount()
        await update.effective_message.reply_text(text, parse_mode="HTML")
        return

    await initialize_topup_for_user(
        user=user,
        chat_id=update.effective_chat.id,
        amount=amount,
        context=context,
    )


async def topup_amount_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("topup_mode") != "await_amount":
        return

    user = update.effective_user
    raw_amount = (update.effective_message.text or "").strip().replace(",", "")
    try:
        amount = int(raw_amount)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.effective_message.reply_text(format_invalid_amount(), parse_mode="HTML")
        await update.effective_message.reply_text(format_topup_amount_prompt(), parse_mode="HTML")
        return

    context.user_data.pop("topup_mode", None)
    await initialize_topup_for_user(
        user=user,
        chat_id=update.effective_chat.id,
        amount=amount,
        context=context,
    )


async def confirm_topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        text = format_unauthorized()
        await update.effective_message.reply_text(text, parse_mode="HTML")
        return

    if not context.args:
        await update.effective_message.reply_text("Usage: /confirm_topup <tx_ref>")
        return

    tx_ref = context.args[0].strip()
    tx = db.mark_wallet_tx_success(tx_ref)
    if not tx:
        await update.effective_message.reply_text("Pending transaction not found for that reference.")
        return

    text = format_topup_success(tx["amount"])
    await update.effective_message.reply_text(text, parse_mode="HTML")
    await context.bot.send_message(
        chat_id=tx["user_id"],
        text=format_topup_success(tx["amount"]),
        parse_mode="HTML",
    )


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    vendors = _get_order_vendor_rows()
    if not vendors:
        await update.effective_message.reply_text(format_menu_empty(), parse_mode="HTML")
        return

    await update.effective_message.reply_text(
        "🏪 <b>Choose a Vendor</b>\n\nSelect where you want to order from.",
        parse_mode="HTML",
        reply_markup=vendor_selection_keyboard(vendors),
    )


async def order_vendor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    customer = query.from_user
    db.upsert_user(customer.id, customer.full_name, role=user_role(customer.id))

    vendor_id = int(query.data.split(":")[2])
    vendor = db.get_vendor(vendor_id)
    if not vendor:
        await query.answer("Vendor not found.", show_alert=True)
        return ConversationHandler.END

    draft = _ensure_order_draft(context)
    draft["vendor_id"] = vendor_id
    draft["vendor_name"] = vendor["name"]
    context.user_data["order_draft"] = draft

    items = db.list_menu_items_by_vendor(vendor_id)
    if not items:
        await query.edit_message_text(
            f"{vendor['name']} has no available items yet.",
            reply_markup=vendor_selection_keyboard(_get_order_vendor_rows()),
        )
        return ORDER_VENDOR

    await query.edit_message_text(
        format_menu_vendor_caption(vendor["name"]),
        parse_mode="HTML",
        reply_markup=vendor_items_keyboard(items, vendor_id),
    )
    return ORDER_ITEM


async def order_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    customer = query.from_user
    db.upsert_user(customer.id, customer.full_name, role=user_role(customer.id))

    item_id = int(query.data.split(":")[2])
    item = db.get_menu_item(item_id)
    if not item:
        if query.message and query.message.caption:
            await query.edit_message_caption(caption="This menu item is no longer available.")
        else:
            await query.edit_message_text("This menu item is no longer available.")
        return ConversationHandler.END

    draft = _ensure_order_draft(context)
    vendor = db.get_vendor(item["vendor_id"]) if item["vendor_id"] else None
    draft.update({
        "vendor_id": item["vendor_id"],
        "vendor_name": vendor["name"] if vendor else settings.cafeteria_name,
        "item_id": item_id,
        "item_name": item["name"],
        "amount": item["price"],
    })
    await _send_hall_selection(update, context)
    return ORDER_HALL


async def order_hall_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    draft = _ensure_order_draft(context)
    hall_index = int(query.data.split(":")[2])
    if hall_index < 0 or hall_index >= len(settings.delivery_halls):
        await query.answer("Invalid hall selection.", show_alert=True)
        return ConversationHandler.END

    hall_name = settings.delivery_halls[hall_index]
    draft["hall_name"] = hall_name
    context.user_data["order_draft"] = draft

    await query.edit_message_text(
        format_room_prompt_with_hall(hall_name),
        parse_mode="HTML",
    )
    return ORDER_ROOM


async def order_room_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = context.user_data.get("order_draft", {})
    if not draft:
        await update.effective_message.reply_text("Order session expired. Tap Place an Order and try again.")
        return ConversationHandler.END

    room_text = (update.effective_message.text or "").strip().upper().replace(" ", "")
    room_number = None
    hall_prefixed = re.fullmatch(r"[A-H](\d{1,4})", room_text)
    if hall_prefixed:
        room_number = hall_prefixed.group(1)
    elif re.fullmatch(r"\d{1,4}", room_text):
        room_number = room_text

    if not room_number:
        await update.effective_message.reply_text(format_room_invalid())
        await update.effective_message.reply_text(format_room_prompt_with_hall(draft.get("hall_name", "your hall")))
        return ORDER_ROOM

    draft["room_number"] = room_number
    context.user_data["order_draft"] = draft
    await _finalize_order_checkout(update, context)


async def order_flow_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("order_draft", None)
    await update.effective_message.reply_text("Order flow cancelled.")
    return ConversationHandler.END


async def claim_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    waiter = query.from_user
    if not is_waiter(waiter.id):
        await query.answer("Only registered waiters can claim orders.", show_alert=True)
        return

    db.upsert_user(waiter.id, waiter.full_name, role="waiter")

    order_id = int(query.data.split(":")[1])
    claimed = db.claim_order(order_id, waiter.id)

    if not claimed:
        await query.answer("Order already claimed by another waiter.", show_alert=True)
        return

    order = db.get_order(order_id)
    if order:
        await context.bot.send_message(
            chat_id=order["customer_id"],
            text=format_order_claimed(order_id, waiter.full_name),
            parse_mode="HTML",
        )

    await query.edit_message_text(f"Order #{order_id} claimed successfully by you.")


async def topup_preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    db.upsert_user(user.id, user.full_name, role=user_role(user.id))

    amount = int(query.data.split(":")[1])
    await initialize_topup_for_user(
        user=user,
        chat_id=query.message.chat_id,
        amount=amount,
        context=context,
    )


async def topup_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    action = query.data.split(":", 1)[1]
    if action == "start":
        await start_topup_flow(update, context)
        return
    if action == "custom":
        await start_custom_topup_flow(update, context)
        return


async def home_button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()
    normalized = text.lower()

    if normalized in {"start", "/start"}:
        await start(update, context)
        return
    if text == BTN_PLACE_ORDER or normalized in {"place order", "place an order", "/place_order"}:
        await place_order(update, context)
        return
    if text == BTN_VIEW_CART or normalized in {"view cart", "/view_cart"}:
        await view_cart(update, context)
        return
    if text == BTN_BECOME_WAITER or normalized in {"become waiter", "become a waiter", "/become_waiter"}:
        await become_waiter(update, context)
        return
    if text == BTN_CUSTOMER_SUPPORT or normalized in {"customer support", "/customer_support"}:
        await customer_support(update, context)
        return
    if text == BTN_ORDER_HISTORY or normalized in {"order history", "/order_history"}:
        if is_waiter(update.effective_user.id):
            await view_orders(update, context)
        else:
            await order_history(update, context)
        return
    if text == BTN_TERMS or normalized in {"terms", "terms and conditions", "terms & conditions", "/terms"}:
        await terms(update, context)
        return
    if text == BTN_MENU:
        await menu(update, context)
        return
    if normalized == "menu":
        await menu(update, context)
        return
    if normalized == "wallet":
        await wallet(update, context)
        return
    if normalized == "help":
        await help_cmd(update, context)
        return
    if text == BTN_WAITER_ONLINE:
        await waiter_online(update, context)
        return
    if text == BTN_WAITER_OFFLINE:
        await waiter_offline(update, context)
        return
    if text == BTN_WALLET:
        await wallet(update, context)
        return
    if text == BTN_VIEW_ORDERS or normalized in {"view orders", "order book", "/view_orders"}:
        await view_orders(update, context)
        return
    if text == BTN_ADMIN_ADDITEM:
        await additem_start(update, context)
        return


async def waiter_online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_waiter(user.id):
        text = format_unauthorized()
        await update.effective_message.reply_text(text, parse_mode="HTML")
        return

    db.upsert_user(user.id, user.full_name, role="waiter")
    db.set_waiter_online(user.id, True)
    _audit_waiter_upsert_by_user_id(user.id)
    text = format_waiter_online_success()
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def waiter_offline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_waiter(user.id):
        text = format_unauthorized()
        await update.effective_message.reply_text(text, parse_mode="HTML")
        return

    db.set_waiter_online(user.id, False)
    _audit_waiter_upsert_by_user_id(user.id)
    text = format_waiter_offline_success()
    await update.effective_message.reply_text(text, parse_mode="HTML")


async def complete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_waiter(user.id):
        text = format_unauthorized()
        await update.effective_message.reply_text(text, parse_mode="HTML")
        return

    if not context.args:
        await update.effective_message.reply_text("Usage: /complete <order_id>")
        return

    try:
        order_id = int(context.args[0])
    except ValueError:
        await update.effective_message.reply_text("Order ID must be a number.")
        return

    ok = db.complete_order(order_id, user.id)
    if not ok:
        await update.effective_message.reply_text("Unable to complete. Make sure you claimed that order first.")
        return

    order = db.get_order(order_id)
    if not order:
        await update.effective_message.reply_text("Order not found.")
        return

    _audit_order_event(order, event="order_completed", payment_status="confirmed")

    text = format_order_completed_waiter(order_id, order["waiter_share"], order["platform_share"])
    await update.effective_message.reply_text(text, parse_mode="HTML")
    await context.bot.send_message(
        chat_id=order["customer_id"],
        text=format_order_completed(order_id, settings.cafeteria_name),
        parse_mode="HTML",
    )


async def additem_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        text = format_unauthorized()
        await update.effective_message.reply_text(text, parse_mode="HTML")
        return ConversationHandler.END

    if update.effective_callback_query:
        await update.effective_callback_query.answer()

    runtime.add_item_draft[user.id] = {}
    text = format_admin_additem_start()
    await update.effective_message.reply_text(text, parse_mode="HTML")
    return ADD_ITEM_NAME


async def additem_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    runtime.add_item_draft.setdefault(user.id, {})["name"] = update.effective_message.text.strip()
    text = "Which vendor should this item belong to?\n\nExample: Bread Warmer Restaurant"
    await update.effective_message.reply_text(text, parse_mode="HTML")
    return ADD_ITEM_VENDOR


async def additem_vendor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    vendor_name = (update.effective_message.text or "").strip()
    if not vendor_name:
        await update.effective_message.reply_text("Please send a valid vendor name.")
        return ADD_ITEM_VENDOR

    vendor = db.upsert_vendor(vendor_name)
    runtime.add_item_draft.setdefault(user.id, {})["vendor_id"] = vendor["id"]
    runtime.add_item_draft.setdefault(user.id, {})["vendor_name"] = vendor["name"]
    text = format_admin_additem_price()
    await update.effective_message.reply_text(text, parse_mode="HTML")
    return ADD_ITEM_PRICE


async def additem_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        price = int(update.effective_message.text.strip())
        if price <= 0:
            raise ValueError
    except ValueError:
        text = format_invalid_amount()
        await update.effective_message.reply_text(text, parse_mode="HTML")
        return ADD_ITEM_PRICE

    runtime.add_item_draft.setdefault(user.id, {})["price"] = price
    text = format_admin_additem_image()
    await update.effective_message.reply_text(text, parse_mode="HTML")
    return ADD_ITEM_IMAGE


async def additem_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    image_file_id = None
    image_url = None

    if update.effective_message.photo:
        image_file_id = update.effective_message.photo[-1].file_id
    elif update.effective_message.text:
        text = update.effective_message.text.strip()
        if text.lower().startswith("http://") or text.lower().startswith("https://"):
            image_url = text
        else:
            await update.effective_message.reply_text("Send a valid URL or upload a photo, or /skip.")
            return ADD_ITEM_IMAGE

    runtime.add_item_draft.setdefault(user.id, {})["image_file_id"] = image_file_id
    runtime.add_item_draft.setdefault(user.id, {})["image_url"] = image_url
    await additem_save(user.id, update, context)
    return ConversationHandler.END


async def additem_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    runtime.add_item_draft.setdefault(user.id, {})["image_file_id"] = None
    runtime.add_item_draft.setdefault(user.id, {})["image_url"] = None
    await additem_save(user.id, update, context)
    return ConversationHandler.END


async def additem_save(user_id: int, update: Update, context: ContextTypes.DEFAULT_TYPE):
    draft = runtime.add_item_draft.get(user_id, {})
    if not draft.get("name") or not draft.get("price") or not draft.get("vendor_id"):
        await update.effective_message.reply_text("Item incomplete. Try /additem again.")
        return

    image_url = draft.get("image_url") or settings.placeholder_image_url
    item_id = db.add_menu_item(
        vendor_id=draft["vendor_id"],
        name=draft["name"],
        price=draft["price"],
        image_file_id=draft.get("image_file_id"),
        image_url=image_url,
    )

    text = format_admin_additem_success(item_id, draft["name"], draft["price"])
    await update.effective_message.reply_text(text, reply_markup=home_keyboard("admin"), parse_mode="HTML")
    runtime.add_item_draft.pop(user_id, None)


async def additem_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    runtime.add_item_draft.pop(user.id, None)
    await update.effective_message.reply_text("Item creation cancelled.")
    return ConversationHandler.END


def bootstrap_menu_if_empty():
    db.seed_vendors(settings.order_vendors)
    for vendor_name, menu_items in FIXED_VENDOR_PRODUCTS.items():
        vendor = db.upsert_vendor(vendor_name)
        db.sync_vendor_menu(vendor["id"], menu_items, settings.placeholder_image_url)


async def log_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled exception while processing update: %s", context.error)


def main_with_retry():
    """Run the bot with exponential backoff retry on network errors."""
    import time
    from telegram.error import NetworkError, TelegramError

    max_retries = 5
    retry_count = 0
    base_wait = 5  # Start with 5 seconds
    
    while retry_count < max_retries:
        try:
            main()
            break  # Exit if successful
        except (NetworkError, TelegramError) as e:
            retry_count += 1
            wait_time = base_wait * (2 ** (retry_count - 1))  # Exponential backoff
            logger.warning(
                f"Network error occurred: {e}. Retry {retry_count}/{max_retries} in {wait_time} seconds..."
            )
            if retry_count < max_retries:
                time.sleep(wait_time)
            else:
                logger.error(f"Failed to start bot after {max_retries} retries. Exiting.")
                raise
        except KeyboardInterrupt:
            logger.info("Bot interrupted by user.")
            break
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)
            break


def main():
    db.init()
    existing_waiters = [dict(row) for row in db.list_waiters(limit=5000)]
    audit_trail.sync_waiters(existing_waiters)
    bootstrap_menu_if_empty()
    start_korapay_callback_server()
    asyncio.set_event_loop(asyncio.new_event_loop())

    async def post_init(application: Application):
        await application.bot.set_my_commands(
            [
                BotCommand("start", "Show welcome message"),
                BotCommand("place_order", "Browse menu and place an order"),
                BotCommand("view_cart", "View your cart"),
                BotCommand("become_waiter", "Apply to become a waiter"),
                BotCommand("customer_support", "Contact support"),
                BotCommand("order_history", "View recent orders"),
                BotCommand("terms", "View terms and conditions"),
                BotCommand("clear", "Clear recent chat messages"),
                BotCommand("wallet", "Check wallet balance"),
                BotCommand("menu", "Open food menu"),
                BotCommand("confirm_order", "Confirm an order payment by tx ref"),
                BotCommand("view_orders", "Waiter order book (available and claimed)"),
                BotCommand("waiters", "View the waiter database"),
                BotCommand("order_analysis", "Admin order analytics"),
                BotCommand("waiter_analysis", "Admin waiter analytics"),
            ]
        )

    request = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30, pool_timeout=30)
    updates_request = HTTPXRequest(connect_timeout=30, read_timeout=30, write_timeout=30, pool_timeout=30)
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .request(request)
        .get_updates_request(updates_request)
        .post_init(post_init)
        .build()
    )

    add_item_handler = ConversationHandler(
        entry_points=[
            CommandHandler("additem", additem_start),
            CallbackQueryHandler(additem_start, pattern=r"^admin:catalog_additem_start$"),
        ],
        states={
            ADD_ITEM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, additem_name)],
            ADD_ITEM_VENDOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, additem_vendor)],
            ADD_ITEM_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, additem_price)],
            ADD_ITEM_IMAGE: [
                CommandHandler("skip", additem_skip),
                MessageHandler((filters.PHOTO | filters.TEXT) & ~filters.COMMAND, additem_image),
            ],
        },
        fallbacks=[CommandHandler("cancel", additem_cancel)],
    )

    order_flow_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(order_vendor_callback, pattern=r"^catalog:vendor:\d+$")],
        states={
            ORDER_ITEM: [CallbackQueryHandler(order_item_callback, pattern=r"^catalog:item:\d+$")],
            ORDER_HALL: [CallbackQueryHandler(order_hall_callback, pattern=r"^catalog:hall:\d+$")],
            ORDER_ROOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, order_room_step)],
        },
        fallbacks=[CommandHandler("cancel", order_flow_cancel)],
        per_chat=True,
        per_user=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("admin_secret", admin_secret))
    app.add_handler(CommandHandler("place_order", place_order))
    app.add_handler(CommandHandler("view_cart", view_cart))
    app.add_handler(CommandHandler("become_waiter", become_waiter))
    app.add_handler(CommandHandler("customer_support", customer_support))
    app.add_handler(CommandHandler("order_history", order_history))
    app.add_handler(CommandHandler("terms", terms))
    app.add_handler(CommandHandler("clear", clear_chat))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("wallet", wallet))
    app.add_handler(CommandHandler("topup", topup))
    app.add_handler(CommandHandler("confirm_topup", confirm_topup))
    app.add_handler(CommandHandler("confirm_order", confirm_order_payment))
    app.add_handler(CommandHandler("view_orders", view_orders))
    app.add_handler(CommandHandler("waiters", waiters_db))
    app.add_handler(CommandHandler("order_analysis", order_analysis))
    app.add_handler(CommandHandler("waiter_analysis", waiter_analysis))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("waiter_online", waiter_online))
    app.add_handler(CommandHandler("waiter_offline", waiter_offline))
    app.add_handler(CommandHandler("complete", complete))
    app.add_handler(add_item_handler)
    app.add_handler(order_flow_handler)

    app.add_handler(CallbackQueryHandler(admin_waiter_management_callback, pattern=r"^adminwm:.*$"))
    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern=r"^admin:.*$"))
    app.add_handler(CallbackQueryHandler(order_catalog_navigation_callback, pattern=r"^catalog:(back_vendors|back_items)$"))
    app.add_handler(CallbackQueryHandler(waiter_portal_callback, pattern=r"^waiter_portal:(login|register)$"))
    app.add_handler(CallbackQueryHandler(claim_order_callback, pattern=r"^claim:\d+$"))
    app.add_handler(CallbackQueryHandler(topup_preset_callback, pattern=r"^topup:\d+$"))
    app.add_handler(CallbackQueryHandler(topup_action_callback, pattern=r"^topup:(start|custom)$"))
    app.add_handler(CallbackQueryHandler(start_place_order_callback, pattern=r"^start:place_order$"))
    app.add_handler(CallbackQueryHandler(order_action_callback, pattern=r"^order_action:(my_orders|main_menu)$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))
    app.add_error_handler(log_error)

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        bootstrap_retries=-1,
    )


if __name__ == "__main__":
    main_with_retry()
