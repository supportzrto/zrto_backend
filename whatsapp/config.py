import os

WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "YOUR_PHONE_NUMBER_ID")
WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "YOUR_ACCESS_TOKEN")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "YOUR_VERIFY_TOKEN")
# Meta App Secret (from App Dashboard > Settings > Basic). Used to validate the
# X-Hub-Signature-256 header on incoming webhooks so forged requests are rejected.
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "YOUR_WEBHOOK_URL")

GRAPH_API_VERSION = os.getenv("WHATSAPP_GRAPH_API_VERSION", "v21.0")
GRAPH_API_BASE = os.getenv("WHATSAPP_GRAPH_API_BASE", "https://graph.facebook.com")

# Template used for the first outbound verification message.
INITIAL_TEMPLATE_NAME = os.getenv("WHATSAPP_INITIAL_TEMPLATE_NAME", "zrto_order_verification")
# Template used for the follow-up reminder. Business-initiated WhatsApp messages sent
# outside a customer-initiated 24h session MUST use an approved template (free-form
# interactive messages are only allowed as a reply within that 24h window), so the
# reminder needs its own approved template with Confirm/Cancel quick-reply buttons.
# If this template hasn't been created/approved in Meta Business Manager yet, we fall
# back to the initial template so reminders keep working without extra setup.
REMINDER_TEMPLATE_NAME = os.getenv("WHATSAPP_REMINDER_TEMPLATE_NAME", "zrto_order_reminder")

RISK_LOW_MAX = int(os.getenv("RISK_LOW_MAX", "40"))
RISK_MEDIUM_MAX = int(os.getenv("RISK_MEDIUM_MAX", "70"))
# Matches predict.py's decision() logic: HIGH risk is auto-blocked/converted to
# prepaid (no point asking), LOW is auto-allowed. Only MEDIUM ("VERIFY" decision,
# "Call / WhatsApp" action) is the ambiguous band worth a WhatsApp confirmation.
VERIFY_CATEGORIES = {"MEDIUM"}

DEFAULT_REMINDER_DELAY_HOURS = int(os.getenv("REMINDER_DELAY_HOURS", "2"))
NO_RESPONSE_GRACE_HOURS = int(os.getenv("NO_RESPONSE_GRACE_HOURS", "2"))
SCHEDULER_INTERVAL_SECONDS = int(os.getenv("WA_SCHEDULER_INTERVAL_SECONDS", "3600"))

HTTP_TIMEOUT_SECONDS = int(os.getenv("WA_HTTP_TIMEOUT_SECONDS", "15"))
HTTP_MAX_RETRIES = int(os.getenv("WA_HTTP_MAX_RETRIES", "3"))
HTTP_RETRY_BACKOFF_SECONDS = float(os.getenv("WA_HTTP_RETRY_BACKOFF_SECONDS", "1.5"))

class VerificationStatus:
    PENDING = "Pending"
    VERIFIED = "Verified"
    REJECTED = "Rejected"
    NO_RESPONSE = "No Response"

class OrderStatus:
    AWAITING = "Awaiting Confirmation"
    CONFIRMED = "Confirmed By Customer"
    CANCELLED = "Cancelled By Customer"
    NO_RESPONSE = "No Response"
    ON_HOLD = "On Hold"
    MANUAL_REVIEW = "Manual Review Required"
    SHIPPED = "Shipped"

class MessageType:
    INITIAL = "Initial Verification"
    REMINDER = "Reminder"

class RiskCategory:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

DEFAULT_INITIAL_TEMPLATE = (
    "Hi {customer_name} 👋\n\n"
    "Before shipping your order, please confirm whether you still want to receive it.\n\n"
    "Order ID: {order_id}\nAmount: ₹{order_amount}\n\nChoose an option below:"
)

DEFAULT_REMINDER_TEMPLATE = (
    "Reminder 🔔\n\nHi {customer_name}\n\nWe haven't received your confirmation yet.\n"
    "Please confirm your order.\n\nOrder ID: {order_id}\nAmount: ₹{order_amount}"
)

BTN_CONFIRM_ID = "ZRTO_CONFIRM_ORDER"
BTN_CANCEL_ID = "ZRTO_CANCEL_ORDER"
BTN_CONFIRM_TITLE = "✅ Confirm Order"
BTN_CANCEL_TITLE = "❌ Cancel Order"