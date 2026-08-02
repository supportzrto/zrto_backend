import hashlib
import hmac
import json
import traceback
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session

from auth import get_current_user
from database import SessionLocal
from models import User
from whatsapp import config, service
from whatsapp.models import Brand, MessageLog, VerificationOrder
from whatsapp.schemas import (
    BrandCreate,
    BrandUpdate,
    ManualActionRequest,
    OrderCreate,
    PredictRiskRequest,
    ReminderRequest,
    SendWhatsAppRequest,
)

router = APIRouter(tags=["whatsapp"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _owned_brand_ids(db: Session, user: User) -> list:
    return [b.id for b in db.query(Brand.id).filter(Brand.user_id == user.id).all()]


def _get_owned_brand(db: Session, brand_id: int, user: User) -> Brand:
    brand = db.query(Brand).filter(Brand.id == brand_id, Brand.user_id == user.id).first()
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    return brand


def _get_owned_order(db: Session, pk: int, user: User) -> VerificationOrder:
    order = (
        db.query(VerificationOrder)
        .join(Brand, VerificationOrder.brand_id == Brand.id)
        .filter(VerificationOrder.id == pk, Brand.user_id == user.id)
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

@router.post("/api/orders")
def create_order(data: OrderCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    _get_owned_brand(db, data.brand_id, user)
    order = service.create_order(db, data)

    if data.auto_verify and service.should_verify(order.risk_category):
        try:
            service.send_verification(db, order)
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    return {"order": order.to_dict()}


@router.get("/api/orders")
def list_orders(db: Session = Depends(get_db), user: User = Depends(get_current_user), brand_id: int = Query(None)):
    if brand_id:
        _get_owned_brand(db, brand_id, user)
        q = db.query(VerificationOrder).filter(VerificationOrder.brand_id == brand_id)
    else:
        q = db.query(VerificationOrder).filter(VerificationOrder.brand_id.in_(_owned_brand_ids(db, user)))
    return {"total": q.count(), "orders": [o.to_dict() for o in q.order_by(VerificationOrder.created_at.desc()).all()]}


@router.get("/api/orders/{pk}")
def order_detail(pk: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _get_owned_order(db, pk, user)

    logs = (
        db.query(MessageLog)
        .filter(MessageLog.order_pk == pk)
        .order_by(MessageLog.timestamp.asc())
        .all()
    )

    timeline = [{"event": "Order created", "time": order.created_at.isoformat() if order.created_at else None}]
    for log in logs:
        label = {
            "Initial Verification": "WhatsApp verification message sent",
            "Reminder": "Reminder message sent",
            "Customer Response": f"Customer replied: {order.customer_response or 'response received'}",
        }.get(log.message_type, log.message_type or "Message event")
        timeline.append({"event": label, "time": log.timestamp.isoformat() if log.timestamp else None})
    if order.order_status:
        end_time = order.updated_at or order.created_at
        timeline.append({"event": f"Status: {order.order_status}", "time": end_time.isoformat() if end_time else None})

    return {"order": order.to_dict(), "logs": [l.to_dict() for l in logs], "timeline": timeline}


@router.post("/api/orders/{pk}/action")
def order_action(pk: int, body: ManualActionRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _get_owned_order(db, pk, user)
    try:
        service.manual_action(db, order, body.action)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


@router.post("/api/send-whatsapp")
def send_whatsapp(body: SendWhatsAppRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _get_owned_order(db, body.order_pk, user)
    try:
        service.send_verification(db, order)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True}


@router.post("/api/reminder")
def send_reminder(body: ReminderRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    order = _get_owned_order(db, body.order_pk, user)
    try:
        result = service.send_reminder(db, order)
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# Meta webhook (no user auth — Meta calls this directly — but signature-verified)
# ---------------------------------------------------------------------------

@router.get("/api/webhooks/whatsapp")
@router.get("/webhooks/whatsapp")
def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge)

    raise HTTPException(status_code=403, detail="Verification failed")


def _verify_meta_signature(raw_body: bytes, signature_header: str) -> bool:
    """Validate Meta's X-Hub-Signature-256 HMAC so forged webhook calls are rejected."""
    if not config.WHATSAPP_APP_SECRET:
        # No app secret configured — cannot verify. Fail closed rather than silently
        # accepting unsigned requests.
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        config.WHATSAPP_APP_SECRET.encode("utf-8"), raw_body, hashlib.sha256
    ).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)


@router.post("/webhooks/whatsapp")
@router.post("/api/webhooks/whatsapp")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()

    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_meta_signature(raw_body, signature):
        # Don't leak *why* — just reject. Avoids helping an attacker iterate toward
        # a valid forged signature.
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = json.loads(raw_body)
    service.handle_webhook(db, payload)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Dashboard / analytics
# ---------------------------------------------------------------------------

@router.get("/api/dashboard")
def dashboard(brand_id: int = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if brand_id:
        _get_owned_brand(db, brand_id, user)
        return service.dashboard_metrics(db, brand_id)
    return service.dashboard_metrics(db, brand_ids=_owned_brand_ids(db, user))


@router.get("/api/analytics")
def analytics(brand_id: int = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if brand_id:
        _get_owned_brand(db, brand_id, user)
        return service.analytics(db, brand_id)
    return service.analytics(db, brand_ids=_owned_brand_ids(db, user))


# ---------------------------------------------------------------------------
# Brands — credentials live here, so these are the most sensitive endpoints
# ---------------------------------------------------------------------------

@router.get("/api/brands")
def list_brands(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    brands = db.query(Brand).filter(Brand.user_id == user.id).all()
    # Never return unmasked secrets in a list response.
    return {"brands": [b.to_dict(False) for b in brands]}


@router.post("/api/brands")
def create_brand(data: BrandCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    payload = data.dict(exclude_unset=True)
    payload["user_id"] = user.id  # force ownership to the caller, ignore any client-supplied value
    b = Brand(**payload)
    db.add(b)
    db.commit()
    db.refresh(b)
    # Echo back masked — the caller already has the value they just typed in.
    return {"brand": b.to_dict(False)}


@router.get("/api/brands/{id}")
def get_brand(id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = _get_owned_brand(db, id, user)
    # Secrets are write-only from the API's perspective: never echoed back, even to the owner.
    return {"brand": b.to_dict(False)}


@router.put("/api/brands/{id}")
def update_brand(id: int, data: BrandUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = _get_owned_brand(db, id, user)
    update_data = data.dict(exclude_unset=True)
    update_data.pop("user_id", None)  # ownership can't be reassigned via update
    for k, v in update_data.items():
        setattr(b, k, v)
    db.commit()
    return {"ok": True}


@router.delete("/api/brands/{id}")
def delete_brand(id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    b = _get_owned_brand(db, id, user)
    db.delete(b)
    db.commit()
    return {"ok": True}