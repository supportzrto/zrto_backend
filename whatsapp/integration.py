import pandas as pd
from sqlalchemy.orm import Session
from database import SessionLocal
from whatsapp import service
from whatsapp.models import Brand
from whatsapp.schemas import OrderCreate

def auto_verify_from_prediction(db: Session, *, brand_id: int, order_id: str, customer_name: str, phone_number: str, order_amount: float, probability: float = None, risk_score: float = None, risk_category: str = None, auto_send: bool = True) -> dict:
    if not (brand_id and customer_name and phone_number): return {"verification": "skipped"}
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand or not brand.whatsapp_enabled: return {"verification": "skipped"}

    score = service.normalise_risk_score(probability=probability, risk_score=risk_score)
    category = (risk_category or "").upper()
    if category not in ("LOW", "MEDIUM", "HIGH"): category = service.categorise_risk(score)

    # Only the ambiguous MEDIUM band goes through WhatsApp verification (matches
    # predict.py's decision(): HIGH is auto-blocked/converted to prepaid, LOW is
    # auto-allowed — neither needs a customer confirmation, so we don't create a
    # dashboard record that would otherwise sit "pending" forever.
    if not service.should_verify(category): return {"verification": "not_required"}

    order = service.create_order(db, OrderCreate(order_id=str(order_id), brand_id=brand_id, customer_name=customer_name, phone_number=phone_number, order_amount=float(order_amount or 0), risk_score=score, risk_category=category, auto_verify=False))

    try:
        service.send_verification(db, order)
        return {"verification": "sent"}
    except Exception:
        return {"verification": "send_failed"}

def build_prediction_records(df) -> list:
    records = []
    for _, row in df.iterrows():
        # 'VERIFY' is set by predict.py's decision() only for MEDIUM risk orders —
        # HIGH is auto-blocked/converted to prepaid, LOW is auto-allowed, neither
        # needs a WhatsApp check.
        decision = str(row.get("decision", "")).upper()
        if decision != "VERIFY":
            continue
        phone = row.get("phone_number") or row.get("phone")
        name = row.get("customer_name") or row.get("name")
        if not phone or not name: continue
        records.append({
            "order_id": str(row.get("order_id")), "order_value": float(row.get("order_value", 0)),
            "risk_score": float(row.get("risk_score", 0)) * 100.0, "risk_category": str(row.get("risk_level", "MEDIUM")).upper(),
            "phone_number": str(phone), "customer_name": str(name), "brand_id": row.get("brand_id")
        })
    return records

def resolve_brand_id(db: Session, explicit_brand_id=None, user_id=None):
    if explicit_brand_id: return explicit_brand_id
    if user_id:
        b = db.query(Brand).filter(Brand.user_id == user_id).first()
        if b: return b.id
    brands = db.query(Brand).all()
    if len(brands) == 1: return brands[0].id
    return None

def batch_auto_verify(records: list, default_brand_id=None, user_id=None) -> dict:
    db = SessionLocal()
    summary = {"sent": 0, "total": len(records)}
    try:
        brand = resolve_brand_id(db, default_brand_id, user_id)
        for r in records:
            res = auto_verify_from_prediction(db, brand_id=r.get("brand_id") or brand, order_id=r["order_id"], customer_name=r["customer_name"], phone_number=r["phone_number"], order_amount=r["order_value"], risk_score=r.get("risk_score"), risk_category=r.get("risk_category"))
            if res.get("verification") == "sent": summary["sent"] += 1
    finally: db.close()
    return summary