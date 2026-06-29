from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy.orm import Session
from database import SessionLocal
from whatsapp import config, service
from whatsapp.models import Brand, VerificationOrder
from whatsapp.schemas import BrandCreate, BrandUpdate, ManualActionRequest, OrderCreate, PredictRiskRequest, ReminderRequest, SendWhatsAppRequest
import traceback

router = APIRouter(tags=["whatsapp"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

@router.post("/api/orders")
def create_order(data: OrderCreate, db: Session = Depends(get_db)):
    order = service.create_order(db, data)

    if data.auto_verify and service.should_verify(order.risk_category):
        try:
            service.send_verification(db, order)
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))

    return {"order": order.to_dict()}

@router.get("/api/orders")
def list_orders(db: Session = Depends(get_db), brand_id: int = Query(None)):
    q = db.query(VerificationOrder)
    if brand_id: q = q.filter(VerificationOrder.brand_id == brand_id)
    return {"total": q.count(), "orders": [o.to_dict() for o in q.order_by(VerificationOrder.created_at.desc()).all()]}

@router.get("/api/orders/{pk}")
def order_detail(pk: int, db: Session = Depends(get_db)):
    order = db.query(VerificationOrder).filter(VerificationOrder.id == pk).first()
    return {"order": order.to_dict(), "logs": [], "timeline": []}

@router.post("/api/orders/{pk}/action")
def order_action(pk: int, body: ManualActionRequest, db: Session = Depends(get_db)):
    order = db.query(VerificationOrder).filter(VerificationOrder.id == pk).first()
    service.manual_action(db, order, body.action)
    return {"ok": True}

@router.post("/api/send-whatsapp")
def send_whatsapp(body: SendWhatsAppRequest, db: Session = Depends(get_db)):
    order = db.query(VerificationOrder).filter(VerificationOrder.id == body.order_pk).first()
    service.send_verification(db, order)
    return {"ok": True}

@router.get("/api/webhooks/whatsapp")
@router.get("/webhooks/whatsapp")
def verify_webhook(request: Request):

    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == config.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge)

    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("/api/webhooks/whatsapp")
@router.post("/webhooks/whatsapp")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    print("🔥🔥🔥 WEBHOOK RECEIVED 🔥🔥🔥")
    payload = await request.json()
    print(payload)
    service.handle_webhook(db, payload)
    return JSONResponse(content={"ok": True})

@router.get("/api/dashboard")
def dashboard(brand_id: int = Query(None), db: Session = Depends(get_db)):
    return service.dashboard_metrics(db, brand_id)

@router.get("/api/analytics")
def analytics(brand_id: int = Query(None), db: Session = Depends(get_db)):
    m = service.dashboard_metrics(db, brand_id)
    m["daily_verifications"] = []
    m["risk_distribution"] = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    m["cancellation_rate"] = 0
    m["no_response_rate"] = 0
    return m

@router.get("/api/brands")
def list_brands(db: Session = Depends(get_db)):
    return {"brands": [b.to_dict() for b in db.query(Brand).all()]}

@router.post("/api/brands")
def create_brand(data: BrandCreate, db: Session = Depends(get_db)):
    b = Brand(**data.dict(exclude_unset=True))
    db.add(b); db.commit(); db.refresh(b)
    return {"brand": b.to_dict(True)}

@router.get("/api/brands/{id}")
def get_brand(id: int, db: Session = Depends(get_db)):
    return {"brand": db.query(Brand).filter(Brand.id == id).first().to_dict(True)}

@router.put("/api/brands/{id}")
def update_brand(id: int, data: BrandUpdate, db: Session = Depends(get_db)):
    b = db.query(Brand).filter(Brand.id == id).first()
    for k, v in data.dict(exclude_unset=True).items(): setattr(b, k, v)
    db.commit()
    return {"ok": True}