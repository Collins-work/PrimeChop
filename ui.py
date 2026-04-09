"""
Enhanced UI components for Primechop bot.
Provides formatted message templates and improved keyboard layouts.
"""

import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


# ==================== EMOJI CONSTANTS ====================
EMOJI_MENU = "🍽️"
EMOJI_WALLET = "👛"
EMOJI_TOPUP = "💳"
EMOJI_HELP = "❓"
EMOJI_ONLINE = "🟢"
EMOJI_OFFLINE = "🔴"
EMOJI_ADD = "➕"
EMOJI_SUCCESS = "✅"
EMOJI_PENDING = "⏳"
EMOJI_ERROR = "❌"
EMOJI_INFO = "ℹ️"
EMOJI_DELIVERY = "🚚"
EMOJI_FOOD = "🍜"
EMOJI_MONEY = "💰"
EMOJI_BACK = "↩️"
EMOJI_CLOSE = "🔚"
EMOJI_STAR = "⭐"
EMOJI_WAITER = "🧑‍🍳"
EMOJI_CUSTOMER = "👤"
EMOJI_ADMIN = "🔧"
EMOJI_DIVIDER = "━━━━━━━━━━━━━━━━━"


# ==================== BUTTON TEXT ====================
BTN_PLACE_ORDER = "🛒 Place an Order"
BTN_VIEW_CART = "🛍️ View Cart"
BTN_BECOME_WAITER = f"{EMOJI_WAITER} Become a Waiter"
BTN_CUSTOMER_SUPPORT = "📞 Customer Support"
BTN_ORDER_HISTORY = "📋 Order History"
BTN_TERMS = "📄 Terms & Conditions"
BTN_MENU = f"{EMOJI_MENU} Menu"
BTN_WALLET = f"{EMOJI_WALLET} Wallet"
BTN_TOPUP = f"{EMOJI_TOPUP} Top Up"
BTN_HELP = f"{EMOJI_HELP} Help"
BTN_WAITER_ONLINE = f"{EMOJI_ONLINE} Go Online"
BTN_WAITER_OFFLINE = f"{EMOJI_OFFLINE} Go Offline"
BTN_VIEW_ORDERS = "📦 View Orders"
BTN_EXIT_WAITER_MODE = "🚪 Exit Waiter Mode"
BTN_ADMIN_ADDITEM = f"{EMOJI_ADD} Add Item"


# ==================== KEYBOARD BUILDERS ====================
def home_keyboard(role: str) -> ReplyKeyboardMarkup:
    """Build home keyboard based on user role."""
    if role == "waiter":
        rows = [
            [KeyboardButton(BTN_VIEW_ORDERS)],
            [KeyboardButton(BTN_WAITER_ONLINE), KeyboardButton(BTN_WAITER_OFFLINE)],
            [KeyboardButton(BTN_ORDER_HISTORY), KeyboardButton(BTN_CUSTOMER_SUPPORT)],
            [KeyboardButton(BTN_EXIT_WAITER_MODE)],
        ]
        return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)

    rows = [
        [KeyboardButton(BTN_PLACE_ORDER), KeyboardButton(BTN_VIEW_CART)],
        [KeyboardButton(BTN_BECOME_WAITER), KeyboardButton(BTN_CUSTOMER_SUPPORT)],
        [KeyboardButton(BTN_ORDER_HISTORY), KeyboardButton(BTN_TERMS)],
        [KeyboardButton(BTN_WALLET), KeyboardButton(BTN_MENU)],
    ]
    if role == "admin":
        rows.append([KeyboardButton(BTN_ADMIN_ADDITEM)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)


def topup_presets_keyboard() -> InlineKeyboardMarkup:
    """Show quick top-up amount presets."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("₦1000", callback_data="topup:1000"),
                InlineKeyboardButton("₦2000", callback_data="topup:2000"),
                InlineKeyboardButton("₦5000", callback_data="topup:5000"),
            ],
            [
                InlineKeyboardButton("₦10000", callback_data="topup:10000"),
                InlineKeyboardButton("₦20000", callback_data="topup:20000"),
            ],
            [InlineKeyboardButton("✍️ Enter custom amount", callback_data="topup:custom")],
        ]
    )


def payment_method_keyboard(order_ref: str, wallet_balance: int, amount: int) -> InlineKeyboardMarkup:
    """Build payment options keyboard for checkout."""
    rows = []
    if wallet_balance >= amount:
        rows.append([InlineKeyboardButton(f"👛 Pay with Wallet (₦{wallet_balance:,})", callback_data=f"checkout:wallet:{order_ref}")])
    else:
        rows.append([InlineKeyboardButton("💳 Top up wallet", callback_data="topup:start")])
    rows.append([InlineKeyboardButton("💳 Pay with KoraPay", callback_data=f"checkout:korapay:{order_ref}")])
    rows.append([InlineKeyboardButton("❌ Cancel checkout", callback_data=f"checkout:cancel:{order_ref}")])
    return InlineKeyboardMarkup(rows)


def wallet_actions_keyboard() -> InlineKeyboardMarkup:
    """Build wallet action buttons."""
    return InlineKeyboardMarkup([])


def menu_item_keyboard(item_id: int) -> InlineKeyboardMarkup:
    """Build keyboard for ordering a menu item."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"{EMOJI_FOOD} Order this", callback_data=f"order:{item_id}")]]
    )


def vendor_selection_keyboard(vendors) -> InlineKeyboardMarkup:
    """Build keyboard for selecting a vendor - displayed as one full-width button per row."""
    rows = []
    for vendor in vendors:
        vendor_display = re.sub(r"\s+", " ", str(vendor["name"]).strip())
        rows.append([InlineKeyboardButton(vendor_display, callback_data=f"catalog:vendor:{vendor['id']}")])
    return InlineKeyboardMarkup(rows)


def vendor_items_keyboard(items, vendor_id: int) -> InlineKeyboardMarkup:
    """Build keyboard for selecting an item under a vendor."""
    rows = []
    for item in items:
        rows.append([InlineKeyboardButton(item["name"], callback_data=f"catalog:item:{item['id']}")])
    rows.append([InlineKeyboardButton("🔙 Back to Vendors", callback_data="catalog:back_vendors")])
    return InlineKeyboardMarkup(rows)


def hall_selection_keyboard(halls) -> InlineKeyboardMarkup:
    """Build keyboard for selecting a delivery hall."""
    rows = []
    current_row = []
    for index, hall_name in enumerate(halls):
        current_row.append(InlineKeyboardButton(hall_name, callback_data=f"catalog:hall:{index}"))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton("🔙 Back to Items", callback_data="catalog:back_items")])
    return InlineKeyboardMarkup(rows)


def order_claim_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Build keyboard for waiter to claim order."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"{EMOJI_DELIVERY} Claim order", callback_data=f"claim:{order_id}")]]
    )


def pay_now_keyboard(payment_url: str, label: str = None) -> InlineKeyboardMarkup:
    """Build keyboard with payment link."""
    button_label = label or f"{EMOJI_TOPUP} Pay Now"
    return InlineKeyboardMarkup([[InlineKeyboardButton(button_label, url=payment_url)]])


def start_place_order_keyboard() -> InlineKeyboardMarkup:
    """Build start-banner call-to-action keyboard."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(BTN_PLACE_ORDER, callback_data="start:place_order")]]
    )


def order_post_actions_keyboard() -> InlineKeyboardMarkup:
    """Build post-order action buttons for customer."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📦 My Orders", callback_data="order_action:my_orders")],
            [InlineKeyboardButton("🏠 Main Menu", callback_data="order_action:main_menu")],
        ]
    )


# ==================== MESSAGE FORMATTERS ====================
def format_start_message(cafeteria_name: str) -> str:
    """Format welcome/start message."""
    return (
        "Welcome to PrimeChop!\n"
        "Your cravings, our priority. Fresh meals, fast delivery — let’s get started!"
    )


def format_help_message() -> str:
    """Format help/info message."""
    return (
        f"{EMOJI_INFO} <b>Help & Information</b>\n\n"
        f"{EMOJI_DIVIDER}\n\n"
        f"<b>{EMOJI_FOOD} Menu</b>\n"
        f"Browse available food items and place orders\n\n"
        f"<b>{EMOJI_WALLET} Wallet</b>\n"
        f"View your wallet balance & transaction history\n\n"
        f"<b>{EMOJI_TOPUP} Top Up</b>\n"
        f"Add funds to your wallet for faster checkout\n\n"
        f"<b>{EMOJI_DELIVERY} Order Status</b>\n"
        f"Orders are matched with online waiters automatically\n\n"
        f"{EMOJI_DIVIDER}\n\n"
        f"<b>Questions?</b>\n"
        f"Contact support or speak with a waiter."
    )


def format_become_waiter_success(name: str) -> str:
    """Format successful waiter registration message."""
    return (
        f"{EMOJI_SUCCESS} <b>Waiter Profile Activated</b>\n\n"
        f"{EMOJI_WAITER} <b>Name:</b> {name}\n"
        f"{EMOJI_ONLINE} <b>Status:</b> Online\n\n"
        f"You can now receive and claim delivery orders."
    )


def format_customer_support() -> str:
    """Format customer support help text."""
    return (
        f"{EMOJI_INFO} <b>Customer Support</b>\n\n"
        f"Need help with an order, payment, or delivery?\n"
        f"Contact us directly:\n"
        f"Phone: 09116002889\n"
        f"Telegram: @ItsClins"
    )


def format_terms_and_conditions() -> str:
    """Format short terms and conditions text."""
    return (
        f"<b>Terms & Conditions</b>\n\n"
        f"1. Orders are processed based on menu availability.\n"
        f"2. Wallet top-ups are credited after successful payment confirmation.\n"
        f"3. Waiters are assigned on a first-claim basis when online.\n"
        f"4. Completed deliveries cannot be reversed automatically.\n"
        f"5. By using this bot, you agree to these terms."
    )


def format_empty_order_history() -> str:
    """Format message when user has no order history."""
    return f"{EMOJI_INFO} You have not placed any orders yet."


def format_empty_cart() -> str:
    """Format empty cart/active-order message."""
    return (
        "🛍️ <b>Your Cart</b>\n\n"
        "Nothing in your cart yet. Tap <b>Place an Order</b> to make your first purchase."
    )


def format_view_cart(rows) -> str:
    """Format active orders shown in cart view."""
    lines = ["🛍️ <b>Your Cart Orders</b>"]
    for row in rows:
        item_name = row["item_name"] or f"Item #{row['item_id']}"
        order_ref = row["order_ref"] or f"{row['id']}"
        hall_name = row["hall_name"] or "Unknown hall"
        room_number = row["room_number"] or "N/A"
        lines.append(f"#{order_ref} - {item_name} - ₦{row['amount']:,} - {row['status']}")
        lines.append(f"   Delivery: {hall_name} - Room {room_number}")
    return "\n".join(lines)


def format_order_history(rows) -> str:
    """Format compact order history list for a customer."""
    lines = [f"{EMOJI_DELIVERY} <b>Your Recent Orders</b>"]
    for row in rows:
        item_name = row["item_name"] or f"Item #{row['item_id']}"
        order_ref = row["order_ref"] or f"{row['id']}"
        details = row["order_details"] or "No extra note"
        room = row["room_number"] or "N/A"
        hall_name = row["hall_name"] or "Unknown hall"
        lines.append(f"#{order_ref} - {item_name} - ₦{row['amount']:,} - {row['status']}")
        lines.append(f"   Delivery: {hall_name} - Room {room}")
        lines.append(f"   Note: {details}")
    return "\n".join(lines)


def format_order_details_prompt(item_name: str, price: int) -> str:
    """Prompt user to enter detailed order instructions."""
    return (
        "📝 <b>Order Details</b>\n\n"
        f"<b>Item:</b> {item_name}\n"
        f"<b>Price:</b> ₦{price:,}\n\n"
        "Specify your order in detail.\n"
        "Example:\n"
        "• Abacha and Nkwobi x1\n"
        "• Compulsory pack x1\n"
        "• Peppered Gizzard x3"
    )


def format_vendor_prompt() -> str:
    """Prompt user to choose a vendor."""
    return (
        "🏪 <b>Choose a Vendor</b>\n\n"
        "Select the vendor you want to order from below."
    )


def format_vendor_items_prompt(vendor_name: str) -> str:
    """Prompt user to choose an item from a vendor."""
    return (
        f"🍽️ <b>{vendor_name}</b>\n\n"
        "Choose the food you want to order."
    )


def format_hall_prompt(item_name: str, vendor_name: str) -> str:
    """Prompt user to choose their delivery hall."""
    return (
        "🏫 <b>Select Delivery Hall</b>\n\n"
        f"<b>Vendor:</b> {vendor_name}\n"
        f"<b>Item:</b> {item_name}\n\n"
        "Choose your hall below."
    )


def format_room_prompt_with_hall(hall_name: str) -> str:
    """Prompt user to enter room number after hall selection."""
    return (
        f"🏠 <b>{hall_name}</b>\n\n"
        "Enter your room number.\n"
        "Examples: E204 or 308"
    )


def format_order_payment_ready(
    order_ref: str,
    vendor_name: str,
    item_name: str,
    hall_name: str,
    room_number: str,
    amount: int,
    payment_provider: str,
) -> str:
    """Format the checkout message shown before payment is completed."""
    provider_label = payment_provider.title() if payment_provider else "Payment"
    return (
        f"✅ <b>Order Ready for Payment</b>\n\n"
        f"📦 <b>Order ID:</b> #{order_ref}\n"
        f"🏪 <b>Vendor:</b> {vendor_name}\n"
        f"🍽️ <b>Item:</b> {item_name}\n"
        f"🏫 <b>Delivery:</b> {hall_name} - Room {room_number}\n"
        f"💰 <b>Amount:</b> ₦{amount:,}\n"
        f"💳 <b>Pay with:</b> {provider_label}\n\n"
        "Tap the button below to complete payment inside the app."
    )


def format_room_prompt() -> str:
    """Prompt user to enter room location in accepted format."""
    return (
        "Please enter your location in this format:\n"
        "Wing Letter (A-H) followed by room number\n\n"
        "Examples:\n"
        "• A106\n"
        "• E305\n"
        "• H212\n\n"
        "Enter your location:"
    )


def format_room_invalid() -> str:
    """Message when room location format is invalid."""
    return "❌ Invalid room format. Use examples like A106, E305, H212."


def format_time_prompt() -> str:
    """Prompt user for preferred delivery time."""
    return (
        "⏰ Enter your preferred delivery time slot.\n"
        "Example: 06:30pm-07:00pm"
    )


def format_order_confirmed(
    order_ref: str,
    amount: int,
    vendor_name: str,
    hall_name: str,
    room_number: str,
    item_name: str,
) -> str:
    """Format customer order confirmation card."""
    return (
        "✅ <b>Order Confirmed!</b>\n\n"
        f"📦 <b>Order ID:</b> #{order_ref}\n"
        f"💰 <b>Amount:</b> ₦{amount:,}\n"
        f"🏪 <b>Vendor:</b> {vendor_name}\n"
        f"🏢 <b>Delivery:</b> {hall_name} - Room {room_number}\n\n"
        f"🍽️ <b>Your Order:</b>\n{item_name}\n\n"
        "Your order is waiting for a waiter to accept it. You'll be notified when assigned!"
    )


def format_menu_empty() -> str:
    """Format empty menu message."""
    return f"{EMOJI_INFO} No vendors or menu items are available yet.\nAdmin, add items with /additem"


def format_vendor_empty() -> str:
    """Format empty vendor message."""
    return f"{EMOJI_INFO} No vendors are available yet.\nAdmin, add a vendor with /additem first."


def format_menu_item_caption(item_id: int, name: str, price: int, cafeteria_name: str) -> str:
    """Format menu item caption."""
    return (
        f"<b>{EMOJI_FOOD} {name}</b>\n\n"
        f"<b>Price:</b> ₦{price:,}\n"
        f"<b>ID:</b> #{item_id}\n"
        f"<b>Cafeteria:</b> {cafeteria_name}"
    )


def format_menu_vendor_caption(vendor_name: str) -> str:
    """Format vendor caption shown before listing items."""
    return f"<b>{EMOJI_MENU} {vendor_name}</b>\n\nChoose the item you want to order."


def format_order_created_no_waiter(order_ref: str, item_name: str, price: int) -> str:
    """Format order created message when no waiter online."""
    return (
        f"{EMOJI_SUCCESS} <b>Order #{order_ref} Created!</b>\n\n"
        f"{EMOJI_FOOD} <b>Item:</b> {item_name}\n"
        f"{EMOJI_MONEY} <b>Price:</b> ₦{price:,}\n\n"
        f"{EMOJI_PENDING} No waiter online yet...\n"
        f"A waiter will claim your order as soon as they come online."
    )


def format_order_pending_payment(order_ref: str, item_name: str, vendor_name: str, hall_name: str, room_number: str, price: int) -> str:
    """Format order message while payment is pending."""
    return (
        f"{EMOJI_PENDING} <b>Payment Pending</b>\n\n"
        f"📦 <b>Order ID:</b> #{order_ref}\n"
        f"🏪 <b>Vendor:</b> {vendor_name}\n"
        f"🍽️ <b>Item:</b> {item_name}\n"
        f"🏢 <b>Delivery:</b> {hall_name} - Room {room_number}\n"
        f"💰 <b>Amount:</b> ₦{price:,}\n\n"
        "Complete payment using the button below to submit your order."
    )


def format_order_payment_pending(
    order_ref: str,
    vendor_name: str,
    item_name: str,
    hall_name: str,
    room_number: str,
    amount: int,
    payment_provider: str = None,
) -> str:
    """Backward-compatible pending-payment formatter used by app imports."""
    _ = payment_provider
    return format_order_pending_payment(order_ref, item_name, vendor_name, hall_name, room_number, amount)


def format_order_submitted(order_ref: str, item_name: str) -> str:
    """Format order submitted message."""
    return (
        f"{EMOJI_SUCCESS} <b>Order #{order_ref} Submitted!</b>\n\n"
        f"{EMOJI_FOOD} <b>Item:</b> {item_name}\n"
        f"{EMOJI_DELIVERY} <b>Status:</b> Sent to online waiters\n\n"
        f"<i>One of our waiters will claim your order shortly...</i>"
    )


def format_waiter_order_alert(
    order_ref: str,
    item_name: str,
    price: int,
    vendor_name: str,
    hall_name: str,
    room_number: str,
) -> str:
    """Format order alert for waiters."""
    return (
        f"{EMOJI_DELIVERY} <b>New Order #{order_ref}</b>\n\n"
        f"{EMOJI_FOOD} <b>Item:</b> {item_name}\n"
        f"{EMOJI_MONEY} <b>Amount:</b> ₦{price:,}\n"
        f"{EMOJI_INFO} <b>Vendor:</b> {vendor_name}\n\n"
        f"🏫 <b>Hall:</b> {hall_name}\n"
        f"🏢 <b>Room:</b> {room_number}\n\n"
        f"<b>First waiter to claim gets this order!</b>"
    )


def format_order_claimed(order_id: int, waiter_name: str) -> str:
    """Format order claimed message for customer."""
    return (
        f"{EMOJI_SUCCESS} <b>Order #{order_id} Accepted!</b>\n\n"
        f"{EMOJI_WAITER} <b>Waiter:</b> {waiter_name}\n"
        f"{EMOJI_DELIVERY} <b>Status:</b> On the way\n\n"
        f"Your order will arrive shortly. Thank you for your patience! 🙏"
    )


def format_order_completed(order_id: int, cafeteria_name: str) -> str:
    """Format order completed message for customer."""
    return (
        f"{EMOJI_SUCCESS} <b>Order #{order_id} Delivered!</b>\n\n"
        f"Thank you for ordering from <b>{cafeteria_name}</b>!\n\n"
        f"{EMOJI_STAR} Hope you enjoyed your meal. See you soon!"
    )


def format_topup_info() -> str:
    """Format top-up explanation message."""
    return (
        f"{EMOJI_TOPUP} <b>Wallet Top-Up</b>\n\n"
        f"Add funds to your wallet for faster checkout on future orders.\n"
        f"Payment opens a KoraPay card checkout link.\n\n"
        f"<b>Quick Amounts:</b>\n"
        f"• ₦1,000\n"
        f"• ₦2,000\n"
        f"• ₦5,000\n"
        f"• ₦10,000\n"
        f"• ₦20,000\n\n"
        f"<b>Or enter custom amount:</b> /topup <amount>\n"
        f"<i>Example: /topup 3500</i>"
    )


def format_topup_amount_prompt() -> str:
    """Prompt for a custom wallet top-up amount."""
    return (
        f"{EMOJI_TOPUP} <b>Enter Top-Up Amount</b>\n\n"
        f"Send the amount in naira.\n"
        f"Example: <code>3500</code>\n\n"
        f"Use /cancel to stop this flow."
    )


def format_topup_created(amount: int, tx_ref: str, korapay_mode: str = "live") -> str:
    """Format top-up request created message."""
    text = (
        f"{EMOJI_SUCCESS} <b>Top-Up Request Created!</b>\n\n"
        f"{EMOJI_MONEY} <b>Amount:</b> ₦{amount:,}\n"
        f"<b>Reference:</b> {tx_ref}\n\n"
        f"<i>Click the button below to open the KoraPay card checkout and complete payment.</i>"
    )
    if korapay_mode == "mock":
        text += f"\n\n{EMOJI_INFO} <i>Mock mode: admin can complete with</i> /confirm_topup {tx_ref}"
    return text


def format_topup_success(amount: int) -> str:
    """Format top-up success message."""
    return (
        f"{EMOJI_SUCCESS} <b>Top-Up Successful!</b>\n\n"
        f"{EMOJI_MONEY} <b>Amount Added:</b> ₦{amount:,}\n"
        f"Your wallet balance has been updated.\n\n"
        f"Happy ordering! {EMOJI_FOOD}"
    )


def format_wallet_info(balance: int, user_name: str) -> str:
    """Format wallet info message."""
    return (
        f"{EMOJI_WALLET} <b>Your Wallet</b>\n\n"
        f"{EMOJI_CUSTOMER} <b>User:</b> {user_name}\n"
        f"{EMOJI_MONEY} <b>Balance:</b> ₦{balance:,}\n\n"
        f"<i>Top up with card via KoraPay to add funds directly to your wallet.</i>"
    )


def format_wallet_transactions(rows) -> str:
    """Format recent wallet transactions."""
    if not rows:
        return "\n\nNo wallet transactions yet."

    lines = ["", "🧾 <b>Recent Wallet Activity</b>"]
    for row in rows:
        amount = int(row["amount"] or 0)
        amount_label = f"+₦{amount:,}" if amount > 0 else f"-₦{abs(amount):,}"
        tx_type = (row["tx_type"] or "tx").replace("_", " ").title()
        status = (row["status"] or "").title()
        tx_ref = row["tx_ref"] or f"TX{row['id']}"
        lines.append(f"• {tx_type}: <b>{amount_label}</b> ({status})")
        lines.append(f"  Ref: {tx_ref}")
    return "\n".join(lines)


def format_checkout_payment_choice(
    order_ref: str,
    vendor_name: str,
    item_name: str,
    hall_name: str,
    room_number: str,
    amount: int,
    wallet_balance: int,
) -> str:
    """Format payment choice prompt after order details are captured."""
    sufficiency = "enough" if wallet_balance >= amount else "not enough"
    return (
        "💸 <b>Choose Payment Method</b>\n\n"
        f"📦 <b>Order ID:</b> #{order_ref}\n"
        f"🏪 <b>Vendor:</b> {vendor_name}\n"
        f"🍽️ <b>Item:</b> {item_name}\n"
        f"🏫 <b>Delivery:</b> {hall_name} - Room {room_number}\n"
        f"💰 <b>Amount:</b> ₦{amount:,}\n"
        f"👛 <b>Wallet Balance:</b> ₦{wallet_balance:,} ({sufficiency})\n\n"
        "Choose wallet or card checkout below."
    )


def format_wallet_insufficient(balance: int, amount: int) -> str:
    """Format wallet insufficient funds warning."""
    shortfall = max(0, amount - balance)
    return (
        "❌ <b>Insufficient Wallet Balance</b>\n\n"
        f"Wallet: ₦{balance:,}\n"
        f"Required: ₦{amount:,}\n"
        f"Shortfall: ₦{shortfall:,}\n\n"
        "Top up your wallet or pay with KoraPay card checkout."
    )


def format_waiter_online_success() -> str:
    """Format waiter online confirmation."""
    return (
        f"{EMOJI_ONLINE} <b>You're Online!</b>\n\n"
        f"You are now active and will receive order alerts.\n"
        f"Ready to deliver! 🚀"
    )


def format_waiter_offline_success() -> str:
    """Format waiter offline confirmation."""
    return (
        f"{EMOJI_OFFLINE} <b>You're Offline</b>\n\n"
        f"You will no longer receive new order alerts.\n"
        f"Come back when ready to deliver!"
    )


def format_order_completed_waiter(order_id: int, waiter_share: int, platform_share: int) -> str:
    """Format order completion for waiter."""
    return (
        f"{EMOJI_SUCCESS} <b>Order #{order_id} Completed!</b>\n\n"
        f"{EMOJI_MONEY} <b>Your Earnings:</b> ₦{waiter_share:,}\n"
        f"<b>Platform Fee:</b> ₦{platform_share:,}\n\n"
        f"Great job! Thanks for your delivery. 👍"
    )


def format_invalid_amount() -> str:
    """Format invalid amount error."""
    return (
        f"{EMOJI_ERROR} <b>Invalid Amount</b>\n\n"
        f"Please enter a positive number.\n"
        f"<i>Example: /topup 5000</i>"
    )


def format_admin_additem_start() -> str:
    """Format admin add item start message."""
    return (
        f"{EMOJI_ADD} <b>Add New Menu Item</b>\n\n"
        f"Let's create a new menu item. First, send me the item name.\n\n"
        f"<i>Example: Jollof Rice</i>"
    )


def format_admin_additem_price() -> str:
    """Format ask for price."""
    return (
        f"Great! Now send the price in naira.\n\n"
        f"<i>Example: 3500</i>"
    )


def format_admin_additem_image() -> str:
    """Format ask for image."""
    return (
        f"Perfect! Now send an image of the item (optional).\n\n"
        f"Send /skip if you don't have an image."
    )


def format_admin_additem_success(item_id: int, name: str, price: int) -> str:
    """Format item added successfully."""
    return (
        f"{EMOJI_SUCCESS} <b>Item Added!</b>\n\n"
        f"{EMOJI_FOOD} <b>Name:</b> {name}\n"
        f"{EMOJI_MONEY} <b>Price:</b> ₦{price:,}\n"
        f"<b>ID:</b> #{item_id}\n\n"
        f"<i>Item is now available in the menu!</i>"
    )


def format_error_message(error_text: str) -> str:
    """Format generic error message."""
    return f"{EMOJI_ERROR} <b>Error</b>\n\n{error_text}"


def format_unauthorized() -> str:
    """Format unauthorized access message."""
    return f"{EMOJI_ERROR} Sorry, you don't have permission to do this."


def format_catalog_management_menu() -> str:
    """Format the catalog management main menu."""
    return (
        f"{EMOJI_MENU} <b>Catalog Management</b>\n\n"
        f"Manage your menu items and vendors.\n"
        f"Use the buttons below to add, view, or remove items."
    )


def format_catalog_items_list(items: list) -> str:
    """Format list of menu items with IDs for admin management."""
    if not items:
        return f"{EMOJI_INFO} No menu items found.\n\nUse <b>Add Item</b> to create the first item."
    
    lines = [f"{EMOJI_FOOD} <b>Menu Items</b>\n"]
    for item in items:
        vendor_name = item.get("vendor_name", "Unknown")
        price = item.get("price", 0)
        active = "✅" if item.get("active", 1) else "❌"
        lines.append(f"{active} <b>#{item['id']}</b> - {item['name']}")
        lines.append(f"   {vendor_name} • ₦{price:,}\n")
    
    return "\n".join(lines)


def format_item_removal_confirmation(item_name: str, price: int, vendor_name: str) -> str:
    """Format confirmation message before removing an item."""
    return (
        f"{EMOJI_ERROR} <b>Remove Item?</b>\n\n"
        f"<b>Item:</b> {item_name}\n"
        f"<b>Vendor:</b> {vendor_name}\n"
        f"<b>Price:</b> ₦{price:,}\n\n"
        f"<i>This will permanently delete the item. Are you sure?</i>"
    )


def format_item_removed_success(item_name: str) -> str:
    """Format success message after removing an item."""
    return (
        f"{EMOJI_SUCCESS} <b>Item Removed!</b>\n\n"
        f"<b>{item_name}</b> has been deleted from the catalog."
    )


def format_item_management_options(item_id: int, item_name: str) -> str:
    """Format options for managing a specific item."""
    return (
        f"{EMOJI_FOOD} <b>{item_name}</b>\n"
        f"<b>ID:</b> #{item_id}\n\n"
        f"<i>What would you like to do?</i>"
    )


# ==================== UTILITY FUNCTIONS ====================
def separator() -> str:
    """Get a visual separator."""
    return EMOJI_DIVIDER
