from dataclasses import dataclass
import json
import uuid

import aiohttp


@dataclass
class KoraPayPaymentResult:
    tx_ref: str
    checkout_url: str


class KoraPayClient:
    def __init__(
        self,
        mode: str,
        secret_key: str,
        currency: str,
        callback_url: str,
        initialize_url: str,
    ):
        self.mode = mode
        self.secret_key = secret_key
        self.currency = currency
        self.callback_url = callback_url
        self.initialize_url = initialize_url

    def provider_name(self) -> str:
        return "korapay"

    async def initialize_payment(
        self,
        amount: int,
        email: str,
        full_name: str,
        reference_prefix: str,
        user_id: int,
    ) -> KoraPayPaymentResult:
        tx_ref = f"{reference_prefix}_{user_id}_{uuid.uuid4().hex[:12]}"
        if self.mode == "mock":
            return KoraPayPaymentResult(
                tx_ref=tx_ref,
                checkout_url=f"https://checkout.mock.korapay.test/pay/{tx_ref}",
            )

        missing_fields = []
        if not self.secret_key:
            missing_fields.append("KORAPAY_SECRET_KEY")
        if not self.callback_url:
            missing_fields.append("KORAPAY_CALLBACK_URL")
        if missing_fields:
            missing_csv = ", ".join(missing_fields)
            raise RuntimeError(f"Kora Pay live mode is missing required settings: {missing_csv}")

        payload = {
            "amount": amount,
            "currency": self.currency,
            "reference": tx_ref,
            "redirect_url": self.callback_url,
            "customer": {
                "name": full_name,
                "email": email,
            },
        }

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "PrimeChopBot/1.0 (+https://primechop-production.up.railway.app)",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.initialize_url, json=payload, headers=headers) as resp:
                raw_body = await resp.text()
                request_id = (resp.headers.get("kora-request-id") or "").strip()
                cf_ray = (resp.headers.get("cf-ray") or "").strip()
                server = (resp.headers.get("server") or "").strip().lower()
                data = None
                if raw_body:
                    try:
                        data = json.loads(raw_body)
                    except json.JSONDecodeError:
                        data = None

                if resp.status >= 400:
                    message = ""
                    if isinstance(data, dict):
                        message = str(
                            data.get("message")
                            or data.get("error")
                            or data.get("detail")
                            or ""
                        ).strip()
                    if not message:
                        body_preview = " ".join((raw_body or "").split())
                        if not body_preview:
                            body_preview = "empty response body"
                        body_preview = body_preview[:240]
                        message = f"HTTP {resp.status} ({body_preview})"
                    if (
                        resp.status == 403
                        and "<!doctype html" in (raw_body or "").lower()
                        and ("cloudflare" in server or cf_ray)
                    ):
                        message = (
                            "HTTP 403 (Blocked by upstream edge/WAF before reaching Kora API)"
                        )
                    if request_id:
                        message = f"{message} [kora_request_id={request_id}]"
                    if cf_ray:
                        message = f"{message} [cf_ray={cf_ray}]"
                    raise RuntimeError(f"Kora Pay initialize failed: {message}")

                if not isinstance(data, dict):
                    body_preview = " ".join((raw_body or "").split())[:240]
                    if not body_preview:
                        body_preview = "empty response body"
                    suffix = f", kora_request_id={request_id}" if request_id else ""
                    raise RuntimeError(
                        "Kora Pay initialize returned a non-JSON response "
                        f"(HTTP {resp.status}, {body_preview}{suffix})"
                    )

                checkout_url = self._extract_checkout_url(data)
                return KoraPayPaymentResult(tx_ref=tx_ref, checkout_url=checkout_url)

    async def initialize_wallet_topup(
        self,
        amount: int,
        email: str,
        full_name: str,
        user_id: int,
    ) -> KoraPayPaymentResult:
        return await self.initialize_payment(
            amount=amount,
            email=email,
            full_name=full_name,
            reference_prefix="wallet",
            user_id=user_id,
        )

    async def initialize_order_checkout(
        self,
        amount: int,
        email: str,
        full_name: str,
        user_id: int,
        order_ref: str,
    ) -> KoraPayPaymentResult:
        return await self.initialize_payment(
            amount=amount,
            email=email,
            full_name=full_name,
            reference_prefix=f"order_{order_ref}",
            user_id=user_id,
        )

    def _extract_checkout_url(self, data: dict) -> str:
        if not isinstance(data, dict):
            raise RuntimeError("Invalid Kora Pay response format")
        data_node = data.get("data") or {}
        for key in (
            "authorization_url",
            "authorizationUrl",
            "checkout_url",
            "checkoutUrl",
            "payment_url",
            "paymentUrl",
        ):
            value = data_node.get(key)
            if value:
                return str(value)
        raise RuntimeError("Kora Pay response did not include a checkout URL")
