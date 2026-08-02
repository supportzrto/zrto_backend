import httpx
import os
from dotenv import load_dotenv

load_dotenv()

BREVO_API_KEY = os.getenv("BREVO_API_KEY")
MAIL_FROM = os.getenv("MAIL_FROM", "zrtosupport@gmail.com")
BACKEND_URL = os.getenv("BACKEND_URL", "https://api-zrto.up.railway.app")

async def send_email(to: str, subject: str, html: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.brevo.com/v3/smtp/email",
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json"
            },
            json={
                "sender": {"name": "ZRTO", "email": MAIL_FROM},
                "to": [{"email": to}],
                "subject": subject,
                "htmlContent": html
            }
        )
        if response.status_code not in [200, 201]:
            raise Exception(f"Brevo error: {response.text}")

async def send_verification_email(email: str, token: str):
    verification_link = f"{BACKEND_URL}/verify-email/{token}"
    await send_email(
        to=email,
        subject="Verify your ZRTO Account",
        html=f"""
        <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto; padding: 40px; background: white; border-radius: 12px;">
            <h2 style="color: #6366f1;">Welcome to ZRTO! 🚀</h2>
            <p>Click the button below to verify your account:</p>
            <a href="{verification_link}" style="background:#6366f1;color:white;padding:12px 28px;text-decoration:none;border-radius:6px;display:inline-block;margin:16px 0;font-weight:bold;">
                Verify My Account
            </a>
            <p style="color:#888;font-size:13px;">Or copy: {verification_link}</p>
            <p style="color:#aaa;font-size:12px;">Expires in 24 hours.</p>
        </div>
        """
    )

async def send_otp_email(email: str, otp: str):
    await send_email(
        to=email,
        subject="Your ZRTO OTP Code",
        html=f"""
        <div style="font-family: Arial, sans-serif; max-width: 480px; margin: auto; padding: 40px; background: white; border-radius: 12px;">
            <h2 style="color: #6366f1;">Password Reset OTP</h2>
            <p>Use this code to reset your password:</p>
            <h1 style="letter-spacing:10px;color:#6366f1;font-size:40px;text-align:center;">{otp}</h1>
            <p style="color:#888;font-size:13px;text-align:center;">Expires in 5 minutes.</p>
        </div>
        """
    )

# Keep conf as None for backward compatibility
conf = None
