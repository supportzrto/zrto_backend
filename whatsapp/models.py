from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from database import Base
from whatsapp.config import DEFAULT_INITIAL_TEMPLATE, DEFAULT_REMINDER_DELAY_HOURS, DEFAULT_REMINDER_TEMPLATE, OrderStatus, VerificationStatus

class Brand(Base):
    __tablename__ = "wa_brands"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    brand_name = Column(String, nullable=False)
    whatsapp_phone_number_id = Column(String, default="YOUR_PHONE_NUMBER_ID")
    whatsapp_access_token = Column(String, default="YOUR_ACCESS_TOKEN")
    verify_token = Column(String, default="YOUR_VERIFY_TOKEN")
    webhook_url = Column(String, default="YOUR_WEBHOOK_URL")
    whatsapp_enabled = Column(Boolean, default=True)
    reminder_delay_hours = Column(Integer, default=DEFAULT_REMINDER_DELAY_HOURS)
    initial_template = Column(Text, default=DEFAULT_INITIAL_TEMPLATE)
    reminder_template = Column(Text, default=DEFAULT_REMINDER_TEMPLATE)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    orders = relationship("VerificationOrder", back_populates="brand", cascade="all, delete-orphan")

    def to_dict(self, include_secrets: bool = False):
        def mask(val: str) -> str:
            if not val or include_secrets: return val
            return (val[:4] + "••••") if len(val) > 4 else "••••"
        return {
            "id": self.id, "user_id": self.user_id, "brand_name": self.brand_name,
            "whatsapp_phone_number_id": self.whatsapp_phone_number_id,
            "whatsapp_access_token": mask(self.whatsapp_access_token),
            "verify_token": mask(self.verify_token), "webhook_url": self.webhook_url,
            "whatsapp_enabled": self.whatsapp_enabled, "reminder_delay_hours": self.reminder_delay_hours,
            "initial_template": self.initial_template, "reminder_template": self.reminder_template,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class VerificationOrder(Base):
    __tablename__ = "wa_orders"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(String, nullable=False, index=True)
    brand_id = Column(Integer, ForeignKey("wa_brands.id"), nullable=False, index=True)
    customer_name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    order_amount = Column(Float, default=0.0)
    risk_score = Column(Float, default=0.0)
    risk_category = Column(String, default="LOW")
    risk_factors = Column(Text, nullable=True)
    verification_status = Column(String, default=VerificationStatus.PENDING)
    order_status = Column(String, default=OrderStatus.AWAITING)
    message_id = Column(String, nullable=True)
    message_sent_time = Column(DateTime, nullable=True)
    reminder_message_id = Column(String, nullable=True)
    reminder_sent_time = Column(DateTime, nullable=True)
    customer_response = Column(String, nullable=True)
    response_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    brand = relationship("Brand", back_populates="orders")
    logs = relationship("MessageLog", back_populates="order", cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("brand_id", "order_id", name="uq_brand_order"),)

    def response_minutes(self):
        if self.message_sent_time and self.response_time:
            return round((self.response_time - self.message_sent_time).total_seconds() / 60.0, 2)
        return None

    def to_dict(self):
        return {
            "id": self.id, "order_id": self.order_id, "brand_id": self.brand_id,
            "brand_name": self.brand.brand_name if self.brand else None,
            "customer_name": self.customer_name, "phone_number": self.phone_number,
            "order_amount": self.order_amount, "risk_score": self.risk_score,
            "risk_category": self.risk_category, "risk_factors": self.risk_factors,
            "verification_status": self.verification_status, "order_status": self.order_status,
            "message_id": self.message_id, "message_sent_time": self.message_sent_time.isoformat() if self.message_sent_time else None,
            "reminder_sent_time": self.reminder_sent_time.isoformat() if self.reminder_sent_time else None,
            "customer_response": self.customer_response,
            "response_time": self.response_time.isoformat() if self.response_time else None,
            "response_minutes": self.response_minutes(),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class MessageLog(Base):
    __tablename__ = "wa_message_logs"
    id = Column(Integer, primary_key=True, index=True)
    order_pk = Column(Integer, ForeignKey("wa_orders.id"), nullable=True, index=True)
    order_id = Column(String, nullable=True, index=True)
    brand_id = Column(Integer, nullable=True, index=True)
    message_type = Column(String, nullable=True)
    message_id = Column(String, nullable=True, index=True)
    delivery_status = Column(String, nullable=True)
    read_status = Column(Boolean, default=False)
    webhook_payload = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    order = relationship("VerificationOrder", back_populates="logs")

    def to_dict(self):
        return {
            "id": self.id, "message_type": self.message_type, "message_id": self.message_id,
            "delivery_status": self.delivery_status, "read_status": self.read_status,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None
        }

class ProcessedWebhook(Base):
    __tablename__ = "wa_processed_webhooks"
    id = Column(Integer, primary_key=True, index=True)
    dedup_key = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)