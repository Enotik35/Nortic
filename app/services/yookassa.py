from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import is_yookassa_configured, settings


YOOKASSA_API_URL = "https://api.yookassa.ru/v3"


class YooKassaError(Exception):
    pass


@dataclass(slots=True)
class YooKassaPayment:
    id: str
    status: str
    confirmation_url: str | None
    metadata: dict[str, Any]


def amount_to_rub_value(amount_rub: int) -> str:
    return str(Decimal(amount_rub).quantize(Decimal("1.00")))


async def _request(method: str, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    if not is_yookassa_configured():
        raise YooKassaError("YooKassa is not configured")

    headers: dict[str, str] = {}
    if method.upper() == "POST":
        headers["Idempotence-Key"] = str(uuid4())

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.request(
            method,
            f"{YOOKASSA_API_URL}{path}",
            json=body,
            headers=headers,
            auth=(settings.yookassa_shop_id, settings.yookassa_secret_key),
        )

    if response.status_code >= 400:
        raise YooKassaError(f"YooKassa request failed: {response.status_code} {response.text}")

    return response.json()


def _parse_payment(payload: dict[str, Any]) -> YooKassaPayment:
    confirmation = payload.get("confirmation") or {}
    metadata = payload.get("metadata") or {}
    return YooKassaPayment(
        id=str(payload["id"]),
        status=str(payload["status"]),
        confirmation_url=confirmation.get("confirmation_url"),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


async def create_payment(*, order_id: int, amount_rub: int, description: str) -> YooKassaPayment:
    payload = {
        "amount": {
            "value": amount_to_rub_value(amount_rub),
            "currency": "RUB",
        },
        "capture": True,
        "confirmation": {
            "type": "redirect",
            "return_url": settings.yookassa_return_url,
        },
        "description": description,
        "metadata": {
            "order_id": str(order_id),
        },
    }
    response = await _request("POST", "/payments", body=payload)
    return _parse_payment(response)


async def create_sbp_payment(*, order_id: int, amount_rub: int, description: str) -> YooKassaPayment:
    return await create_payment(
        order_id=order_id,
        amount_rub=amount_rub,
        description=description,
    )


async def get_payment(payment_id: str) -> YooKassaPayment:
    response = await _request("GET", f"/payments/{payment_id}")
    return _parse_payment(response)
