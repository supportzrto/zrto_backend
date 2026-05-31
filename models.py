from sqlalchemy import Column, Integer, String, Float, DateTime,Boolean,ForeignKey,Text
from database import Base
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    company_name = Column(String, nullable=True)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    plan = Column(String, default="free")
    usage_count = Column(Integer, default=0)
    # api_key = Column(String, unique=True)
    # api_enable = Column(Boolean,default=True)
    email_verified = Column(Boolean,default=False)
    phone = Column(String, nullable=True)
    verification_token = Column(String)
    is_admin = Column(Boolean,default=False)
    api_purchased = Column(Boolean, default=False)  
    api_key = Column(String, nullable=True)         
    api_enable = Column(Boolean, default=False)
    role = Column(String, default="user")
    subscription_start = Column(DateTime, nullable=True)
    subscription_end = Column(DateTime, nullable=True)


class APILog(Base):
    __tablename__ = "api_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)

    order_id = Column(String)

    risk_score = Column(Float)
    decision = Column(String)

    created_at = Column(DateTime, default=datetime.utcnow)

class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    total_orders = Column(Integer)
    risky_orders = Column(Integer)
    verify_orders = Column(Integer)
    safe_orders = Column(Integer)
    potential_savings = Column(Float)
    file_id = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    result_json = Column(Text, nullable=True)

class PredictionLog(Base):
    __tablename__ = "prediction_logs"

    id = Column(Integer, primary_key=True, index=True)
    prediction_id = Column(Integer, index=True)
    user_id = Column(Integer)
    order_id = Column(String)
    risk_level = Column(String)
    order_value = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    decision = Column(String)

class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    razorpay_order_id = Column(String, nullable=False)
    razorpay_payment_id = Column(String, nullable=False)

    amount = Column(Integer)
    status = Column(String, default="success")

    created_at = Column(DateTime, default=datetime.utcnow)

class EarlyAccess(Base):
    __tablename__ = "early_access"

    id = Column(Integer, primary_key=True)
    full_name = Column(String)
    email = Column(String)
    brand_name = Column(String)
    monthly_orders = Column(String)
    phone = Column(String)

