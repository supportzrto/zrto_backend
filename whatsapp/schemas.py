from typing import Optional
from pydantic import BaseModel, Field

class BrandCreate(BaseModel):
    brand_name: str
    whatsapp_phone_number_id: str = "YOUR_PHONE_NUMBER_ID"
    whatsapp_access_token: str = "YOUR_ACCESS_TOKEN"
    verify_token: str = "YOUR_VERIFY_TOKEN"
    webhook_url: str = "YOUR_WEBHOOK_URL"
    whatsapp_enabled: bool = True
    reminder_delay_hours: int = 8
    initial_template: Optional[str] = None
    reminder_template: Optional[str] = None
    user_id: Optional[int] = None

class BrandUpdate(BaseModel):
    brand_name: Optional[str] = None
    whatsapp_phone_number_id: Optional[str] = None
    whatsapp_access_token: Optional[str] = None
    verify_token: Optional[str] = None
    webhook_url: Optional[str] = None
    whatsapp_enabled: Optional[bool] = None
    reminder_delay_hours: Optional[int] = None
    initial_template: Optional[str] = None
    reminder_template: Optional[str] = None

class OrderCreate(BaseModel):
    order_id: str
    brand_id: int
    customer_name: str
    phone_number: str
    order_amount: float = 0.0
    risk_score: Optional[float] = None
    risk_category: Optional[str] = None
    risk_factors: Optional[str] = None
    auto_verify: bool = True

class PredictRiskRequest(BaseModel):
    order_id: Optional[str] = None
    order_amount: float = 0.0
    probability: Optional[float] = Field(None, ge=0.0, le=1.0)
    risk_score: Optional[float] = Field(None, ge=0.0, le=100.0)
    risk_factors: Optional[str] = None

class SendWhatsAppRequest(BaseModel):
    order_pk: int

class ReminderRequest(BaseModel):
    order_pk: int

class ManualActionRequest(BaseModel):
    action: str