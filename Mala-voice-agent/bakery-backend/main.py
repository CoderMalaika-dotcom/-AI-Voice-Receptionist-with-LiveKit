from fastapi import FastAPI
from pydantic import BaseModel
from db import save_order
from email_utils import send_order_confirmation
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()


class Order(BaseModel):
    customer_name: str
    email: str
    items: str
    total_price: int


@app.post("/place-order")
def place_order(order: Order):
    logger.info(f"📥 Received order from: {order.customer_name}")
    
    # 1. Save to local SQLite database + send to Baserow via n8n
    save_order(
        order.customer_name,
        order.email,
        order.items,
        order.total_price
    )
    
    # 2. Send confirmation email via n8n
    send_order_confirmation(
        order.email,
        order.customer_name,
        order.items,
        order.total_price
    )

    return {"status": "Order placed successfully"}