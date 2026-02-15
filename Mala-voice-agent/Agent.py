from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import AgentServer, AgentSession, Agent, room_io, WorkerOptions
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
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv(".env.local")

# Get backend URL from environment variable
BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")

logger.info(f"🔧 Backend URL configured: {BACKEND_URL}")


def send_order_to_backend(order_data):
    """Send order to backend API"""
    logger.info(f"\n{'='*60}")
    logger.info(f"📦 SENDING ORDER TO BACKEND")
    logger.info(f"{'='*60}")
    logger.info(f"Customer: {order_data.get('customer_name')}")
    logger.info(f"Email: {order_data.get('email')}")
    logger.info(f"Items: {order_data.get('items')}")
    logger.info(f"Total: Rs. {order_data.get('total_price')}")
    logger.info(f"Backend URL: {BACKEND_URL}")
    logger.info(f"{'='*60}\n")
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/place-order",
            json=order_data,
            timeout=10,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code == 200:
            logger.info(f"✅ Order saved and email sent!")
            logger.info(f"Response: {response.json()}")
            return True
        else:
            logger.error(f"⚠️ Backend error: {response.status_code}")
            logger.error(f"Response: {response.text}")
            return False
            
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ Cannot connect to backend at {BACKEND_URL}")
        logger.error("Make sure your backend is deployed and the BACKEND_URL is correct")
        return False
        
    except requests.exceptions.Timeout:
        logger.error(f"❌ Request timeout to {BACKEND_URL}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Error sending order: {str(e)}")
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
    
    logger.info("="*80)
    logger.info(f"🚀 NEW SESSION STARTED")
    logger.info(f"📍 Room: {ctx.room.name}")
    logger.info(f"🔗 Room SID: {ctx.room.sid if hasattr(ctx.room, 'sid') else 'N/A'}")
    logger.info(f"🌐 LiveKit URL: {os.getenv('LIVEKIT_URL')}")
    logger.info("="*80)
    
    # Track room events
    @ctx.room.on("participant_connected")
    def on_participant_connected(participant: rtc.RemoteParticipant):
        logger.info("="*60)
        logger.info(f"👤 PARTICIPANT CONNECTED")
        logger.info(f"Identity: {participant.identity}")
        logger.info(f"Kind: {participant.kind}")
        logger.info(f"SID: {participant.sid}")
        logger.info("="*60)

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant: rtc.RemoteParticipant):
        logger.info(f"👋 Participant disconnected: {participant.identity}")

    @ctx.room.on("track_subscribed")
    def on_track_subscribed(track: rtc.Track, publication: rtc.TrackPublication, participant: rtc.RemoteParticipant):
        logger.info(f"🎵 Track subscribed: {track.kind} from {participant.identity}")

    try:
        logger.info("🔧 Creating session with Groq + Deepgram...")
        
        session = AgentSession(
            llm=groq.LLM(model="llama-3.3-70b-versatile"),
            tts=deepgram.TTS(model="aura-luna-en"),
            stt=deepgram.STT()
        )

        bakery_agent = BakeryAssistant()

        # Monitor agent responses for order confirmation
        @session.on("agent_speech")
        def on_agent_speech(text: str):
            """Monitor agent speech for order confirmation pattern"""
            logger.info(f"🗣️ Agent said: {text[:150]}...")
            
            if "ORDER_CONFIRMED:" in text:
                logger.info("✅ ORDER CONFIRMATION DETECTED!")
                try:
                    confirmation_text = text.split("ORDER_CONFIRMED:")[1].split("\n")[0]
                    parts = [p.strip() for p in confirmation_text.split("|")]
                    
                    if len(parts) >= 4:
                        order_data = {
                            "customer_name": parts[0],
                            "email": parts[1],
                            "items": parts[2],
                            "total_price": int(re.sub(r'[^\d]', '', parts[3]))
                        }
                        logger.info(f"📋 Parsed order data: {order_data}")
                        send_order_to_backend(order_data)
                    else:
                        logger.error(f"❌ Invalid order format. Expected 4 parts, got {len(parts)}")
                        
                except Exception as e:
                    logger.error(f"❌ Error parsing order: {e}")

        logger.info("🎬 Starting session...")
        
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

        logger.info("✅ Session started successfully!")

        # Wait a bit before greeting
        await asyncio.sleep(1)

        logger.info("👋 Sending initial greeting...")
        
        # Initial greeting
        await session.generate_reply(
            instructions="""You're answering a call at Crincle Cupkakes bakery.

Keep it VERY SHORT and warm.

Say: "Hi! Thanks for calling Crincle Cupkakes. What can I get for you today?"

Then STOP and listen."""
        )
        
        logger.info("✅ Initial greeting sent!")
        
    except Exception as e:
        logger.error("="*60)
        logger.error(f"❌ ERROR IN SESSION")
        logger.error(f"Error: {e}")
        logger.error("="*60)
        import traceback
        logger.error(traceback.format_exc())
        raise


if __name__ == "__main__":
    logger.info("\n" + "="*80)
    logger.info("🎬 STARTING CRINCLE CUPKAKES AI AGENT")
    logger.info("="*80)
    logger.info(f"📍 Backend URL: {BACKEND_URL}")
    logger.info(f"🔑 LiveKit URL: {os.getenv('LIVEKIT_URL', 'NOT SET')}")
    logger.info(f"🔑 API Key: {'SET ✅' if os.getenv('LIVEKIT_API_KEY') else 'NOT SET ❌'}")
    logger.info(f"🔑 API Secret: {'SET ✅' if os.getenv('LIVEKIT_API_SECRET') else 'NOT SET ❌'}")
    logger.info("="*80 + "\n")
    
    agents.cli.run_app(server)
