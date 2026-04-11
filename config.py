from dataclasses import dataclass
from pathlib import Path
from typing import Set
import os
import logging

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=True)


DEFAULT_ORDER_VENDORS = [
    "Kingsway",
    "Delight blessings edibles",
    "Sref ventures toast bread",
    "Waffledom",
    "Yamarita",
    "Burrito chicken",
    "D4fries",
    "Emabuop",
    "DGG Grills",
    "Evelyn chip& protein",
    "Suya Academy",
    "Spicy Igbo delicacy",
    "Grandpa chips",
    "6:33 pizza republic",
    "Dekoen amazing fruits",
    "Pizzaburger (BYCP)",
    "Slash shawarma",
    "CU Pizza & burger",
    "Bread warmer",
    "Suya spot",
    "Yam and fish",
]


def _parse_ids(raw: str) -> Set[int]:
    if not raw.strip():
        return set()
    return {int(part.strip()) for part in raw.split(",") if part.strip()}


def _parse_set(raw: str) -> Set[str]:
    if not raw.strip():
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _parse_csv_list(raw: str) -> list[str]:
    if not raw.strip():
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _parse_bool(raw: str, default: bool = False) -> bool:
    value = (raw or "").strip().lower()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    db_path: str
    webhook_enabled: bool
    webhook_base_url: str
    webhook_path: str
    webhook_listen_host: str
    webhook_port: int
    admin_ids: Set[int]
    admin_phone_numbers: Set[str]
    waiter_ids: Set[int]
    bot_timezone: str
    cafeteria_name: str
    order_vendors: list[str]
    delivery_halls: list[str]
    korapay_mode: str
    korapay_secret_key: str
    korapay_public_key: str
    korapay_currency: str
    korapay_callback_url: str
    korapay_initialize_url: str
    korapay_web_host: str
    korapay_web_port: int
    service_fee_total: int
    service_fee_split_mode: str
    placeholder_image_url: str
    start_logo: str
    super_admin_secret: str
    excel_audit_enabled: bool
    excel_audit_backend: str
    excel_audit_file: str
    excel_audit_sqlite_db: str
    google_sheets_spreadsheet_id: str
    google_sheets_credentials_file: str
    google_sheets_order_sheet: str
    google_sheets_waiter_sheet: str
    excel_audit_async_writes: bool
    excel_audit_flush_interval_seconds: float
    excel_audit_batch_size: int
    lightweight_mode: bool
    allowed_updates: list[str]
    startup_waiter_sync_limit: int
    prime_ai_enabled: bool
    prime_ai_api_key: str
    prime_ai_chat_url: str
    prime_ai_model: str
    prime_ai_timeout_seconds: float


settings = Settings(
    telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
    db_path=os.getenv("DB_PATH", "primechop.db").strip() or "primechop.db",
    webhook_enabled=_parse_bool(
        os.getenv("WEBHOOK_ENABLED", ""),
        default=bool(os.getenv("RENDER") and os.getenv("WEBHOOK_BASE_URL")),
    ),
    webhook_base_url=os.getenv("WEBHOOK_BASE_URL", "").strip().rstrip("/"),
    webhook_path=(os.getenv("WEBHOOK_PATH", "/telegram/webhook").strip() or "/telegram/webhook"),
    webhook_listen_host=os.getenv("WEBHOOK_LISTEN_HOST", "0.0.0.0").strip(),
    webhook_port=int(os.getenv("WEBHOOK_PORT", os.getenv("PORT", "8080"))),
    admin_ids=_parse_ids(os.getenv("ADMIN_IDS", "")),
    admin_phone_numbers=_parse_set(os.getenv("ADMIN_PHONE_NUMBERS", "")),
    waiter_ids=_parse_ids(os.getenv("WAITER_IDS", "")),
    bot_timezone=os.getenv("BOT_TIMEZONE", "Africa/Lagos").strip(),
    cafeteria_name=os.getenv("CAFETERIA_NAME", "Cafeteria 1").strip(),
    order_vendors=_parse_csv_list(os.getenv("ORDER_VENDORS", "")) or DEFAULT_ORDER_VENDORS,
    delivery_halls=_parse_csv_list(os.getenv("DELIVERY_HALLS", ""))
    or [
        "Hall John",
        "Hall Paul",
        "Hall Peter",
        "Hall Joseph",
        "Hall Daniel",
        "Hall Mary",
        "Hall Esther",
        "Hall Dorcas",
        "Hall Lydia",
        "Hall Deborah",
    ],
    korapay_mode=os.getenv("KORAPAY_MODE", "mock").strip().lower(),
    korapay_secret_key=os.getenv("KORAPAY_SECRET_KEY", "").strip(),
    korapay_public_key=os.getenv("KORAPAY_PUBLIC_KEY", "").strip(),
    korapay_currency=os.getenv("KORAPAY_CURRENCY", "NGN").strip(),
    korapay_callback_url=os.getenv("KORAPAY_CALLBACK_URL", "").strip(),
    korapay_initialize_url=os.getenv(
        "KORAPAY_INITIALIZE_URL",
        "https://api.korapay.com/merchant/api/v1/charges/initialize",
    ).strip(),
    korapay_web_host=os.getenv("KORAPAY_WEB_HOST", "0.0.0.0").strip(),
    korapay_web_port=int(os.getenv("KORAPAY_WEB_PORT", os.getenv("PORT", "8080"))),
    service_fee_total=int(os.getenv("SERVICE_FEE_TOTAL", "500")),
    service_fee_split_mode=os.getenv("SERVICE_FEE_SPLIT_MODE", "equal").strip().lower(),
    placeholder_image_url=os.getenv(
        "PLACEHOLDER_IMAGE_URL",
        "https://via.placeholder.com/1024x768.png?text=Food+Item",
    ).strip(),
    start_logo=os.getenv("START_LOGO", "assets/primechop-logo.png").strip(),
    super_admin_secret=os.getenv("SUPER_ADMIN_SECRET", "collpre123").strip(),
    excel_audit_enabled=_parse_bool(os.getenv("EXCEL_AUDIT_ENABLED", "true"), default=True),
    excel_audit_backend=os.getenv("EXCEL_AUDIT_BACKEND", "sqlite").strip().lower(),
    excel_audit_file=os.getenv("EXCEL_AUDIT_FILE", "primechop_audit.xlsx").strip(),
    excel_audit_sqlite_db=os.getenv("EXCEL_AUDIT_SQLITE_DB", "primechop.db").strip(),
    google_sheets_spreadsheet_id=os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "").strip(),
    google_sheets_credentials_file=os.getenv("GOOGLE_SHEETS_CREDENTIALS_FILE", "").strip(),
    google_sheets_order_sheet=os.getenv("GOOGLE_SHEETS_ORDER_SHEET", "OrdersAudit").strip(),
    google_sheets_waiter_sheet=os.getenv("GOOGLE_SHEETS_WAITER_SHEET", "WaiterRegistry").strip(),
    excel_audit_async_writes=_parse_bool(os.getenv("EXCEL_AUDIT_ASYNC_WRITES", "true"), default=True),
    excel_audit_flush_interval_seconds=float(os.getenv("EXCEL_AUDIT_FLUSH_INTERVAL_SECONDS", "1.0")),
    excel_audit_batch_size=max(1, int(os.getenv("EXCEL_AUDIT_BATCH_SIZE", "25"))),
    lightweight_mode=_parse_bool(
        os.getenv("LIGHTWEIGHT_MODE", "true" if os.getenv("RENDER") else "false"),
        default=bool(os.getenv("RENDER")),
    ),
    allowed_updates=_parse_csv_list(os.getenv("ALLOWED_UPDATES", "message,callback_query"))
    or ["message", "callback_query"],
    startup_waiter_sync_limit=max(100, int(os.getenv("STARTUP_WAITER_SYNC_LIMIT", "500"))),
    prime_ai_enabled=_parse_bool(os.getenv("PRIME_AI_ENABLED", "true"), default=True),
    prime_ai_api_key=os.getenv("PRIME_AI_API_KEY", "").strip(),
    prime_ai_chat_url=os.getenv("PRIME_AI_CHAT_URL", "https://openrouter.ai/api/v1/chat/completions").strip(),
    prime_ai_model=os.getenv("PRIME_AI_MODEL", "openai/gpt-4o-mini").strip(),
    prime_ai_timeout_seconds=max(5.0, float(os.getenv("PRIME_AI_TIMEOUT_SECONDS", "20"))),
)

if not settings.telegram_bot_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required in environment variables.")

if (
    settings.korapay_mode == "live"
    and (settings.korapay_secret_key.startswith("sk_test_")
         or settings.korapay_public_key.startswith("pk_test_"))
):
    logger.warning(
        "KoraPay is running in live mode with test credentials (sandbox). "
        "This is fine for testing but should be switched to production keys before go-live."
    )
