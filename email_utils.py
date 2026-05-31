import resend
import os
from dotenv import load_dotenv

load_dotenv()

resend.api_key = os.getenv("RESEND_API_KEY")

BACKEND_URL = os.getenv("BACKEND_URL", "https://zrtobackend-production.up.railway.app")
MAIL_FROM = os.getenv("MAIL_FROM", "onboarding@resend.dev")


async def send_verification_email(email: str, token: str):
    verification_link = f"{BACKEND_URL}/verify-email/{token}"

    resend.Emails.send({
        "from": MAIL_FROM,
        "to": email,
        "subject": "Verify your ZRTO Account",
        "html": f"""
        <html>
        <body style="font-family: Arial, sans-serif; background: #f5f5f5; padding: 40px;">
            <div style="max-width: 480px; margin: auto; background: white; border-radius: 12px; padding: 40px; box-shadow: 0 2px 12px rgba(0,0,0,0.1);">
                <h2 style="color: #6366f1;">Welcome to ZRTO! 🚀</h2>
                <p style="color: #555;">Click the button below to verify your account:</p>
                <a href="{verification_link}" style="
                    background-color: #6366f1;
                    color: white;
                    padding: 12px 28px;
                    text-decoration: none;
                    border-radius: 6px;
                    display: inline-block;
                    margin: 16px 0;
                    font-weight: bold;
                ">Verify My Account</a>
                <p style="color: #888; font-size: 13px;">Or copy this link:<br>{verification_link}</p>
                <p style="color: #aaa; font-size: 12px;">This link expires in 24 hours.</p>
            </div>
        </body>
        </html>
        """
    })


async def send_otp_email(email: str, otp: str):
    resend.Emails.send({
        "from": MAIL_FROM,
        "to": email,
        "subject": "Your ZRTO OTP Code",
        "html": f"""
        <html>
        <body style="font-family: Arial, sans-serif; background: #f5f5f5; padding: 40px;">
            <div style="max-width: 480px; margin: auto; background: white; border-radius: 12px; padding: 40px; box-shadow: 0 2px 12px rgba(0,0,0,0.1);">
                <h2 style="color: #6366f1;">Password Reset OTP</h2>
                <p style="color: #555;">Use the code below to reset your password:</p>
                <h1 style="letter-spacing: 10px; color: #6366f1; font-size: 40px; text-align: center;">{otp}</h1>
                <p style="color: #888; font-size: 13px; text-align: center;">Expires in 5 minutes.</p>
                <p style="color: #aaa; font-size: 12px;">If you didn't request this, ignore this email.</p>
            </div>
        </body>
        </html>
        """
    })


# Keep conf as None — main.py imports it but only uses it in /early-access
# which we'll also update to use resend
conf = None