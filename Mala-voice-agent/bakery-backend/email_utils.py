import requests
import logging
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Force load .env.local from the same directory as this file
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / ".env.local"
load_dotenv(dotenv_path=env_path)

# n8n Email webhook URL - PRODUCTION URL (not webhook-test)
N8N_EMAIL_WEBHOOK = "https://mala-mala.app.n8n.cloud/webhook/Email"


def send_order_confirmation(to_email, customer_name, items, total_price):
    """Send order confirmation email via n8n webhook"""

    payload = {
        "to_email": to_email,
        "customer_name": customer_name,
        "items": items,
        "total_price": total_price,
        "subject": "🧁 Your Crincle Cupkakes Order is Confirmed!",
        "body": f"""Hi {customer_name},

Thank you for ordering from Crincle Cupkakes! 🎉

🧁 Order Details:
Items: {items}
Total: Rs {total_price}

Your cupcakes are freshly baked and will be delivered soon.

If you have allergies or questions, reply to this email anytime.

Sweet regards,
Crincle Cupkakes 🍰
"""
    }

    try:
        logger.info(f"📤 Sending confirmation email to {to_email}...")
        response = requests.post(
            N8N_EMAIL_WEBHOOK,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Confirmation email sent to {to_email}")
        else:
            logger.warning(f"⚠️ Email webhook returned status: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"❌ Failed to send email to {to_email}: {e}")