import time
import uuid
import requests
from whatsapp import config

_PLACEHOLDERS = {
    "YOUR_PHONE_NUMBER_ID",
    "YOUR_ACCESS_TOKEN",
    "YOUR_VERIFY_TOKEN",
    "YOUR_WEBHOOK_URL",
    "",
    None,
}


class WhatsAppAPIError(Exception):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def send_interactive_message(
    *, phone_number_id: str, access_token: str, to: str, body_text: str
) -> dict:
    if phone_number_id in _PLACEHOLDERS or access_token in _PLACEHOLDERS:
        return {
            "_simulated": True,
            "messaging_product": "whatsapp",
            "contacts": [{"input": to, "wa_id": to}],
            "messages": [{"id": "wamid.SIMULATED_" + uuid.uuid4().hex[:24]}],
        }

    url = (
        f"{config.GRAPH_API_BASE}/{config.GRAPH_API_VERSION}/{phone_number_id}/messages"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": "ZRTO backend test"},
    }
    # payload = {
    #     "messaging_product": "whatsapp", "recipient_type": "individual", "to": to,
    #     "type": "interactive",
    #     "interactive": {
    #         "type": "button", "body": {"text": body_text},
    #         "action": {
    #             "buttons": [
    #                 {"type": "reply", "reply": {"id": config.BTN_CONFIRM_ID, "title": config.BTN_CONFIRM_TITLE}},
    #                 {"type": "reply", "reply": {"id": config.BTN_CANCEL_ID, "title": config.BTN_CANCEL_TITLE}}
    #             ]
    #         }
    #     }
    # }

    last_exc = None
    for attempt in range(1, config.HTTP_MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url, json=payload, headers=headers, timeout=config.HTTP_TIMEOUT_SECONDS
            )
            if resp.status_code in (200, 201):
                return resp.json()
            if 400 <= resp.status_code < 500:
                raise WhatsAppAPIError(
                    f"Client error {resp.status_code}", resp.status_code, resp.text
                )
            last_exc = WhatsAppAPIError(
                f"Server error {resp.status_code}", resp.status_code, resp.text
            )
        except requests.RequestException as exc:
            last_exc = WhatsAppAPIError(f"Network error: {exc}")
        if attempt < config.HTTP_MAX_RETRIES:
            time.sleep(config.HTTP_RETRY_BACKOFF_SECONDS * attempt)

    raise last_exc or WhatsAppAPIError("Request failed")
