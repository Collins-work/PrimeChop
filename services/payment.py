from dataclasses import dataclass
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
            "callback_url": self.callback_url,
            "email": email,
            "metadata": {
                "full_name": full_name,
            },
        }

        headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.initialize_url, json=payload, headers=headers) as resp:
                data = await resp.json(content_type=None)
                if resp.status >= 400:
                    message = data.get("message") if isinstance(data, dict) else str(data)
                    raise RuntimeError(f"Kora Pay initialize failed: {message}")
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
