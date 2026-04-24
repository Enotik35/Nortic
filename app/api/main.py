import base64
from datetime import timezone
import re

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import is_internal_api_token_configured, settings
from app.core.db import get_db
from app.init_data import upsert_server, upsert_tariffs
from app.models.order import Order
from app.models.tariff import Tariff
from app.models.user import User
from app.repositories.access_keys import get_latest_access_key_by_subscription
from app.repositories.servers import get_active_servers
from app.repositories.subscriptions import (
    get_active_subscription_by_id,
    get_active_subscription_by_token,
)
from app.services.payment_activation import activate_order_from_payment
from app.services.vpn_service import (
    build_vless_uri,
    ensure_access_key_on_active_servers,
)
from app.services.yookassa import YooKassaError

app = FastAPI(title="Subscription Bot API")


@app.on_event("startup")
async def sync_seed_data_on_startup() -> None:
    await upsert_tariffs()
    await upsert_server()


@app.get("/health")
async def health():
    return {"status": "ok"}


def encode_profile_header(value: str) -> str:
    encoded = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return f"base64:{encoded}"


def prettify_profile_title(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ")).strip()
    return cleaned or "Nortic"


def build_node_label(server_name: str) -> str:
    normalized = server_name.replace("_", " ").replace("-", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    normalized = re.sub(r"^(nortic)\s+", "", normalized, flags=re.IGNORECASE)
    return f"Nortic {normalized}".strip()


def build_happ_routing_rule_line() -> str | None:
    routing_rule_url = settings.happ_routing_rule_url.strip()
    if not routing_rule_url:
        return None
    return routing_rule_url


async def build_subscription_headers(session: AsyncSession, subscription) -> dict[str, str]:
    title = prettify_profile_title(settings.subscription_profile_title)
    headers = {
        "cache-control": "no-store",
        "x-subscription-source": "nortic-api",
        "profile-title": encode_profile_header(title),
        "Profile-Title": encode_profile_header(title),
        "profile-update-interval": str(settings.subscription_update_interval_hours),
        "Profile-Update-Interval": str(settings.subscription_update_interval_hours),
        "content-disposition": 'attachment; filename="nortic-subscription.txt"',
    }

    if settings.support_url.strip():
        headers["support-url"] = settings.support_url.strip()
        headers["Support-Url"] = settings.support_url.strip()

    profile_url = settings.subscription_profile_url.strip() or settings.instruction_url.strip()
    if profile_url:
        headers["profile-web-page-url"] = profile_url
        headers["Profile-Web-Page-Url"] = profile_url

    announce = settings.subscription_announce.strip()
    if announce:
        encoded_announce = encode_profile_header(announce)
        headers["announce"] = encoded_announce
        headers["Announce"] = encoded_announce

    total_bytes = 0
    if subscription.order_id:
        result = await session.execute(
            select(Tariff.traffic_limit_gb)
            .join(Order, Order.tariff_id == Tariff.id)
            .where(Order.id == subscription.order_id)
        )
        traffic_limit_gb = result.scalar_one_or_none()
        if traffic_limit_gb:
            total_bytes = int(traffic_limit_gb) * 1024 * 1024 * 1024

    expire_ts = int(subscription.end_at.replace(tzinfo=timezone.utc).timestamp())
    userinfo = f"upload=0; download=0; total={total_bytes}; expire={expire_ts}"
    headers["subscription-userinfo"] = userinfo
    headers["Subscription-Userinfo"] = userinfo
    return headers


async def build_subscription_payload(session: AsyncSession, subscription) -> tuple[str, dict[str, str]]:
    access_key = await get_latest_access_key_by_subscription(session, subscription.id)
    if not access_key or not access_key.uuid:
        raise HTTPException(status_code=404, detail="Subscription key not found")

    result = await session.execute(select(User).where(User.id == access_key.user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Subscription user not found")

    try:
        await ensure_access_key_on_active_servers(
            session=session,
            access_key=access_key,
            subscription=subscription,
            user=user,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "NO_ACTIVE_SERVER":
            if access_key.vless_uri:
                headers = await build_subscription_headers(session, subscription)
                return access_key.vless_uri.strip(), headers
            raise HTTPException(status_code=503, detail="No active VPN servers") from exc
        if detail.startswith("SERVER_PANEL_CONFIG_MISSING:"):
            raise HTTPException(status_code=503, detail=detail) from exc
        raise

    servers = await get_active_servers(session)
    if not servers:
        if access_key.vless_uri:
            headers = await build_subscription_headers(session, subscription)
            return access_key.vless_uri.strip(), headers
        raise HTTPException(status_code=503, detail="No active VPN servers")

    payload_lines = [
        build_vless_uri(
            host=server.host,
            port=server.port,
            public_key=server.public_key,
            short_id=server.short_id,
            sni=server.sni,
            uuid=access_key.uuid,
            label=build_node_label(server.name),
            flow=server.flow,
            security=server.security,
            transport=server.transport,
        )
        for server in servers
    ]
    routing_rule_line = build_happ_routing_rule_line()
    if routing_rule_line:
        payload_lines.append(routing_rule_line)
    payload = "\n".join(payload_lines)
    headers = await build_subscription_headers(session, subscription)
    return payload, headers


@app.get("/s/{subscription_token}", response_class=PlainTextResponse)
async def subscription_by_token(subscription_token: str, session: AsyncSession = Depends(get_db)):
    subscription = await get_active_subscription_by_token(session, subscription_token)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    payload, headers = await build_subscription_payload(session, subscription)
    return PlainTextResponse(payload, headers=headers)


@app.get("/sub/{subscription_id}", response_class=PlainTextResponse)
async def subscription_by_id(subscription_id: int, session: AsyncSession = Depends(get_db)):
    subscription = await get_active_subscription_by_id(session, subscription_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="Subscription not found")

    payload, headers = await build_subscription_payload(session, subscription)
    return PlainTextResponse(payload, headers=headers)


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
