from dataclasses import dataclass
import hashlib
import hmac
import json
import uuid

import aiohttp


@dataclass
class PaystackPaymentResult:
    tx_ref: str
    checkout_url: str


class PaystackClient:
    def __init__(
        self,
        mode: str,
        secret_key: str,
        public_key: str,
        currency: str,
        callback_url: str,
        initialize_url: str,
        verify_url: str,
    ):
        self.mode = mode
        self.secret_key = secret_key
        self.public_key = public_key
        self.currency = currency
        self.callback_url = callback_url
        self.initialize_url = initialize_url
        self.verify_url = verify_url.rstrip("/")

    def provider_name(self) -> str:
        return "paystack"

    async def initialize_payment(
        self,
        amount: int,
        email: str,
        full_name: str,
        reference_prefix: str,
        user_id: int,
    ) -> PaystackPaymentResult:
        tx_ref = f"{reference_prefix}_{user_id}_{uuid.uuid4().hex[:12]}"
        if self.mode == "mock":
            return PaystackPaymentResult(
                tx_ref=tx_ref,
                checkout_url=f"https://checkout.paystack.mock/pay/{tx_ref}",
            )

        missing_fields = []
        if not self.secret_key:
            missing_fields.append("PAYSTACK_SECRET_KEY")
        if not self.callback_url:
            missing_fields.append("PAYSTACK_CALLBACK_URL")
        if missing_fields:
            missing_csv = ", ".join(missing_fields)
            raise RuntimeError(f"Paystack live mode is missing required settings: {missing_csv}")

        payload = {
            "amount": int(amount) * 100,
            "currency": self.currency,
            "reference": tx_ref,
            "callback_url": self.callback_url,
            "email": email,
            "metadata": {
                "full_name": full_name,
                "user_id": user_id,
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
                data = self._parse_json(raw_body)
                request_id = (resp.headers.get("x-request-id") or resp.headers.get("request-id") or "").strip()
                cf_ray = (resp.headers.get("cf-ray") or "").strip()

                if resp.status >= 400:
                    message = self._response_message(data, raw_body, resp.status)
                    if request_id:
                        message = f"{message} [request_id={request_id}]"
                    if cf_ray:
                        message = f"{message} [cf_ray={cf_ray}]"
                    raise RuntimeError(f"Paystack initialize failed: {message}")

                if not isinstance(data, dict):
                    preview = self._preview_body(raw_body)
                    suffix = f", request_id={request_id}" if request_id else ""
                    raise RuntimeError(
                        "Paystack initialize returned a non-JSON response "
                        f"(HTTP {resp.status}, {preview}{suffix})"
                    )

                checkout_url = self._extract_checkout_url(data)
                return PaystackPaymentResult(tx_ref=tx_ref, checkout_url=checkout_url)

    async def verify_payment(self, reference: str) -> dict:
        if self.mode == "mock":
            return {"status": True, "data": {"status": "success", "reference": reference}}

        if not self.secret_key:
            raise RuntimeError("PAYSTACK_SECRET_KEY is required to verify payments")

        url = f"{self.verify_url}/{reference}"
        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Accept": "application/json",
            "User-Agent": "PrimeChopBot/1.0 (+https://primechop-production.up.railway.app)",
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                raw_body = await resp.text()
                data = self._parse_json(raw_body)
                if resp.status >= 400:
                    raise RuntimeError(f"Paystack verify failed: {self._response_message(data, raw_body, resp.status)}")
                if not isinstance(data, dict):
                    raise RuntimeError(
                        f"Paystack verify returned a non-JSON response (HTTP {resp.status}, {self._preview_body(raw_body)})"
                    )
                return data

    async def initialize_wallet_topup(
        self,
        amount: int,
        email: str,
        full_name: str,
        user_id: int,
    ) -> PaystackPaymentResult:
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
    ) -> PaystackPaymentResult:
        return await self.initialize_payment(
            amount=amount,
            email=email,
            full_name=full_name,
            reference_prefix=f"order_{order_ref}",
            user_id=user_id,
        )

    def _extract_checkout_url(self, data: dict) -> str:
        if not isinstance(data, dict):
            raise RuntimeError("Invalid Paystack response format")
        data_node = data.get("data") or {}
        if isinstance(data_node, dict):
            value = data_node.get("authorization_url")
            if value:
                return str(value)
        raise RuntimeError("Paystack response did not include an authorization URL")

    def _parse_json(self, raw_body: str):
        if not raw_body:
            return None
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError:
            return None

    def _preview_body(self, raw_body: str) -> str:
        preview = " ".join((raw_body or "").split())
        return preview[:240] if preview else "empty response body"

    def _response_message(self, data, raw_body: str, status_code: int) -> str:
        if isinstance(data, dict):
            message = str(data.get("message") or data.get("error") or data.get("detail") or "").strip()
            if message:
                return message
        return f"HTTP {status_code} ({self._preview_body(raw_body)})"

    def is_valid_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        if not signature or not self.secret_key:
            return False
        computed = hmac.new(
            self.secret_key.encode("utf-8"),
            raw_body,
            hashlib.sha512,
        ).hexdigest().lower()
        return hmac.compare_digest(computed, signature.strip().lower())
