from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import is_internal_api_token_configured, settings
from app.core.db import get_db
from app.repositories.access_keys import get_latest_access_key_by_subscription
from app.repositories.subscriptions import (
    get_active_subscription_by_id,
    get_active_subscription_by_token,
)
from app.services.payment_activation import activate_order_from_payment
from app.services.vpn_service import build_vless_uri, get_server_for_access_key
from app.services.yookassa import YooKassaError

app = FastAPI(title="Subscription Bot API")


@app.get("/health")
async def health():
    return {"status": "ok"}


async def build_subscription_payload(session: AsyncSession, subscription_id: int) -> str:
    access_key = await get_latest_access_key_by_subscription(session, subscription_id)
    if not access_key or not access_key.uuid:
        raise HTTPException(status_code=404, detail="Subscription key not found")

    server = await get_server_for_access_key(session, access_key)
    if not server:
        if access_key.vless_uri:
            return access_key.vless_uri.strip()
        raise HTTPException(status_code=503, detail="No active VPN servers")

    label_suffix = str(access_key.device_id or subscription_id)
    return build_vless_uri(
        host=server.host,
        port=server.port,
        public_key=server.public_key,
        short_id=server.short_id,
        sni=server.sni,
        uuid=access_key.uuid,
        label=f"Nortic-{server.name}-{label_suffix}",
        flow=server.flow,
        security=server.security,
        transport=server.transport,
    )


@app.get("/s/{subscription_token}", response_class=PlainTextResponse)
async def subscription_by_token(subscription_token: str, session: AsyncSession = Depends(get_db)):
    subscription = await get_active_subscription_by_token(session, subscription_token)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    payload = await build_subscription_payload(session, subscription.id)
    return PlainTextResponse(
        payload,
        headers={
            "cache-control": "no-store",
            "x-subscription-source": "nortic-api",
        },
    )


@app.get("/sub/{subscription_id}", response_class=PlainTextResponse)
async def subscription_by_id(subscription_id: int, session: AsyncSession = Depends(get_db)):
    subscription = await get_active_subscription_by_id(session, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    payload = await build_subscription_payload(session, subscription.id)
    return PlainTextResponse(
        payload,
        headers={
            "cache-control": "no-store",
            "x-subscription-source": "nortic-api",
        },
    )


@app.post("/webhooks/yookassa")
async def yookassa_webhook(payload: dict, session: AsyncSession = Depends(get_db)):
    event = payload.get("event")
    obj = payload.get("object") or {}
    payment_id = obj.get("id")

    if not payment_id:
        raise HTTPException(status_code=400, detail="Missing payment id")

    if event != "payment.succeeded":
        return {"ok": True}

    try:
        result, order = await activate_order_from_payment(
            session=session,
            payment_id=str(payment_id),
            payment_provider="yookassa_sbp",
        )
    except YooKassaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        if detail == "PAYMENT_NOT_SUCCEEDED":
            return {"ok": True}
        if detail == "ORDER_ID_MISSING":
            raise HTTPException(status_code=400, detail="Missing order_id in payment metadata") from exc
        if detail == "ORDER_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Order not found") from exc
        if detail == "USER_NOT_FOUND":
            raise HTTPException(status_code=404, detail="User not found") from exc
        raise

    if result is None and order.status == "paid":
        return {"ok": True}

    return {"ok": True}


@app.post("/internal/yookassa/activate")
async def internal_yookassa_activate(
    payload: dict,
    session: AsyncSession = Depends(get_db),
    x_internal_token: str | None = Header(default=None),
):
    if not is_internal_api_token_configured():
        raise HTTPException(status_code=503, detail="Internal API token is not configured")

    if x_internal_token != settings.internal_api_token:
        raise HTTPException(status_code=401, detail="Invalid internal token")

    payment_id = payload.get("payment_id")
    if not payment_id:
        raise HTTPException(status_code=400, detail="Missing payment_id")

    payment_provider = str(payload.get("payment_provider") or "yookassa_sbp")

    try:
        result, order = await activate_order_from_payment(
            session=session,
            payment_id=str(payment_id),
            payment_provider=payment_provider,
        )
    except YooKassaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        detail = str(exc)
        if detail == "PAYMENT_NOT_SUCCEEDED":
            raise HTTPException(status_code=409, detail="Payment is not succeeded") from exc
        if detail == "ORDER_ID_MISSING":
            raise HTTPException(status_code=400, detail="Missing order_id in payment metadata") from exc
        if detail == "ORDER_NOT_FOUND":
            raise HTTPException(status_code=404, detail="Order not found") from exc
        if detail == "USER_NOT_FOUND":
            raise HTTPException(status_code=404, detail="User not found") from exc
        raise

    if result is None:
        return {"ok": True, "status": "already_paid", "order_id": order.id}

    return {"ok": True, "status": "activated", "order_id": order.id}
