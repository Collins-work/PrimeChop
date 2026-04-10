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
BTN_PLACE_ORDER = "🎯 Launch Food Mission"
BTN_VIEW_CART = "🧺 Mission Cart"
BTN_BECOME_WAITER = f"{EMOJI_WAITER} Join Delivery Guild"
BTN_CUSTOMER_SUPPORT = "🛟 Rescue Desk"
BTN_ORDER_HISTORY = "📜 Match History"
BTN_TERMS = "📘 Rulebook"
BTN_MENU = f"{EMOJI_MENU} Battle Menu"
BTN_WALLET = f"{EMOJI_WALLET} Coin Vault"
BTN_TOPUP = f"{EMOJI_TOPUP} Charge Coins"
BTN_HELP = f"{EMOJI_HELP} Guide"
BTN_PRIME = "⚡ Prime Arena"
BTN_PRIME_GAME = "🎮 Play Prime Mini-Game"
BTN_PRIME_HELP = "🧠 Arena Help"
BTN_PRIME_EXIT = "🏠 Return to Base"
BTN_WAITER_ONLINE = f"{EMOJI_ONLINE} Queue for Runs"
BTN_WAITER_OFFLINE = f"{EMOJI_OFFLINE} Pause Runs"
BTN_VIEW_ORDERS = "📦 Active Runs"
BTN_EXIT_WAITER_MODE = "🚪 Leave Guild Mode"
BTN_ADMIN_ADDITEM = f"{EMOJI_ADD} Forge Menu Item"


# ==================== KEYBOARD BUILDERS ====================
def home_keyboard(role: str) -> ReplyKeyboardMarkup:
    """Build home keyboard based on user role."""
    if role == "waiter":
        rows = [
            [KeyboardButton(BTN_VIEW_ORDERS)],
            [KeyboardButton(BTN_WAITER_ONLINE), KeyboardButton(BTN_WAITER_OFFLINE)],
            [KeyboardButton(BTN_ORDER_HISTORY), KeyboardButton(BTN_CUSTOMER_SUPPORT)],
            [KeyboardButton(BTN_PRIME)],
            [KeyboardButton(BTN_EXIT_WAITER_MODE)],
        ]
        return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)

    rows = [
        [KeyboardButton(BTN_PLACE_ORDER), KeyboardButton(BTN_VIEW_CART)],
        [KeyboardButton(BTN_BECOME_WAITER), KeyboardButton(BTN_CUSTOMER_SUPPORT)],
        [KeyboardButton(BTN_ORDER_HISTORY), KeyboardButton(BTN_TERMS)],
        [KeyboardButton(BTN_WALLET), KeyboardButton(BTN_MENU)],
        [KeyboardButton(BTN_PRIME)],
    ]
    if role == "admin":
        rows.insert(4, [KeyboardButton(BTN_ADMIN_ADDITEM)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)


def prime_keyboard() -> ReplyKeyboardMarkup:
    """Build keyboard for Prime chat mode."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(BTN_PRIME_GAME), KeyboardButton(BTN_PRIME_HELP)],
            [KeyboardButton(BTN_PRIME_EXIT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def topup_presets_keyboard() -> InlineKeyboardMarkup:
    """Show quick top-up amount presets."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚡ +₦1000", callback_data="topup:1000"),
                InlineKeyboardButton("⚡ +₦2000", callback_data="topup:2000"),
                InlineKeyboardButton("⚡ +₦5000", callback_data="topup:5000"),
            ],
            [
                InlineKeyboardButton("💥 +₦10000", callback_data="topup:10000"),
                InlineKeyboardButton("💥 +₦20000", callback_data="topup:20000"),
            ],
            [InlineKeyboardButton("✍️ Set custom charge", callback_data="topup:custom")],
        ]
    )


def payment_method_keyboard(order_ref: str, wallet_balance: int, amount: int) -> InlineKeyboardMarkup:
    """Build payment options keyboard for checkout."""
    rows = []
    if wallet_balance >= amount:
        rows.append([InlineKeyboardButton(f"👛 Use Coin Vault (₦{wallet_balance:,})", callback_data=f"checkout:wallet:{order_ref}")])
    else:
        rows.append([InlineKeyboardButton("💳 Charge Coin Vault", callback_data="topup:start")])
    rows.append([InlineKeyboardButton("💳 Card Checkout (KoraPay)", callback_data=f"checkout:korapay:{order_ref}")])
    rows.append([InlineKeyboardButton("❌ Abort Mission", callback_data=f"checkout:cancel:{order_ref}")])
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
        rows.append([InlineKeyboardButton(f"{item['name']} - ₦{int(item['price']):,}", callback_data=f"catalog:item:{item['id']}")])
    rows.append([InlineKeyboardButton("🧺 Open Mission Cart", callback_data="cart:view")])
    rows.append([InlineKeyboardButton("🔙 Back to Vendor Arena", callback_data="catalog:back_vendors")])
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
    rows.append([InlineKeyboardButton("🔙 Back to Item Deck", callback_data="catalog:back_items")])
    return InlineKeyboardMarkup(rows)


def cart_hall_selection_keyboard(halls) -> InlineKeyboardMarkup:
    """Build keyboard for selecting delivery hall during cart checkout."""
    rows = []
    current_row = []
    for index, hall_name in enumerate(halls):
        current_row.append(InlineKeyboardButton(hall_name, callback_data=f"cart:hall:{index}"))
        if len(current_row) == 2:
            rows.append(current_row)
            current_row = []
    if current_row:
        rows.append(current_row)
    rows.append([InlineKeyboardButton("🔙 Back to Mission Cart", callback_data="cart:view")])
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


def start_recommendation_keyboard(recommendations) -> InlineKeyboardMarkup:
    """Build quick actions for start-screen recommendations."""
    rows = []
    for recommendation in (recommendations or [])[:2]:
        item_id = int(recommendation["id"])
        item_name = str(recommendation["name"])
        short_name = (item_name[:14] + "...") if len(item_name) > 17 else item_name
        rows.append(
            [
                InlineKeyboardButton(f"🛍️ Add {short_name}", callback_data=f"rec:add:{item_id}"),
                InlineKeyboardButton(f"⚡ Urgent {short_name}", callback_data=f"rec:urgent:{item_id}"),
            ]
        )

    rows.append([InlineKeyboardButton("🛒 View Cart", callback_data="cart:view")])
    rows.append([InlineKeyboardButton(BTN_PLACE_ORDER, callback_data="start:place_order")])
    return InlineKeyboardMarkup(rows)


def order_post_actions_keyboard() -> InlineKeyboardMarkup:
    """Build post-order action buttons for customer."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📦 Open Match History", callback_data="order_action:my_orders")],
            [InlineKeyboardButton("🏠 Return to Base", callback_data="order_action:main_menu")],
        ]
    )


def cart_actions_keyboard() -> InlineKeyboardMarkup:
    """Build cart action buttons."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Sync Mission Cart", callback_data="cart:refresh")],
            [InlineKeyboardButton("🗑️ Empty Mission Cart", callback_data="cart:clear")],
        ]
    )


# ==================== MESSAGE FORMATTERS ====================
def format_start_banner_caption(cafeteria_name: str, period_label: str) -> str:
    """Format the short caption shown with the welcome image."""
    return (
        "⚡ <b>PRIMECHOP MATCHDAY RADAR</b>\n\n"
        f"<b>{cafeteria_name}</b> • {period_label}\n"
        "Your daily power picks are locked in below."
    )


def format_start_message(
    cafeteria_name: str,
    period_label: str,
    recommendations,
    user_name: str = "",
) -> str:
    """Format the personalized welcome and meal recommendation message."""
    first_name = user_name.split()[0] if user_name else "there"
    lines = [
        "🎮 <b>WELCOME TO PRIMECHOP ARENA</b>",
        "",
        f"Player {first_name}, here are today's {period_label.lower()} power picks from <b>{cafeteria_name}</b>.",
        "",
        "<b>Today's loadout</b>",
    ]

    if recommendations:
        for index, recommendation in enumerate(recommendations[:3], start=1):
            lines.append(
                f"{index}. <b>{recommendation['name']}</b> - {recommendation['vendor_name']} - ₦{recommendation['price']:,}"
            )
            lines.append(f"   {recommendation['reason']}")
    else:
        lines.append("Your taste profile is charging up. Tap Launch Food Mission to unlock smarter picks.")

    lines.extend(
        [
            "",
            "<b>How your score builds</b>",
            "• We blend time-of-day signals, your order streak, and what students are vibing with.",
            "• The board refreshes daily so every launch feels new.",
            "",
            "<i>PrimeChop - eat smart, move fast, stay legendary.</i>",
        ]
    )
    return "\n".join(lines)


def format_help_message() -> str:
    """Format help/info message."""
    return (
        f"{EMOJI_INFO} <b>PrimeChop Guidebook</b>\n\n"
        f"{EMOJI_DIVIDER}\n\n"
        f"<b>{EMOJI_FOOD} Battle Menu</b>\n"
        f"Browse vendors and launch food missions\n\n"
        f"<b>{EMOJI_WALLET} Coin Vault</b>\n"
        f"Track your coins and recent transactions\n\n"
        f"<b>{EMOJI_TOPUP} Charge Coins</b>\n"
        f"Top up for faster one-tap checkout\n\n"
        f"<b>{EMOJI_DELIVERY} Mission Status</b>\n"
        f"Paid orders auto-match with active waiters\n\n"
        f"{EMOJI_DIVIDER}\n\n"
        f"<b>Need backup?</b>\n"
        f"Ping Rescue Desk and we jump in quickly."
    )


def format_prime_intro(cafeteria_name: str) -> str:
    """Format Prime's opening message."""
    return (
        "⚡ <b>Prime Arena Online</b> ⚡\n\n"
        "I am Prime, your hype guide for food runs, wallet plays, menu picks, and quick mini-games.\n"
        "Ask me anything user-facing and I will keep it sharp, playful, and useful.\n\n"
        f"This arena is tuned for <b>{cafeteria_name}</b> with daily meal intel and fast support paths.\n\n"
        "I cannot reveal internal bot operations, but I can guide every customer flow like a pro.\n\n"
        "Drop a question, request a mini-game, or use the arena buttons below."
    )


def format_prime_exit() -> str:
    """Format Prime exit message."""
    return (
        "🏁 <b>Exiting Prime Arena</b>\n\n"
        "You are back at base menu. Tap <b>Prime Arena</b> whenever you want me again."
    )


def format_become_waiter_success(name: str) -> str:
    """Format successful waiter registration message."""
    return (
        f"{EMOJI_SUCCESS} <b>Guild Profile Activated</b>\n\n"
        f"{EMOJI_WAITER} <b>Name:</b> {name}\n"
        f"{EMOJI_ONLINE} <b>Status:</b> Active\n\n"
        f"You can now receive and claim delivery missions."
    )


def format_customer_support() -> str:
    """Format customer support help text."""
    return (
        f"{EMOJI_INFO} <b>Rescue Desk</b>\n\n"
        f"Need help with missions, payments, or delivery?\n"
        f"Reach support directly:\n"
        f"Phone: 09116002889\n"
        f"Telegram: @ItsClins"
    )


def format_terms_and_conditions() -> str:
    """Format short terms and conditions text."""
    return (
        f"<b>PrimeChop Rulebook</b>\n\n"
        f"1. Missions process based on live menu availability.\n"
        f"2. Coin Vault charges land after successful payment confirmation.\n"
        f"3. Online guild runners are assigned on first-claim basis.\n"
        f"4. Completed deliveries are final and not auto-reversed.\n"
        f"5. Using PrimeChop means you agree to these rules."
    )


def format_empty_order_history() -> str:
    """Format message when user has no order history."""
    return f"{EMOJI_INFO} No match history yet. Complete your first food mission to start the board."


def format_empty_cart() -> str:
    """Format empty cart/active-order message."""
    return (
        "🧺 <b>Mission Cart</b>\n\n"
        "Your cart is empty. Tap <b>Launch Food Mission</b> to draft your first loadout."
    )


def format_view_cart(rows) -> str:
    """Format active orders shown in cart view."""
    lines = ["🧺 <b>Mission Cart Orders</b>"]
    for row in rows:
        item_name = row["item_name"] or f"Item #{row['item_id']}"
        order_ref = row["order_ref"] or f"{row['id']}"
        hall_name = row["hall_name"] or "Unknown hall"
        room_number = row["room_number"] or "N/A"
        lines.append(f"#{order_ref} - {item_name} - ₦{row['amount']:,} - {row['status']}")
        lines.append(f"   Drop Zone: {hall_name} - Room {room_number}")
    return "\n".join(lines)


def format_cart_view(lines, total: int) -> str:
    """Format the current shopping cart."""
    if not lines:
        return format_empty_cart()

    return "\n".join([
        "🧺 <b>Mission Cart</b>",
        "",
        *lines,
        "",
        f"<b>Mission Total:</b> ₦{total:,}",
    ])


def cart_actions_keyboard() -> InlineKeyboardMarkup:
    """Build the main cart action keyboard."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚀 Launch Checkout", callback_data="cart:checkout")],
            [InlineKeyboardButton("🛒 Add More Items", callback_data="cart:vendors")],
            [InlineKeyboardButton("🧹 Clear Mission Cart", callback_data="cart:clear")],
        ]
    )


def format_order_history(rows) -> str:
    """Format compact order history list for a customer."""
    lines = [f"{EMOJI_DELIVERY} <b>Your Match History</b>"]
    for row in rows:
        item_name = row["item_name"] or f"Item #{row['item_id']}"
        order_ref = row["order_ref"] or f"{row['id']}"
        details = row["order_details"] or "No extra note"
        room = row["room_number"] or "N/A"
        hall_name = row["hall_name"] or "Unknown hall"
        lines.append(f"#{order_ref} - {item_name} - ₦{row['amount']:,} - {row['status']}")
        lines.append(f"   Drop Zone: {hall_name} - Room {room}")
        lines.append(f"   Loadout Note: {details}")
    return "\n".join(lines)


def format_order_details_prompt(item_name: str, price: int) -> str:
    """Prompt user to enter detailed order instructions."""
    return (
        "📝 <b>Mission Loadout</b>\n\n"
        f"<b>Selected Item:</b> {item_name}\n"
        f"<b>Cost:</b> ₦{price:,}\n\n"
        "Add your exact request details.\n"
        "Example loadout:\n"
        "• Abacha and Nkwobi x1\n"
        "• Compulsory pack x1\n"
        "• Peppered Gizzard x3"
    )


def format_vendor_prompt() -> str:
    """Prompt user to choose a vendor."""
    return (
        "🏪 <b>Vendor Arena</b>\n\n"
        "Pick your vendor station to begin this mission."
    )


def format_vendor_items_prompt(vendor_name: str) -> str:
    """Prompt user to choose an item from a vendor."""
    return (
        f"🍽️ <b>{vendor_name}</b>\n\n"
        "Choose your item loadout for this run."
    )


def format_hall_prompt(item_name: str, vendor_name: str) -> str:
    """Prompt user to choose their delivery hall."""
    return (
        "🏫 <b>Select Drop Zone</b>\n\n"
        f"<b>Vendor:</b> {vendor_name}\n"
        f"<b>Item:</b> {item_name}\n\n"
        "Choose your hall drop zone below."
    )


def format_room_prompt_with_hall(hall_name: str) -> str:
    """Prompt user to enter room number after hall selection."""
    return (
        f"🏠 <b>{hall_name}</b>\n\n"
        "Enter your room checkpoint.\n"
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
        f"✅ <b>Mission Locked - Payment Needed</b>\n\n"
        f"📦 <b>Order ID:</b> #{order_ref}\n"
        f"🏪 <b>Vendor:</b> {vendor_name}\n"
        f"🍽️ <b>Item:</b> {item_name}\n"
        f"🏫 <b>Delivery:</b> {hall_name} - Room {room_number}\n"
        f"💰 <b>Amount:</b> ₦{amount:,}\n"
        f"💳 <b>Payment Rail:</b> {provider_label}\n\n"
        "Tap below to complete payment and dispatch this mission."
    )


def format_room_prompt() -> str:
    """Prompt user to enter room location in accepted format."""
    return (
        "Enter your room checkpoint in this format:\n"
        "Wing Letter (A-H) followed by room number\n\n"
        "Examples:\n"
        "• A106\n"
        "• E305\n"
        "• H212\n\n"
        "Send your location now:"
    )


def format_room_invalid() -> str:
    """Message when room location format is invalid."""
    return "❌ Invalid checkpoint format. Use A106, E305, or H212."


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
        "✅ <b>Mission Confirmed!</b>\n\n"
        f"📦 <b>Order ID:</b> #{order_ref}\n"
        f"💰 <b>Amount:</b> ₦{amount:,}\n"
        f"🏪 <b>Vendor:</b> {vendor_name}\n"
        f"🏢 <b>Delivery:</b> {hall_name} - Room {room_number}\n\n"
        f"🍽️ <b>Your Loadout:</b>\n{item_name}\n\n"
        "Your mission is now in queue. You will be alerted once a guild runner claims it."
    )


def format_menu_empty() -> str:
    """Format empty menu message."""
    return f"{EMOJI_INFO} The arena menu is empty right now.\nAdmin: forge items with /additem"


def format_vendor_empty() -> str:
    """Format empty vendor message."""
    return f"{EMOJI_INFO} No vendor stations are active yet.\nAdmin, add a vendor with /additem first."


def format_menu_item_caption(item_id: int, name: str, price: int, cafeteria_name: str) -> str:
    """Format menu item caption."""
    return (
        f"<b>{EMOJI_FOOD} {name}</b>\n\n"
        f"<b>Power Cost:</b> ₦{price:,}\n"
        f"<b>Item ID:</b> #{item_id}\n"
        f"<b>Arena:</b> {cafeteria_name}"
    )


def format_menu_vendor_caption(vendor_name: str) -> str:
    """Format vendor caption shown before listing items."""
    return f"<b>{EMOJI_MENU} {vendor_name}</b>\n\nPick an item and continue your food mission."


def format_order_created_no_waiter(order_ref: str, item_name: str, price: int) -> str:
    """Format order created message when no waiter online."""
    return (
        f"{EMOJI_SUCCESS} <b>Mission #{order_ref} Created!</b>\n\n"
        f"{EMOJI_FOOD} <b>Item:</b> {item_name}\n"
        f"{EMOJI_MONEY} <b>Cost:</b> ₦{price:,}\n\n"
        f"{EMOJI_PENDING} No runner is queued yet...\n"
        f"The first online runner will claim your mission automatically."
    )


def format_order_pending_payment(order_ref: str, item_name: str, vendor_name: str, hall_name: str, room_number: str, price: int) -> str:
    """Format order message while payment is pending."""
    return (
        f"{EMOJI_PENDING} <b>Mission Waiting for Payment</b>\n\n"
        f"📦 <b>Order ID:</b> #{order_ref}\n"
        f"🏪 <b>Vendor:</b> {vendor_name}\n"
        f"🍽️ <b>Item:</b> {item_name}\n"
        f"🏢 <b>Delivery:</b> {hall_name} - Room {room_number}\n"
        f"💰 <b>Amount:</b> ₦{price:,}\n\n"
        "Complete payment below to launch this mission to runner queue."
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
        f"{EMOJI_SUCCESS} <b>Mission #{order_ref} Submitted!</b>\n\n"
        f"{EMOJI_FOOD} <b>Item:</b> {item_name}\n"
        f"{EMOJI_DELIVERY} <b>Status:</b> Broadcast to online guild runners\n\n"
        f"<i>A runner will claim this mission shortly.</i>"
    )


def format_waiter_order_alert(
    order_ref: str,
    item_name: str,
    price: int,
    vendor_name: str,
    hall_name: str,
    room_number: str,
    order_details: str = "",
) -> str:
    """Format order alert for waiters."""
    details_block = f"\n🧾 <b>Details:</b>\n{order_details}\n" if order_details else ""
    return (
        f"{EMOJI_DELIVERY} <b>New Mission #{order_ref}</b>\n\n"
        f"{EMOJI_FOOD} <b>Item:</b> {item_name}\n"
        f"{EMOJI_MONEY} <b>Amount:</b> ₦{price:,}\n"
        f"{EMOJI_INFO} <b>Vendor Station:</b> {vendor_name}\n"
        f"{details_block}\n"
        f"🏫 <b>Drop Zone:</b> {hall_name}\n"
        f"🏢 <b>Checkpoint:</b> {room_number}\n\n"
        f"<b>First runner to claim wins this mission.</b>"
    )


def format_order_claimed(order_id: int, waiter_name: str) -> str:
    """Format order claimed message for customer."""
    return (
        f"{EMOJI_SUCCESS} <b>Mission #{order_id} Claimed!</b>\n\n"
        f"{EMOJI_WAITER} <b>Runner:</b> {waiter_name}\n"
        f"{EMOJI_DELIVERY} <b>Status:</b> On the way\n\n"
        f"Your mission delivery is in motion. Thanks for staying locked in."
    )


def format_order_completed(order_id: int, cafeteria_name: str) -> str:
    """Format order completed message for customer."""
    return (
        f"{EMOJI_SUCCESS} <b>Mission #{order_id} Completed!</b>\n\n"
        f"Delivery confirmed at <b>{cafeteria_name}</b>.\n\n"
        f"{EMOJI_STAR} GG. Enjoy your meal and come back for another run."
    )


def format_topup_info() -> str:
    """Format top-up explanation message."""
    return (
        f"{EMOJI_TOPUP} <b>Coin Vault Charge</b>\n\n"
        f"Load your Coin Vault for faster mission checkout.\n"
        f"Payment opens a secure KoraPay card screen.\n\n"
        f"<b>Quick Charge Packs:</b>\n"
        f"• ₦1,000\n"
        f"• ₦2,000\n"
        f"• ₦5,000\n"
        f"• ₦10,000\n"
        f"• ₦20,000\n\n"
        f"<b>Or set a custom charge:</b> /topup <amount>\n"
        f"<i>Example: /topup 3500</i>"
    )


def format_topup_amount_prompt() -> str:
    """Prompt for a custom wallet top-up amount."""
    return (
        f"{EMOJI_TOPUP} <b>Set Charge Amount</b>\n\n"
        f"Send the amount in naira.\n"
        f"Example: <code>3500</code>\n\n"
        f"Use /cancel to abort this flow."
    )


def format_topup_created(amount: int, tx_ref: str, korapay_mode: str = "live") -> str:
    """Format top-up request created message."""
    text = (
        f"{EMOJI_SUCCESS} <b>Charge Request Created!</b>\n\n"
        f"{EMOJI_MONEY} <b>Amount:</b> ₦{amount:,}\n"
        f"<b>Run Ref:</b> {tx_ref}\n\n"
        f"<i>Tap below to open KoraPay and complete your Coin Vault charge.</i>"
    )
    if korapay_mode == "mock":
        text += (
            f"\n\n{EMOJI_INFO} <i>Mock mode: admin has been pinged to confirm this charge</i>"
            f"\n<i>Command fallback:</i> /confirm_topup {tx_ref}"
        )
    return text


def format_topup_success(amount: int) -> str:
    """Format top-up success message."""
    return (
        f"{EMOJI_SUCCESS} <b>Coin Vault Charged!</b>\n\n"
        f"{EMOJI_MONEY} <b>Amount Added:</b> ₦{amount:,}\n"
        f"Your vault balance is now updated.\n\n"
        f"Ready for your next mission. {EMOJI_FOOD}"
    )


def format_wallet_info(balance: int, user_name: str) -> str:
    """Format wallet info message."""
    return (
        f"{EMOJI_WALLET} <b>Your Coin Vault</b>\n\n"
        f"{EMOJI_CUSTOMER} <b>Player:</b> {user_name}\n"
        f"{EMOJI_MONEY} <b>Balance:</b> ₦{balance:,}\n\n"
        f"<i>Charge with card via KoraPay for instant mission checkout.</i>"
    )


def format_wallet_transactions(rows) -> str:
    """Format recent wallet transactions."""
    if not rows:
        return "\n\nNo Coin Vault activity yet."

    lines = ["", "🧾 <b>Recent Vault Activity</b>"]
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
        "💸 <b>Choose Your Payment Route</b>\n\n"
        f"📦 <b>Order ID:</b> #{order_ref}\n"
        f"🏪 <b>Vendor:</b> {vendor_name}\n"
        f"🍽️ <b>Item:</b> {item_name}\n"
        f"🏫 <b>Delivery:</b> {hall_name} - Room {room_number}\n"
        f"💰 <b>Amount:</b> ₦{amount:,}\n"
        f"👛 <b>Coin Vault:</b> ₦{wallet_balance:,} ({sufficiency})\n\n"
        "Choose Coin Vault or card checkout below."
    )


def format_wallet_insufficient(balance: int, amount: int) -> str:
    """Format wallet insufficient funds warning."""
    shortfall = max(0, amount - balance)
    return (
        "❌ <b>Insufficient Coin Vault Balance</b>\n\n"
        f"Vault: ₦{balance:,}\n"
        f"Required: ₦{amount:,}\n"
        f"Shortfall: ₦{shortfall:,}\n\n"
        "Charge your vault or pay with KoraPay card checkout."
    )


def format_waiter_online_success() -> str:
    """Format waiter online confirmation."""
    return (
        f"{EMOJI_ONLINE} <b>Guild Status: Active</b>\n\n"
        f"You are now queued for new mission alerts.\n"
        f"Ready to run."
    )


def format_waiter_offline_success() -> str:
    """Format waiter offline confirmation."""
    return (
        f"{EMOJI_OFFLINE} <b>Guild Status: Paused</b>\n\n"
        f"You will no longer receive new mission alerts.\n"
        f"Return when you are ready for another run."
    )


def format_order_completed_waiter(order_id: int, waiter_share: int, platform_share: int) -> str:
    """Format order completion for waiter."""
    return (
        f"{EMOJI_SUCCESS} <b>Mission #{order_id} Completed!</b>\n\n"
        f"{EMOJI_MONEY} <b>Your Reward:</b> ₦{waiter_share:,}\n"
        f"<b>Platform Fee:</b> ₦{platform_share:,}\n\n"
        f"Great run. Thanks for the delivery."
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
        f"{EMOJI_ADD} <b>Forge New Menu Item</b>\n\n"
        f"Let's craft a new arena item. First, send the item name.\n\n"
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
        f"Perfect. Now send an image card for this item (optional).\n\n"
        f"Send /skip if you don't have an image."
    )


def format_admin_additem_success(item_id: int, name: str, price: int) -> str:
    """Format item added successfully."""
    return (
        f"{EMOJI_SUCCESS} <b>Item Forged Successfully!</b>\n\n"
        f"{EMOJI_FOOD} <b>Name:</b> {name}\n"
        f"{EMOJI_MONEY} <b>Price:</b> ₦{price:,}\n"
        f"<b>ID:</b> #{item_id}\n\n"
        f"<i>This item is now live in the arena menu.</i>"
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
        f"{EMOJI_MENU} <b>Arena Catalog Control</b>\n\n"
        f"Manage menu items and vendor stations.\n"
        f"Use the controls below to forge, inspect, or remove items."
    )


def format_catalog_items_list(items: list) -> str:
    """Format list of menu items with IDs for admin management."""
    if not items:
        return f"{EMOJI_INFO} No menu items found.\n\nUse <b>Forge Menu Item</b> to create the first entry."
    
    def _value(row, key: str, default):
        if isinstance(row, dict):
            return row.get(key, default)
        try:
            return row[key]
        except (KeyError, IndexError, TypeError):
            return default

    lines = [f"{EMOJI_FOOD} <b>Arena Menu Items</b>\n"]
    for item in items:
        vendor_name = _value(item, "vendor_name", "Unknown") or "Unknown"
        price = int(_value(item, "price", 0) or 0)
        active = "✅" if _value(item, "active", 1) else "❌"
        lines.append(f"{active} <b>#{item['id']}</b> - {item['name']}")
        lines.append(f"   {vendor_name} • ₦{price:,}\n")
    
    return "\n".join(lines)


def format_item_removal_confirmation(item_name: str, price: int, vendor_name: str) -> str:
    """Format confirmation message before removing an item."""
    return (
        f"{EMOJI_ERROR} <b>Retire Item?</b>\n\n"
        f"<b>Item:</b> {item_name}\n"
        f"<b>Vendor:</b> {vendor_name}\n"
        f"<b>Price:</b> ₦{price:,}\n\n"
        f"<i>This permanently removes the item from arena menu. Continue?</i>"
    )


def format_item_removed_success(item_name: str) -> str:
    """Format success message after removing an item."""
    return (
        f"{EMOJI_SUCCESS} <b>Item Retired!</b>\n\n"
        f"<b>{item_name}</b> has been removed from the arena catalog."
    )


def format_item_management_options(item_id: int, item_name: str) -> str:
    """Format options for managing a specific item."""
    return (
        f"{EMOJI_FOOD} <b>{item_name}</b>\n"
        f"<b>ID:</b> #{item_id}\n\n"
        f"<i>Select a management action for this item.</i>"
    )


# ==================== UTILITY FUNCTIONS ====================
def separator() -> str:
    """Get a visual separator."""
    return EMOJI_DIVIDER
