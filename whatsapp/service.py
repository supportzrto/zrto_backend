import json
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from whatsapp import config
from whatsapp.client import (
    WhatsAppAPIError,
    send_interactive_message,
    send_template_message,
)
from whatsapp.models import Brand, MessageLog, ProcessedWebhook, VerificationOrder


def normalise_risk_score(
    *, probability: float = None, risk_score: float = None
) -> float:
    if risk_score is not None:
        return max(0.0, min(100.0, float(risk_score)))
    if probability is not None:
        return max(0.0, min(100.0, float(probability) * 100.0))
    return 0.0


def categorise_risk(score: float) -> str:
    if score <= config.RISK_LOW_MAX:
        return config.RiskCategory.LOW
    if score <= config.RISK_MEDIUM_MAX:
        return config.RiskCategory.MEDIUM
    return config.RiskCategory.HIGH


def should_verify(category: str) -> bool:
    return category in config.VERIFY_CATEGORIES


def render_template(template: str, order: VerificationOrder) -> str:
    try:
        return template.format(
            customer_name=order.customer_name or "Customer",
            order_id=order.order_id,
            order_amount=("%g" % order.order_amount) if order.order_amount else "0",
        )
    except Exception:
        return template


def create_order(db: Session, data) -> VerificationOrder:
    score = max(
        0.0, min(100.0, float(data.risk_score if data.risk_score is not None else 0.0))
    )
    category = data.risk_category or categorise_risk(score)
    order = (
        db.query(VerificationOrder)
        .filter(
            VerificationOrder.brand_id == data.brand_id,
            VerificationOrder.order_id == data.order_id,
        )
        .first()
    )
    if not order:
        order = VerificationOrder(brand_id=data.brand_id, order_id=data.order_id)
        db.add(order)
    order.customer_name = data.customer_name
    order.phone_number = data.phone_number
    order.order_amount = data.order_amount
    order.risk_score = score
    order.risk_category = category
    order.risk_factors = data.risk_factors
    order.verification_status = config.VerificationStatus.PENDING
    order.order_status = config.OrderStatus.AWAITING
    db.commit()
    db.refresh(order)
    return order


def _log_message(db, order, message_type, message_id, delivery_status, payload):
    db.add(
        MessageLog(
            order_pk=order.id,
            order_id=order.order_id,
            brand_id=order.brand_id,
            message_type=message_type,
            message_id=message_id,
            delivery_status=delivery_status,
            webhook_payload=json.dumps(payload) if payload else None,
        )
    )
    db.commit()


def send_verification(db: Session, order: VerificationOrder) -> dict:
    brand = db.query(Brand).filter(Brand.id == order.brand_id).first()
    if not brand or not brand.whatsapp_enabled:
        raise WhatsAppAPIError("Brand disabled or not found")
    resp = send_template_message(
        phone_number_id=brand.whatsapp_phone_number_id,
        access_token=brand.whatsapp_access_token,
        to=order.phone_number,
        template_name=brand.template_name,
        customer_name=order.customer_name,
        order_id=order.order_id,
        order_amount=order.order_amount,
    )
    msg_id = resp["messages"][0]["id"] if "messages" in resp else None
    order.message_id = msg_id
    order.message_sent_time = datetime.utcnow()
    db.commit()
    db.refresh(order)
    _log_message(db, order, config.MessageType.INITIAL, msg_id, "sent", resp)
    return {"message_id": msg_id, "simulated": resp.get("_simulated", False)}


def send_reminder(db: Session, order: VerificationOrder) -> dict:
    brand = db.query(Brand).filter(Brand.id == order.brand_id).first()
    if not brand or not brand.whatsapp_enabled:
        raise WhatsAppAPIError("Brand disabled")
    resp = send_interactive_message(
        phone_number_id=brand.whatsapp_phone_number_id,
        access_token=brand.whatsapp_access_token,
        to=order.phone_number,
        body_text=render_template(
            brand.reminder_template or config.DEFAULT_REMINDER_TEMPLATE, order
        ),
    )
    msg_id = resp["messages"][0]["id"] if "messages" in resp else None
    order.reminder_message_id = msg_id
    order.reminder_sent_time = datetime.utcnow()
    db.commit()
    db.refresh(order)
    _log_message(db, order, config.MessageType.REMINDER, msg_id, "sent", resp)
    return {"message_id": msg_id, "simulated": resp.get("_simulated", False)}


def _already_processed(db, key):
    if not key:
        return False
    if db.query(ProcessedWebhook).filter(ProcessedWebhook.dedup_key == key).first():
        return True
    db.add(ProcessedWebhook(dedup_key=key))
    db.commit()
    return False


def handle_webhook(db: Session, payload: dict) -> dict:
    results = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            val = change.get("value", {})
            for msg in val.get("messages", []):
                wamid = msg.get("id")
                reply_id = None
                if (
                    msg.get("type") == "interactive"
                    and msg.get("interactive", {}).get("type") == "button_reply"
                ):
                    reply_id = msg["interactive"]["button_reply"]["id"]
                if not reply_id or _already_processed(db, f"reply:{wamid}"):
                    continue
                order = (
                    db.query(VerificationOrder)
                    .filter(
                        VerificationOrder.phone_number == msg.get("from"),
                        VerificationOrder.verification_status
                        == config.VerificationStatus.PENDING,
                    )
                    .order_by(VerificationOrder.message_sent_time.desc())
                    .first()
                )
                if not order:
                    continue

                if reply_id == config.BTN_CONFIRM_ID:
                    (
                        order.verification_status,
                        order.order_status,
                        order.customer_response,
                    ) = (
                        config.VerificationStatus.VERIFIED,
                        config.OrderStatus.CONFIRMED,
                        "Confirm Order",
                    )
                elif reply_id == config.BTN_CANCEL_ID:
                    (
                        order.verification_status,
                        order.order_status,
                        order.customer_response,
                    ) = (
                        config.VerificationStatus.REJECTED,
                        config.OrderStatus.CANCELLED,
                        "Cancel Order",
                    )
                order.response_time = datetime.utcnow()
                db.commit()
                _log_message(
                    db,
                    order,
                    "Customer Response",
                    wamid,
                    "received",
                    {"button_reply_id": reply_id},
                )
                results.append({"wamid": wamid, "status": "processed"})

            for status in val.get("statuses", []):
                wamid = status.get("id")
                state = status.get("status")
                if not wamid or _already_processed(db, f"status:{wamid}:{state}"):
                    continue
                log = (
                    db.query(MessageLog)
                    .filter(MessageLog.message_id == wamid)
                    .order_by(MessageLog.id.desc())
                    .first()
                )
                if log:
                    log.delivery_status = state
                    if state == "read":
                        log.read_status = True
                    db.commit()
    return {"handled": len(results), "results": results}


def process_pending_orders(db: Session) -> dict:
    now = datetime.utcnow()
    reminders, no_resp = 0, 0
    for order in (
        db.query(VerificationOrder)
        .filter(
            VerificationOrder.verification_status == config.VerificationStatus.PENDING,
            VerificationOrder.message_sent_time.isnot(None),
        )
        .all()
    ):
        brand = db.query(Brand).filter(Brand.id == order.brand_id).first()
        if not brand or not brand.whatsapp_enabled:
            continue

        if order.reminder_sent_time:
            if now >= order.reminder_sent_time + timedelta(
                hours=config.NO_RESPONSE_GRACE_HOURS
            ):
                order.verification_status, order.order_status = (
                    config.VerificationStatus.NO_RESPONSE,
                    config.OrderStatus.MANUAL_REVIEW,
                )
                db.commit()
                no_resp += 1
        elif now >= order.message_sent_time + timedelta(
            hours=brand.reminder_delay_hours or config.DEFAULT_REMINDER_DELAY_HOURS
        ):
            try:
                send_reminder(db, order)
                reminders += 1
            except Exception:
                pass
    return {"reminders_sent": reminders, "marked_no_response": no_resp}


def manual_action(db: Session, order: VerificationOrder, action: str) -> dict:
    if action == "resend":
        return send_verification(db, order)
    if action == "mark_verified":
        (
            order.verification_status,
            order.order_status,
            order.customer_response,
            order.response_time,
        ) = (
            config.VerificationStatus.VERIFIED,
            config.OrderStatus.CONFIRMED,
            "Manually Verified",
            datetime.utcnow(),
        )
    elif action == "mark_rejected":
        (
            order.verification_status,
            order.order_status,
            order.customer_response,
            order.response_time,
        ) = (
            config.VerificationStatus.REJECTED,
            config.OrderStatus.CANCELLED,
            "Manually Rejected",
            datetime.utcnow(),
        )
    elif action == "hold":
        order.order_status = config.OrderStatus.ON_HOLD
    elif action == "manual_review":
        order.order_status = config.OrderStatus.MANUAL_REVIEW
    elif action == "ship":
        order.order_status = config.OrderStatus.SHIPPED
    db.commit()
    return {"order_status": order.order_status}


def dashboard_metrics(db: Session, brand_id: int = None) -> dict:
    q = db.query(VerificationOrder)
    if brand_id:
        q = q.filter(VerificationOrder.brand_id == brand_id)
    orders = q.all()
    v = sum(
        1 for o in orders if o.verification_status == config.VerificationStatus.VERIFIED
    )
    r = sum(
        1 for o in orders if o.verification_status == config.VerificationStatus.REJECTED
    )
    n = sum(
        1
        for o in orders
        if o.verification_status == config.VerificationStatus.NO_RESPONSE
    )
    rt = [o.response_minutes() for o in orders if o.response_minutes() is not None]
    return {
        "total_orders": len(orders),
        "risky_orders": sum(
            1 for o in orders if o.risk_category in config.VERIFY_CATEGORIES
        ),
        "verified_orders": v,
        "rejected_orders": r,
        "pending_orders": sum(
            1
            for o in orders
            if o.verification_status == config.VerificationStatus.PENDING
        ),
        "no_response_orders": n,
        "verification_rate": round((v / (v + r + n)) * 100, 2) if (v + r + n) else 0.0,
        "revenue_saved": round(
            sum(
                o.order_amount
                for o in orders
                if o.verification_status == config.VerificationStatus.REJECTED
            ),
            2,
        ),
        "average_response_time_minutes": round(sum(rt) / len(rt), 2) if rt else 0.0,
    }


def analytics(db: Session, brand_id: int = None) -> dict:
    return dashboard_metrics(
        db, brand_id
    )  # Simplify for space, frontend uses these keys
