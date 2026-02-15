from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import AgentServer, AgentSession, Agent, room_io
from livekit.plugins import (
    noise_cancellation,
    groq,
    deepgram,
    silero
)
import os
import requests
from datetime import datetime
import json
import re

load_dotenv(".env.local")


def send_order_to_backend(order_data):
    """Send order to backend API"""
    print(f"\n{'='*60}")
    print(f"📦 SENDING ORDER TO BACKEND")
    print(f"{'='*60}")
    print(f"Customer: {order_data.get('customer_name')}")
    print(f"Email: {order_data.get('email')}")
    print(f"Items: {order_data.get('items')}")
    print(f"Total: Rs. {order_data.get('total_price')}")
    print(f"{'='*60}\n")
    
    try:
        response = requests.post(
            "http://127.0.0.1:8000/place-order",
            json=order_data,
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Order saved and email sent!")
            return True
        else:
            print(f"⚠️ Backend error: {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to backend. Make sure it's running:")
        print("   uvicorn main:app --reload")
        return False
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return False


class BakeryAssistant(Agent):
    def __init__(self) -> None:
        self.current_order = {
            'customer_name': None,
            'email': None,
            'items': None,
            'total_price': None
        }
        
        instructions = """You are a friendly, professional AI assistant for Crincle Cupkakes bakery.

CRITICAL RULES - READ CAREFULLY:
- Ask ONE question at a time, then STOP
- Keep responses SHORT (2-3 sentences max)
- Let the customer talk MORE than you
- Never ramble or assume
- Sound warm and human, not robotic

MANDATORY ORDER FLOW (FOLLOW THIS EXACTLY):
You MUST collect ALL of this information in order:

1. Ask what they want to order
2. Ask quantity/size
3. Ask: "Can I get your name for the order?"
4. Ask: "And your email address for the confirmation?" (REQUIRED)
5. Ask: "Would you like delivery or pickup?"
6. If delivery: Ask "What's the delivery address?"
7. Ask: "When would you like this?"
8. Calculate total and say: "Your total is Rs. [amount]. Does everything sound correct?"
9. When customer confirms, say EXACTLY: "ORDER_CONFIRMED: [Name] | [Email] | [Items] | [Total]"
10. Then say: "Perfect! You'll receive a confirmation email at [email] shortly. Thanks for choosing Crincle Cupkakes!"

EXAMPLE of step 9:
"ORDER_CONFIRMED: Sarah Khan | sarah@email.com | 6 Belgian Chocolate Fudge Cupcakes | 1500"

IMPORTANT: You MUST use the exact format "ORDER_CONFIRMED:" followed by the pipe-separated details.

BAKERY INFORMATION:

Shop Name: Crincle Cupkakes

MENU (Know this well):

CUPCAKES (Most Popular):
- Classic Vanilla Swirl - Rs. 250 each
- Belgian Chocolate Fudge - Rs. 300 each
- Red Velvet Cream Cheese - Rs. 280 each
- Nutella Lava Cupcake - Rs. 350 each
- Lemon Zest - Rs. 240 each
- Salted Caramel Delight - Rs. 320 each

Box of 6 cupcakes: Rs. 1500
Box of 12 cupcakes: Rs. 2800

SIGNATURE CAKES:
- Chocolate Truffle Cake - Rs. 2500 (1 pound), Rs. 4500 (2 pounds)
- Vanilla Strawberry Cream Cake - Rs. 2800 (1 pound), Rs. 5000 (2 pounds)
- Red Velvet Cake - Rs. 3000 (1 pound), Rs. 5500 (2 pounds)
- Ferrero Rocher Cake - Rs. 3500 (1 pound), Rs. 6500 (2 pounds)
- Lotus Biscoff Cake - Rs. 3200 (1 pound), Rs. 6000 (2 pounds)

OTHER DESSERTS:
- Brownies (Walnut/Fudge/Lotus) - Rs. 150 each, Box of 6: Rs. 800
- Chocolate Chip Cookies - Rs. 100 each, Box of 12: Rs. 1000
- Dessert Boxes (assorted) - Rs. 2000

Operating Hours: Mon-Sat: 10 AM – 10 PM | Sun: 12 PM – 9 PM
Delivery: Same-day (orders before 6 PM), 60-90 minutes

ALLERGIES: Contains dairy, eggs, wheat. Some items have nuts.

IMPORTANT:
- DO NOT use asterisks or actions
- ALWAYS get name and email
- Use the ORDER_CONFIRMED format exactly as shown
- Sound like a real friendly bakery staff member"""

        super().__init__(instructions=instructions)


server = AgentServer()


@server.rtc_session()
async def my_agent(ctx: agents.JobContext):
    
    session = AgentSession(
        llm=groq.LLM(model="llama-3.3-70b-versatile"),
        tts=deepgram.TTS(model="aura-luna-en"),
        stt=deepgram.STT()
    )

    bakery_agent = BakeryAssistant()

    # Listen for agent responses to detect order confirmation
    @session.on("agent_speech")
    def on_agent_speech(text: str):
        """Monitor agent speech for order confirmation pattern"""
        if "ORDER_CONFIRMED:" in text:
            # Parse the order details
            try:
                parts = text.split("ORDER_CONFIRMED:")[1].split("|")
                if len(parts) >= 4:
                    order_data = {
                        "customer_name": parts[0].strip(),
                        "email": parts[1].strip(),
                        "items": parts[2].strip(),
                        "total_price": int(parts[3].strip())
                    }
                    send_order_to_backend(order_data)
            except Exception as e:
                print(f"❌ Error parsing order: {e}")

    await session.start(
        room=ctx.room,
        agent=bakery_agent,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=lambda params:
                    noise_cancellation.BVCTelephony()
                    if params.participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
                    else noise_cancellation.BVC(),
            ),
        ),
    )

    # Initial greeting
    await session.generate_reply(
        instructions="""You're answering a call at Crincle Cupkakes bakery.

Keep it VERY SHORT and warm.

Say: "Hi! Thanks for calling Crincle Cupkakes. What can I get for you today?"

Then STOP and listen."""
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
