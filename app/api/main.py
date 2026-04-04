from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import is_internal_api_token_configured, settings
from app.core.db import get_db
from app.services.payment_activation import activate_order_from_payment
from app.services.yookassa import YooKassaError

app = FastAPI(title="Subscription Bot API")


@app.get("/health")
async def health():
    return {"status": "ok"}


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
