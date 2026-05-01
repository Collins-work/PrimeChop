from dataclasses import dataclass
from pathlib import Path
from typing import Set
import os
import logging
import re

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


# Keep real environment variables (Railway/Render) authoritative.
# The local .env file only fills in values that are not already set.
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)


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


def _parse_int(raw: str, default: int = 0) -> int:
    value = (raw or "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _strip_wrapping_quotes(raw: str) -> str:
    value = (raw or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"\"", "'"}:
        return value[1:-1].strip()
    return value


def _normalize_paystack_key(raw: str) -> str:
    value = _strip_wrapping_quotes(raw)
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    # Recover the raw key if extra text/punctuation was accidentally pasted.
    match = re.search(r"\b(?:sk|pk)_(?:live|test)_[A-Za-z0-9]+\b", value)
    if match:
        return match.group(0)
    return value


def _first_nonempty_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "")
        if value and value.strip():
            return value
    return ""


def _collect_env_values(*names: str) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        raw = os.getenv(name, "")
        normalized = _normalize_paystack_key(raw)
        if normalized:
            values.append((name, normalized))
    return values


def _pick_paystack_key(primary_names: list[str], secondary_names: list[str], expected_prefix: str) -> tuple[str, str]:
    primary = _collect_env_values(*primary_names)
    secondary = _collect_env_values(*secondary_names)

    for source, value in primary:
        if value.lower().startswith(expected_prefix):
            return value, source
    for source, value in secondary:
        if value.lower().startswith(expected_prefix):
            return value, source
    if primary:
        return primary[0][1], primary[0][0]
    if secondary:
        return secondary[0][1], secondary[0][0]
    return "", ""


_paystack_secret_key, _paystack_secret_source = _pick_paystack_key(
    primary_names=[
        "PAYSTACK_SECRET_KEY",
        "PAYSTACK_SECRET",
        "PAYSTACK_LIVE_SECRET_KEY",
        "PAYSTACK_SECRET_LIVE_KEY",
        "PAYSTACK_LIVE_SECRET",
    ],
    secondary_names=[
        "PAYSTACK_PUBLIC_KEY",
        "PAYSTACK_PUBLIC",
        "PAYSTACK_LIVE_PUBLIC_KEY",
        "PAYSTACK_PUBLIC_LIVE_KEY",
        "PAYSTACK_LIVE_PUBLIC",
    ],
    expected_prefix="sk_",
)

_paystack_public_key, _paystack_public_source = _pick_paystack_key(
    primary_names=[
        "PAYSTACK_PUBLIC_KEY",
        "PAYSTACK_PUBLIC",
        "PAYSTACK_LIVE_PUBLIC_KEY",
        "PAYSTACK_PUBLIC_LIVE_KEY",
        "PAYSTACK_LIVE_PUBLIC",
    ],
    secondary_names=[
        "PAYSTACK_SECRET_KEY",
        "PAYSTACK_SECRET",
        "PAYSTACK_LIVE_SECRET_KEY",
        "PAYSTACK_SECRET_LIVE_KEY",
        "PAYSTACK_LIVE_SECRET",
    ],
    expected_prefix="pk_",
)

if _paystack_secret_key.lower().startswith("pk_") and _paystack_public_key.lower().startswith("sk_"):
    _paystack_secret_key, _paystack_public_key = _paystack_public_key, _paystack_secret_key
    _paystack_secret_source, _paystack_public_source = _paystack_public_source, _paystack_secret_source
    logger.warning("Detected swapped Paystack keys in environment; auto-corrected secret/public mapping.")


def _normalize_google_sheet_id(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if "/d/" in value:
        try:
            return value.split("/d/", 1)[1].split("/", 1)[0].strip()
        except Exception:
            return value
    return value


def _resolve_database_url() -> str:
    """Resolve PostgreSQL connection URL from environment"""
    database_url = (os.getenv("DATABASE_URL", "") or "").strip()
    if database_url:
        return database_url
    
    # Fallback: construct from individual components
    user = os.getenv("POSTGRES_USER", "").strip()
    password = os.getenv("POSTGRES_PASSWORD", "").strip()
    host = os.getenv("POSTGRES_HOST", "localhost").strip()
    port = os.getenv("POSTGRES_PORT", "5432").strip()
    database = os.getenv("POSTGRES_DB", "primechop").strip()
    
    if not user:
        raise ValueError(
            "DATABASE_URL environment variable is required. "
            "Set it directly or via POSTGRES_* env vars (POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB)"
        )
    
    auth = f"{user}"
    if password:
        auth = f"{user}:{password}"
    
    return f"postgresql://{auth}@{host}:{port}/{database}"


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    database_url: str
    webhook_enabled: bool
    webhook_base_url: str
    webhook_path: str
    webhook_listen_host: str
    webhook_port: int
    admin_ids: Set[int]
    admin_phone_numbers: Set[str]
    waiter_ids: Set[int]
    order_log_group_chat_id: int
    bot_timezone: str
    cafeteria_name: str
    order_vendors: list[str]
    delivery_halls: list[str]
    paystack_mode: str
    paystack_secret_key: str
    paystack_public_key: str
    paystack_currency: str
    paystack_callback_url: str
    paystack_initialize_url: str
    paystack_verify_url: str
    paystack_web_host: str
    paystack_web_port: int
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
    default_delivery_eta_minutes: int
    allow_order_history_purge: bool


settings = Settings(
    telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
    database_url=_resolve_database_url(),
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
    order_log_group_chat_id=_parse_int(os.getenv("ORDER_LOG_GROUP_CHAT_ID", "0"), default=0),
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
    paystack_mode=_strip_wrapping_quotes(os.getenv("PAYSTACK_MODE", "mock")).lower(),
    paystack_secret_key=_paystack_secret_key,
    paystack_public_key=_paystack_public_key,
    paystack_currency=_strip_wrapping_quotes(os.getenv("PAYSTACK_CURRENCY", "NGN")),
    paystack_callback_url=_strip_wrapping_quotes(os.getenv("PAYSTACK_CALLBACK_URL", "")),
    paystack_initialize_url=_strip_wrapping_quotes(os.getenv(
        "PAYSTACK_INITIALIZE_URL",
        "https://api.paystack.co/transaction/initialize",
    )),
    paystack_verify_url=_strip_wrapping_quotes(os.getenv(
        "PAYSTACK_VERIFY_URL",
        "https://api.paystack.co/transaction/verify",
    )),
    paystack_web_host=os.getenv("PAYSTACK_WEB_HOST", "0.0.0.0").strip(),
    paystack_web_port=int(os.getenv("PAYSTACK_WEB_PORT", os.getenv("PORT", "8080"))),
    service_fee_total=int(os.getenv("SERVICE_FEE_TOTAL", "650")),
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
    google_sheets_spreadsheet_id=_normalize_google_sheet_id(os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID", "")),
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
    default_delivery_eta_minutes=max(8, int(os.getenv("DEFAULT_DELIVERY_ETA_MINUTES", "25"))),
    allow_order_history_purge=_parse_bool(os.getenv("ALLOW_ORDER_HISTORY_PURGE", "false"), default=False),
)

if not settings.telegram_bot_token:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is required in environment variables.")

if (
    settings.paystack_mode == "live"
    and ("test" in settings.paystack_secret_key.lower()
         or "test" in settings.paystack_public_key.lower())
):
    logger.warning(
        "Paystack is running in live mode with test credentials. "
        "This is fine for testing but should be switched to production keys before go-live."
    )

if settings.paystack_mode == "live":
    secret_key = settings.paystack_secret_key.strip()
    public_key = settings.paystack_public_key.strip()

    if _paystack_secret_source:
        logger.info("Paystack secret key source: %s", _paystack_secret_source)
    if _paystack_public_source:
        logger.info("Paystack public key source: %s", _paystack_public_source)

    if not secret_key:
        logger.warning("PAYSTACK_SECRET_KEY is empty while PAYSTACK_MODE=live.")
    elif secret_key.startswith("pk_"):
        logger.warning("PAYSTACK_SECRET_KEY looks like a public key (starts with pk_).")

    if not public_key:
        logger.warning("PAYSTACK_PUBLIC_KEY is empty while PAYSTACK_MODE=live.")
    elif public_key.startswith("sk_"):
        logger.warning("PAYSTACK_PUBLIC_KEY looks like a secret key (starts with sk_).")
