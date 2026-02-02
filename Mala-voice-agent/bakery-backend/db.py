import sqlite3
import requests
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# n8n Database webhook URL - PRODUCTION URL (not webhook-test)
N8N_DATABASE_WEBHOOK = "https://mala-mala.app.n8n.cloud/webhook/DataBase"

conn = sqlite3.connect("orders.db", check_same_thread=False)
cursor = conn.cursor()

def parse_items(items_text):
    """
    Example input: 'Chocolate Crinkle Cupcakes x6'
    """
    match = re.search(r"(.*)\s+x(\d+)", items_text)
    if match:
        product_name = match.group(1).strip()
        amount = int(match.group(2))
    else:
        product_name = items_text
        amount = 1
    return product_name, amount


def save_order(customer_name, email, items, total_price):
    """Save order to local SQLite database and send to Baserow via n8n"""
    
    # Save to local database
    cursor.execute("""
    INSERT INTO orders (customer_name, email, items, total_price)
    VALUES (?, ?, ?, ?)
    """, (customer_name, email, items, total_price))
    conn.commit()

    order_id = cursor.lastrowid
    logger.info(f"✅ Order #{order_id} saved to local SQLite database")

    # Parse items
    product_name, amount = parse_items(items)

    # Prepare payload for Baserow
    payload = {
        "orderid": order_id,
        "name": customer_name,
        "email": email,
        "product_name": product_name,
        "amount": amount,
        "price": total_price
    }

    # Send to Baserow via n8n webhook
    try:
        logger.info(f"📤 Sending order #{order_id} to Baserow webhook...")
        response = requests.post(
            N8N_DATABASE_WEBHOOK,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Order #{order_id} sent to Baserow via n8n")
        else:
            logger.warning(f"⚠️ Baserow webhook returned status: {response.status_code} - {response.text}")
            
    except Exception as e:
        logger.error(f"❌ Failed to send order #{order_id} to Baserow: {e}")