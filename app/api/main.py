from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.repositories.orders import get_order_by_id
from app.repositories.users import get_user_by_id
from app.services.order_activation import activate_paid_order
from app.services.yookassa import YooKassaError, get_payment

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
        payment = await get_payment(str(payment_id))
    except YooKassaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if payment.status != "succeeded":
        return {"ok": True}

    order_id_raw = payment.metadata.get("order_id")
    if not order_id_raw:
        raise HTTPException(status_code=400, detail="Missing order_id in payment metadata")

    order = await get_order_by_id(session, int(order_id_raw))
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if order.status == "paid":
        return {"ok": True}

    user = await get_user_by_id(session, order.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await activate_paid_order(
        session=session,
        order=order,
        user=user,
        payment_id=payment.id,
        payment_provider="yookassa_sbp",
    )
    return {"ok": True}
