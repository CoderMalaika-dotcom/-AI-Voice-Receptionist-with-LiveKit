import requests

# Test payload
payload = {
    "to_email": "test@example.com",
    "customer_name": "Test User",
    "items": "Red Velvet Cupcakes x6",
    "total_price": 1800
}

# Test Database webhook
print("Testing Database webhook...")
try:
    response = requests.post(
        "https://mala-mala.app.n8n.cloud/webhook/Database",
        json=payload,
        timeout=10
    )
    print(f"Database webhook status: {response.status_code}")
    print(f"Response: {response.text}\n")
except Exception as e:
    print(f"Database webhook error: {e}\n")

# Test Email webhook
print("Testing Email webhook...")
try:
    response = requests.post(
        "https://mala-mala.app.n8n.cloud/webhook/Email",
        json=payload,
        timeout=10
    )
    print(f"Email webhook status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Email webhook error: {e}")