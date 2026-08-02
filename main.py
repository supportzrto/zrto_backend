import email
import io
from pathlib import Path


from fastapi import (
    FastAPI,
    UploadFile,
    File,
    BackgroundTasks,
    HTTPException,
    Request,
    Depends,
    Header,
)
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    HTMLResponse,
    StreamingResponse,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi_mail import FastMail, MessageSchema
from requests import session
from sqlalchemy import Column, DateTime, Integer, String, func, create_engine, Text
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta, date
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from dotenv import load_dotenv
from fastapi import BackgroundTasks
from fastapi import Response, HTTPException, Depends
from cryptography.fernet import Fernet
from email.mime.text import MIMEText
from dotenv import load_dotenv
from fastapi.responses import FileResponse
from whatsapp.integration import (
    build_prediction_records,
    batch_auto_verify
)
from whatsapp.routes import router as whatsapp_router
from whatsapp.models import Brand, VerificationOrder, MessageLog, ProcessedWebhook
import pandas as pd
import shutil
import os
import uuid
import time
import threading

# import jwt
import smtplib
import random
import hashlib
import razorpay


from logger import log
from database import engine, Base, SessionLocal, engine
from models import Payment, User, Prediction, APILog, PredictionLog, EarlyAccess
from email_utils import send_verification_email, send_otp_email, conf

from fastapi import APIRouter, Request
from utils.file_manager import get_output_path
from predict import run_prediction_pipeline, predict_orders, calculate_savings, model

env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)


RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

Base.metadata.create_all(bind=engine)


# otp_store = {}
# conf = {}

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(password):
    return pwd_context.hash(password)


def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)


def hash_otp(otp: str):
    return hashlib.sha256(otp.encode()).hexdigest()


SECRET_KEY = os.getenv("JWT_SECRET")
ALGORITHM = os.getenv("JWT_ALGORITHM")

# def send_email_otp(to_email, otp):
#     sender = os.getenv("MAIL_USERNAME")
#     password = os.getenv("MAIL_PASSWORD")

#     subject = "Your OTP for Password Reset"
#     body = f"Your OTP is: {otp}. It expires in 5 minutes."

#     msg = MIMEText(body)
#     msg["Subject"] = subject
#     msg["From"] = sender
#     msg["To"] = to_email

#     try:
#         server = smtplib.SMTP("smtp.gmail.com", 587)
#         server.starttls()
#         server.login(sender, password)
#         server.sendmail(sender, to_email, msg.as_string())
#         server.quit()
#     except Exception as e:
#         print("Email error:", e)


def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=1440)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_and_update_subscription(user, db):
    if user.subscription_end and user.subscription_end < datetime.utcnow():
        user.plan = "free"
        user.plan_limit = 50
        user.used_predictions = 0
        db.commit()


def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = decode_token(token)

    user = db.query(User).filter(User.id == payload["user_id"]).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def get_admin_user(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized")
    return user


def admin_required(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    return user


def predict_orders_df(df):

    if "order_value" not in df.columns and "total_amount" in df.columns:
        df["order_value"] = df["total_amount"]

    if "order_id" not in df.columns and "customer_id" in df.columns:
        df["order_id"] = df["customer_id"]

    def get_decision(row):
        if row["order_value"] > 1500:
            return "BLOCK_COD"
        elif row["order_value"] > 800:
            return "VERIFY"
        else:
            return "ALLOW"

    df["decision"] = df.apply(get_decision, axis=1)

    df["risk_level"] = df["decision"].map(
        {"BLOCK_COD": "HIGH", "VERIFY": "MEDIUM", "ALLOW": "LOW"}
    )

    return df


def run_prediction(input_path, output_path):
    try:
        predict_orders(input_path, output_path)
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)


def save_predictions(df, user_id):
    db = SessionLocal()

    for _, row in df.iterrows():
        pred = Prediction(
            user_id=user_id,
            order_id=str(row["order_id"]),
            risk_level=row["risk_level"],
            order_value=float(row["order_value"]),
            created_at=datetime.utcnow(),
        )
        db.add(pred)


def cleanup_old_files():
    while True:
        folder = "."
        now = time.time()
        for file in os.listdir(folder):
            if file.startswith("output_") and file.endswith(".csv"):
                file_path = os.path.join(folder, file)
                if now - os.path.getmtime(file_path) > 259200:
                    os.remove(file_path)
                    print(f"Deleted old file: {file}")
        time.sleep(3600)


router = APIRouter()
app = FastAPI()

app.include_router(whatsapp_router)

cleanup_thread = threading.Thread(target=cleanup_old_files, daemon=True)
cleanup_thread.start()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://zrto.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse({"error": "Rate limit exceeded"}),
)
app.add_middleware(SlowAPIMiddleware)


class RegisterRequest(BaseModel):
    first_name: str
    last_name: str
    company_name: str | None = None
    email: str
    phone: str | None = None
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class OTP(Base):
    __tablename__ = "otp"

    id = Column(Integer, primary_key=True)
    email = Column(String)
    otp_hash = Column(String)
    expires_at = Column(DateTime)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class EmailSchema(BaseModel):
    email: EmailStr


class ResetPasswordSchema(BaseModel):
    email: EmailStr
    token: str
    new_password: str


class OTPVerifySchema(BaseModel):
    email: EmailStr
    otp: str


class OrderRequest(BaseModel):
    order_id: int
    order_value: float
    payment_type: str
    api_key: str
    pincode: int
    customer_city: str
    device_type: str
    order_channel: str
    num_previous_orders: int = 0
    payment_attempts: int = 1
    estimated_delivery_days: int = 5
    past_rto_count: int = 0
    courier: str = "Unknown"
    address_quality: int = 1


@app.post("/register")
async def register(
    data: RegisterRequest,
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    try:
        existing = db.query(User).filter(User.email == data.email).first()
        if existing:
            if not existing.email_verified:
                verification_token = str(uuid.uuid4())
                existing.verification_token = verification_token
                db.commit()
                background_tasks.add_task(
                    send_verification_email, data.email, verification_token
                )
                return {
                    "error": "already_registered_unverified",
                    "message": "Account exists but not verified. Verification email resent.",
                }
            return {"error": "User already exists"}

        verification_token = str(uuid.uuid4())
        new_user = User(
            first_name=data.first_name,
            last_name=data.last_name,
            company_name=data.company_name,
            email=data.email,
            phone=data.phone,
            password=hash_password(data.password),
            api_key=None,
            api_purchased=False,
            api_enable=False,
            email_verified=False,
            verification_token=verification_token,
            is_admin=False,
            plan="free",
            usage_count=0,
        )
        db.add(new_user)
        db.commit()

        background_tasks.add_task(
            send_verification_email, data.email, verification_token
        )

        return {"message": "User registered successfully"}

    except Exception as e:
        print("REGISTER ERROR:", e)
        return {"error": str(e)}


@app.post("/login")
async def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):

    # Find user
    user = db.query(User).filter(User.email == data.email).first()

    # User not found
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Wrong password
    if not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid password")

    # Email not verified
    if not user.email_verified:

        # Generate new verification token
        verification_token = str(uuid.uuid4())

        # Save token in database
        user.verification_token = verification_token
        db.commit()

        # Resend verification email
        await send_verification_email(user.email, verification_token)

        raise HTTPException(
            status_code=403, detail="Email not verified. Verification email sent again."
        )

    # Create JWT token
    token = create_token({"user_id": user.id})

    # Set cookie
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=True,
        samesite="none",
        max_age=86400,
    )

    return {
        "message": "Login successful",
        "token": token,
        "role": user.role,
        "plan": user.plan,
        "user_id": user.id,
    }


@app.get("/verify-email/{token}")
def verify_email(token: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.verification_token == token).first()

    if not user:
        return HTMLResponse(
            content="""
            <html><head><title>Verification Failed</title>
            <meta http-equiv="refresh" content="3;url=https://zrto.vercel.app/login" />
            <style>
                body { font-family: Arial, sans-serif; display: flex; justify-content: center;
                       align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }
                .card { background: white; padding: 40px; border-radius: 12px;
                        text-align: center; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
                .icon { font-size: 60px; } h2 { color: #e53e3e; } p { color: #666; }
            </style></head>
            <body><div class="card"><div class="icon">❌</div>
            <h2>Invalid or Expired Link</h2>
            <p>This verification link is invalid or has already been used.</p>
            <p>Redirecting you back...</p></div></body></html>
        """,
            status_code=400,
        )

    user.email_verified = True
    user.verification_token = None
    user.api_enable = True
    db.commit()

    return HTMLResponse(content="""
        <html><head><title>Email Verified</title>
        <meta http-equiv="refresh" content="3;url=https://zrto.vercel.app/login" />
        <style>
            body { font-family: Arial, sans-serif; display: flex; justify-content: center;
                   align-items: center; height: 100vh; margin: 0; background: #f5f5f5; }
            .card { background: white; padding: 40px; border-radius: 12px;
                    text-align: center; box-shadow: 0 2px 12px rgba(0,0,0,0.1); }
            .icon { font-size: 60px; } h2 { color: #22c55e; } p { color: #666; }
            .bar { width: 100%; height: 4px; background: #e2e8f0; border-radius: 4px; margin-top: 20px; }
            .fill { height: 4px; background: #22c55e; border-radius: 4px;
                    animation: fill 3s linear forwards; }
            @keyframes fill { from { width: 0% } to { width: 100% } }
        </style></head>
        <body><div class="card"><div class="icon">✅</div>
        <h2>Email Verified Successfully!</h2>
        <p>Your account is now active. Redirecting to login...</p>
        <div class="bar"><div class="fill"></div></div>
        </div></body></html>
    """)


@app.get("/test-email")
async def test_email():
    try:
        await send_otp_email("ashokcivil27@gmail.com", "123456")
        return {"success": True}
    except Exception as e:
        return {"error": str(e)}


@app.post("/send-otp")
async def send_otp(data: EmailSchema, db: Session = Depends(get_db)):

    # Check user exists
    user = db.query(User).filter(User.email == data.email).first()
    if not user:
        return {"error": "User not found"}

    # Check 60 second cooldown using DB record
    existing = db.query(OTP).filter(OTP.email == data.email).first()
    if existing:
        seconds_since_sent = (datetime.utcnow() - existing.created_at).total_seconds()
        if seconds_since_sent < 60:
            return {"error": "Wait 60 seconds before requesting new OTP"}
        # Delete old OTP before creating new one
        db.delete(existing)
        db.commit()

    # Generate and store new OTP
    otp = str(random.randint(100000, 999999))

    new_otp = OTP(
        email=data.email,
        otp_hash=hash_otp(otp),
        expires_at=datetime.utcnow() + timedelta(minutes=5),
        attempts=0,
        created_at=datetime.utcnow(),
    )
    db.add(new_otp)
    db.commit()

    await send_otp_email(data.email, otp)

    return {"message": "OTP sent to your email"}


@app.post("/verify-otp")
def verify_otp(data: OTPVerifySchema, db: Session = Depends(get_db)):

    # Fetch OTP record from DB
    record = db.query(OTP).filter(OTP.email == data.email).first()

    if not record:
        return {"error": "OTP not found"}

    if datetime.utcnow() > record.expires_at:
        db.delete(record)
        db.commit()
        return {"error": "OTP expired"}

    if record.attempts >= 5:
        return {"error": "Too many attempts"}

    if record.otp_hash != hash_otp(data.otp.strip()):
        record.attempts += 1
        db.commit()
        return {"error": "Invalid OTP"}

    # OTP verified — delete record and issue token
    db.delete(record)
    db.commit()

    token = create_token({"email": data.email, "type": "reset"})

    return {"message": "OTP verified", "token": token}


@app.post("/reset-password")
def reset_password(data: ResetPasswordSchema, db: Session = Depends(get_db)):

    payload = decode_token(data.token)

    if not payload:
        return {"error": "Invalid or expired token"}

    if payload.get("type") != "reset":
        return {"error": "Invalid token type"}

    email = payload.get("email")

    user = db.query(User).filter(User.email == email).first()

    if not user:
        return {"error": "User not found"}

    user.password = hash_password(data.new_password)
    db.commit()

    return {"message": "Password reset successful"}


@app.delete("/delete-account")
def delete_account(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    try:

        db.query(APILog).filter(APILog.user_id == user.id).delete()
        db.query(Prediction).filter(Prediction.user_id == user.id).delete()
        db.query(User).filter(User.id == user.id).delete()
        db.commit()
        return {"message": "Account deleted successfully"}
    except Exception as e:
        db.rollback()
        return {"error": str(e)}


@app.get("/protected")
def protected(user: User = Depends(get_current_user)):
    return {"message": "Authenticated", "user_id": user.id}


@app.post("/create-order")
def create_order():
    order = client.order.create(
        {"amount": 499900, "currency": "INR", "payment_capture": 1}
    )
    return {"id": order["id"], "amount": order["amount"], "currency": order["currency"]}


@app.post("/verify-payment")
async def verify_payment(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await request.json()

    try:

        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": data.get("razorpay_order_id"),
                "razorpay_payment_id": data.get("razorpay_payment_id"),
                "razorpay_signature": data.get("razorpay_signature"),
            }
        )

        existing = (
            db.query(Payment)
            .filter(Payment.razorpay_payment_id == data.get("razorpay_payment_id"))
            .first()
        )

        if existing:
            return {"message": "Payment already processed"}

        payment = Payment(
            user_id=user.id,
            razorpay_order_id=data.get("razorpay_order_id"),
            razorpay_payment_id=data.get("razorpay_payment_id"),
            amount=499900,
            status="success",
        )

        db.add(payment)

        user.plan = "pro"
        user.subscription_start = datetime.utcnow()
        user.subscription_end = datetime.utcnow() + timedelta(days=30)

        db.commit()

        return {"message": "Payment successful"}

    except Exception as e:
        print("Verification failed:", e)
        return {"error": "Invalid payment"}


@app.get("/api/payments")
def get_payments(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    return db.query(Payment).filter(Payment.user_id == current_user.id).all()


@app.get("/")
def home():
    return {"message": "ZRTO API Running 🚀"}


@app.get("/usage")
def get_usage(user: User = Depends(get_current_user)):
    PLAN_LIMITS = {"free": 50, "pro": 5000}
    return {"used": user.usage_count, "limit": PLAN_LIMITS.get(user.plan, 50)}


@app.post("/predict")
@limiter.limit("10/minute")
async def predict(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # ✅ check subscription
    check_and_update_subscription(user, db)

    PLAN_LIMITS = {"free": 50, "pro": 5000}

    limit = PLAN_LIMITS.get(user.plan, 50)

    # ✅ validate file
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files allowed")

    try:
        # ✅ read CSV FIRST
        file.file.seek(0)
        df = pd.read_csv(file.file)

        # ✅ normalize columns
        df.columns = df.columns.str.lower().str.strip()

        # ✅ fallback column
        if "customer_city" not in df.columns and "address" in df.columns:
            df["customer_city"] = df["address"]

        total_rows = len(df)

        used = user.usage_count or 0
        remaining = limit - used

        if user.role != "admin" and remaining <= 0:
            return {
                "error": "free_limit_reached",
                "message": "You have reached your monthly limit. Upgrade to continue.",
                "used": used,
                "limit": limit,
            }

        if user.role != "admin" and total_rows > remaining:
            return {
                "error": "batch_limit_exceeded",
                "message": f"You can only process {remaining} more orders",
                "remaining": remaining,
                "fileHas": total_rows,
            }

        # ✅ run prediction
        # df = predict_orders_df(df)
        # ✅ run prediction
        df = run_prediction_pipeline(df)

        records = build_prediction_records(df)

        batch_auto_verify(records, user_id=user.id)

        import json

        result_json = df.to_json(orient="records")

        unique_id = str(uuid.uuid4())
        output_path = get_output_path(user.id)

        df.to_csv(output_path, index=False)

        savings = float(
            df[df["decision"] == "BLOCK_COD"]["order_value"].sum() * 0.6 * 0.5
        )

        # ✅ save summary
        prediction = Prediction(
            user_id=user.id,
            file_id=unique_id,
            total_orders=len(df),
            risky_orders=len(df[df["decision"] == "BLOCK_COD"]),
            verify_orders=len(df[df["decision"] == "VERIFY"]),
            safe_orders=len(df[df["decision"] == "ALLOW"]),
            potential_savings=savings,
            result_json=result_json,
        )

        db.add(prediction)
        db.commit()
        db.refresh(prediction)

        # ✅ save logs
        for _, row in df.iterrows():
            prediction_log = PredictionLog(
                prediction_id=prediction.id,
                user_id=user.id,
                order_id=str(row["order_id"]),
                risk_level=row["risk_level"],
                decision=row["decision"],
                order_value=float(row["order_value"]),
            )
            db.add(prediction_log)

        db.commit()

        # ✅ update usage ONCE
        if user.role != "admin":
            user.usage_count += total_rows
            db.commit()

        log("Prediction completed")

        return {
            "message": "Prediction completed",
            "total_orders": int(len(df)),
            "risky_orders": int(len(df[df["decision"] == "BLOCK_COD"])),
            "verify_orders": int(len(df[df["decision"] == "VERIFY"])),
            "safe_orders": int(len(df[df["decision"] == "ALLOW"])),
            "potential_savings": savings,
            "download_url": f"/download/{unique_id}",
        }

    except Exception as e:
        print("Error:", e)
        log(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# @app.get("/download/{file_path:path}")
# def download(file_path: str):
#     if not os.path.exists(file_path):
#         return {"error": "File not found"}

#     return FileResponse(file_path, media_type="text/csv", filename="result.csv")


@app.get("/download/{file_id}")
def download_file(
    file_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    prediction = (
        db.query(Prediction)
        .filter(Prediction.file_id == file_id, Prediction.user_id == user.id)
        .first()
    )

    if not prediction or not prediction.result_json:
        return JSONResponse(
            status_code=404,
            content={
                "error": "file_missing",
                "message": "File no longer available. Please run prediction again.",
            },
        )

    df = pd.read_json(prediction.result_json)
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_buffer.seek(0)

    return StreamingResponse(
        io.BytesIO(csv_buffer.getvalue().encode()),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=prediction_results.csv"},
    )


@app.post("/api/predict-order")
@limiter.limit("60/minute")
def predict_single_order(
    request: Request, order: OrderRequest, db: Session = Depends(get_db)
):

    api_key = order.api_key
    if not api_key:
        raise HTTPException(status_code=401, detail="API key missing")

    user = db.query(User).filter(User.api_key == api_key).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not user.api_purchased:
        raise HTTPException(
            status_code=403,
            detail="API access not purchased. Please upgrade your plan.",
        )

    if not user.api_enable:
        raise HTTPException(status_code=403, detail="API access disabled")

    if user.plan == "free" and user.usage_count >= 50:
        return {"error": "Usage limit reached"}

    df = pd.DataFrame([order.dict()])
    # ✅ run prediction
    df = run_prediction_pipeline(df)

    feature_cols = [
        "is_cod",
        "is_new_customer",
        "previous_rto_flag",
        "many_payment_attempts",
        "cod_high_value",
        "order_value",
        "estimated_delivery_days",
        "address_quality",
        "rto_rate_customer",
        "pincode_risk",
        "courier_performance",
        "city_risk",
        "device_risk",
        "channel_risk",
        "day_risk",
    ]

    X = df[feature_cols]
    prob = model.predict_proba(X)[0][1]
    decision = predict_orders(prob)

    user.usage_count += 1

    log_entry = APILog(
        user_id=user.id,
        order_id=str(order.order_id),
        risk_score=float(prob),
        decision=decision,
    )
    db.add(log_entry)
    db.commit()

    return {
        "risk_score": float(prob),
        "decision": decision,
    }


@app.get("/api/key")
def get_api_key(user: User = Depends(get_current_user)):
    if not user.api_purchased:
        return {"api_purchased": False, "api_key": None, "enabled": False}
    return {"api_purchased": True, "api_key": user.api_key, "enabled": user.api_enable}


@app.get("/api/me")
def get_current_user_data(current_user: User = Depends(get_current_user)):
    return {
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "company_name": current_user.company_name,
        "phone": current_user.phone,
        "email": current_user.email,
        "plan": current_user.plan,
        "role": current_user.role,
        "expiry": current_user.subscription_end,
    }


# @app.post("/early-access")
# def create_early_access(data: dict, db: Session = Depends(get_db)):
#     entry = EarlyAccess(
#         full_name=data.get("full_name"),
#         email=data.get("email"),
#         brand_name=data.get("brand_name"),
#         monthly_orders=data.get("monthly_orders"),
#     )

#     db.add(entry)
#     db.commit()

#     return {"message": "Saved successfully"}


@app.post("/api/regenerate-key")
def regenerate_key(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    user.api_key = str(uuid.uuid4())
    db.commit()
    return {"message": "API key regenerated", "api_key": user.api_key}


@app.post("/api/key/disable")
def disable_api_key(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    user.api_enable = False
    db.commit()
    return {"message": "API key disabled"}


@app.post("/api/key/enable")
def enable_api_key(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    user.api_enable = True
    db.commit()
    return {"message": "API key enabled"}


@app.get("/api/logs")
def get_logs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logs = db.query(APILog).filter(APILog.user_id == user.id).all()
    return [
        {
            "order_id": l.order_id,
            "risk_score": l.risk_score,
            "decision": l.decision,
            "time": l.created_at,
        }
        for l in logs
    ]


@app.get("/api/admin/stats")
def admin_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    total_users = db.query(User).count()
    total_predictions = sum(u.usage_count for u in db.query(User).all())
    total_payments = db.query(Payment).count()
    total_revenue = sum(p.amount for p in db.query(Payment).all())

    return {
        "total_users": total_users,
        "total_predictions": total_predictions,
        "total_payments": total_payments,
        "total_revenue": total_revenue,
    }


@app.get("/api/admin/users")
def get_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    users = db.query(User).all()

    return [
        {
            "id": u.id,
            "email": u.email,
            "plan": u.plan,
            "usage": u.usage_count,
            "created": u.id,  # or created_at if exists
        }
        for u in users
    ]


@app.get("/api/admin/leads")
def get_leads(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(status_code=403)

    leads = db.query(EarlyAccess).all()

    return [
        {
            "name": l.full_name,
            "email": l.email,
            "brand": l.brand_name,
            "orders": l.monthly_orders,  # ✅ FIXED
        }
        for l in leads
    ]


@app.get("/api/admin/export-leads")
def export_leads(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(status_code=403)

    leads = db.query(EarlyAccess).all()

    data = [
        {
            "Name": l.full_name,
            "Email": l.email,
            "Brand": l.brand_name,
            "Orders": l.monthly_orders,
            "Phone": l.phone,
        }
        for l in leads
    ]

    df = pd.DataFrame(data)

    file_path = "leads.xlsx"
    df.to_excel(file_path, index=False)

    return FileResponse(file_path, filename="leads.xlsx")


@app.get("/api/stats")
def get_user_stats(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from sqlalchemy import func

    totals = (
        db.query(
            func.sum(Prediction.risky_orders),
            func.sum(Prediction.verify_orders),
            func.sum(Prediction.safe_orders),
            func.sum(Prediction.potential_savings),
        )
        .filter(Prediction.user_id == user.id)
        .first()
    )

    return {
        "total_predictions": user.usage_count,
        "risky_orders": int(totals[0] or 0),
        "verify_orders": int(totals[1] or 0),
        "safe_orders": int(totals[2] or 0),
        "plan": user.plan,
        "expiry": user.subscription_end,
    }


@app.get("/api/history")
def get_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    logs = (
        db.query(APILog)
        .filter(APILog.user_id == user.id)
        .order_by(APILog.created_at.desc())
        .all()
    )
    return [
        {
            "order_id": l.order_id,
            "risk_score": l.risk_score,
            "decision": l.decision,
            "time": l.created_at,
        }
        for l in logs
    ]


@app.get("/api/prediction-history")
def prediction_history(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    history = (
        db.query(Prediction)
        .filter(Prediction.user_id == user.id)
        .order_by(Prediction.created_at.desc())
        .all()
    )
    return [
        {
            "created_at": p.created_at,
            "total_orders": p.total_orders,
            "risky_orders": p.risky_orders,
            "verify_orders": p.verify_orders,
            "safe_orders": p.safe_orders,
            "potential_savings": p.potential_savings,
            "file_id": p.file_id,
        }
        for p in history
    ]


@app.get("/admin/analytics")
def admin_required(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return current_user


def admin_analytics(
    current_user: User = Depends(admin_required), db: Session = Depends(get_db)
):

    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")
    # Total users
    total_users = db.query(User).count()

    # Total predictions
    total_predictions = db.query(PredictionLog).count()

    # Total savings (optional: simple logic)
    total_savings = db.query(Prediction).count() * 200  # dummy calc

    # Today predictions
    today = datetime.utcnow().date()
    today_predictions = (
        db.query(Prediction).filter(Prediction.created_at >= today).count()
    )

    # Weekly predictions
    last_week = datetime.utcnow() - timedelta(days=7)
    weekly_predictions = (
        db.query(Prediction).filter(Prediction.created_at >= last_week).count()
    )

    # Payments
    paid_users = db.query(Payment).filter(Payment.status == "paid").count()
    pending_payments = db.query(Payment).filter(Payment.status == "pending").count()

    return {
        "total_users": total_users,
        "total_predictions": total_predictions,
        "total_savings": total_savings,
        "today_predictions": today_predictions,
        "weekly_predictions": weekly_predictions,
        "paid_users": paid_users,
        "pending_payments": pending_payments,
    }


@app.get("/status/{job_id}")
def check_status(job_id: str):
    return {
        "status": (
            "completed" if os.path.exists(f"output_{job_id}.csv") else "processing"
        )
    }


class EarlyAccessRequest(BaseModel):
    full_name: str
    email: str
    brand_name: str
    order_volume: str


@app.post("/early-access")
async def early_access(data: EarlyAccessRequest):
    try:
        import resend

        resend.api_key = os.getenv("RESEND_API_KEY")
        resend.Emails.send(
            {
                "from": os.getenv("MAIL_FROM", "onboarding@resend.dev"),
                "to": os.getenv("MAIL_FROM"),
                "subject": f"🚀 New Early Access Request — {data.brand_name}",
                "html": f"""<h2>New Early Access Request</h2>
            <p><b>Name:</b> {data.full_name}</p>
            <p><b>Email:</b> {data.email}</p>
            <p><b>Brand:</b> {data.brand_name}</p>
            <p><b>Volume:</b> {data.order_volume}</p>""",
            }
        )
        return {
            "message": "Application received! We'll be in touch within 24-48 hours."
        }
    except Exception as e:
        print("EARLY ACCESS ERROR:", e)
        return {"error": str(e)}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@app.post("/change-password")
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not verify_password(data.current_password, user.password):
        return {"error": "Current password is incorrect"}
    user.password = hash_password(data.new_password)
    db.commit()
    return {"message": "Password changed successfully"}


@app.post("/api/purchase")
def purchase_api(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.api_purchased:
        return {"error": "You already have API access"}

    # ✅ Generate API key only when purchased
    user.api_key = str(uuid.uuid4())
    user.api_purchased = True
    user.api_enable = True
    db.commit()

    return {"message": "API access activated successfully!", "api_key": user.api_key}


@app.post("/payment/confirm")
def confirm_payment(data: dict, db: Session = Depends(get_db)):
    user_id = data.get("user_id")
    user = db.query(User).filter(User.id == user_id).first()

    #
    user.api_purchased = True
    user.api_key = str(uuid.uuid4())
    user.api_enable = True
    user.plan = "pro"
    db.commit()

    return {"message": "API access activated"}


@app.get("/api/admin/payments")
def get_payments(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied")

    payments = db.query(Payment).all()

    return [
        {
            "user_id": p.user_id,
            "amount": p.amount,
            "payment_id": p.razorpay_payment_id,
            "date": p.created_at,
        }
        for p in payments
    ]


@app.get("/admin/data")
def admin_data(admin: User = Depends(get_admin_user)):
    return {"message": "Admin only data"}


@app.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "plan": user.plan,
    }


@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))