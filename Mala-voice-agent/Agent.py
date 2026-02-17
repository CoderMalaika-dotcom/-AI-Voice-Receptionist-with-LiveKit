from dotenv import load_dotenv
from livekit import agents
from livekit.agents import AgentServer, AgentSession, Agent, room_io, RoomInputOptions, BackgroundAudioPlayer, AudioConfig, BuiltinAudioClip
from livekit.plugins import (
    noise_cancellation,
    openai,
    deepgram,
    bey,
)
import os
import requests
import re
import logging
from datetime import datetime
from typing import Dict, List, Optional
import json
import asyncio

from tools import send_email  # LiveKit @function_tool — given to the LLM
from prompt import (
    AGENT_INSTRUCTIONS,
    GREETING_INSTRUCTIONS,
    HOT_TRANSFER_INSTRUCTIONS,
    COLD_TRANSFER_INSTRUCTIONS,
    HOLD_START_INSTRUCTIONS,
    HOLD_END_INSTRUCTIONS,
)

# =========================
# Logging Configuration
# =========================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("CrincleCupkakes")

load_dotenv(".env.local")

BACKEND_URL = os.getenv("BACKEND_URL")
TRANSFER_PHONE = os.getenv("TRANSFER_PHONE", "+1234567890")

# =========================
# FAQ Knowledge Base
# =========================
FAQ_KNOWLEDGE = {
    "hours": {
        "keywords": ["hours", "open", "close", "timing", "time", "when open"],
        "answer": "We're open Monday to Saturday, 8 AM to 8 PM, and Sunday 10 AM to 6 PM."
    },
    "location": {
        "keywords": ["location", "address", "where", "directions", "find you"],
        "answer": "We're located at 123 Main Street, Karachi. We're right next to the National Bank on Shahrah-e-Faisal."
    },
    "delivery": {
        "keywords": ["delivery", "deliver", "shipping", "courier"],
        "answer": "Yes! We deliver within Karachi. Delivery is Rs. 200 for orders under Rs. 2000, and free for orders above that. It takes 45-60 minutes."
    },
    "payment": {
        "keywords": ["payment", "pay", "cash", "card", "online"],
        "answer": "We accept cash, all major cards, and online payment through JazzCash, Easypaisa, and bank transfer."
    },
    "custom_orders": {
        "keywords": ["custom", "personalized", "special", "design", "theme"],
        "answer": "Absolutely! We do custom cakes and cupcakes. Just give us 24 hours notice for custom designs. Prices start from Rs. 1500."
    },
    "ingredients": {
        "keywords": ["ingredients", "allergen", "gluten", "dairy", "vegan", "halal"],
        "answer": "All our products are 100% halal. We can do gluten-free and dairy-free options with 24 hours notice. Please let us know about any allergies!"
    },
    "prices": {
        "keywords": ["price", "cost", "how much", "expensive"],
        "answer": "Our regular cupcakes are Rs. 150 each, premium ones Rs. 250. Cakes start from Rs. 1200 for 1 pound. Want me to check something specific?"
    },
    "cancellation": {
        "keywords": ["cancel", "refund", "change order"],
        "answer": "You can cancel or modify orders up to 6 hours before delivery. Full refund for cancellations before that. After that, we can try our best but charges may apply."
    },
    "bulk_orders": {
        "keywords": ["bulk", "party", "event", "wedding", "corporate", "large order"],
        "answer": "We love bulk orders! For events, we offer 10% off on orders above 50 cupcakes. Please give us 48 hours notice for large quantities."
    },
    "flavors": {
        "keywords": ["flavor", "flavours", "variety", "what kind", "types"],
        "answer": "We have chocolate, vanilla, red velvet, lemon, strawberry, cookies & cream, and our special Pakistani chai cupcakes! We also have seasonal flavors."
    }
}

# =========================
# Call Analytics Tracker
# =========================
class CallAnalytics:
    def __init__(self):
        self.start_time = datetime.now()
        self.end_time = None
        self.transcript: List[Dict] = []
        self.customer_data: Dict = {}
        self.intent = "unknown"
        self.sentiment = "neutral"
        self.questions_asked: List[str] = []
        self.faq_triggered: List[str] = []
        self.hold_count = 0
        self.interruption_count = 0
        self.transfer_requested = False
        self.order_placed = False

    def add_transcript(self, speaker: str, text: str):
        self.transcript.append({
            "timestamp": datetime.now().isoformat(),
            "speaker": speaker,
            "text": text
        })

    def detect_intent(self):
        transcript_text = " ".join([t["text"].lower() for t in self.transcript if t["speaker"] == "customer"])
        if any(word in transcript_text for word in ["order", "buy", "purchase", "want"]):
            self.intent = "purchase"
        elif any(word in transcript_text for word in ["complain", "issue", "problem", "wrong"]):
            self.intent = "complaint"
        elif any(word in transcript_text for word in ["question", "ask", "wondering", "how", "what", "when"]):
            self.intent = "inquiry"
        elif any(word in transcript_text for word in ["cancel", "refund", "change"]):
            self.intent = "modification"
        else:
            self.intent = "general"

    def generate_summary(self) -> Dict:
        self.end_time = datetime.now()
        duration = (self.end_time - self.start_time).total_seconds()
        self.detect_intent()
        return {
            "call_metadata": {
                "start_time": self.start_time.isoformat(),
                "end_time": self.end_time.isoformat(),
                "duration_seconds": duration,
                "duration_formatted": f"{int(duration // 60)}m {int(duration % 60)}s"
            },
            "customer_data": self.customer_data,
            "call_analysis": {
                "primary_intent": self.intent,
                "sentiment": self.sentiment,
                "order_placed": self.order_placed,
                "transfer_requested": self.transfer_requested,
                "hold_count": self.hold_count,
                "interruption_count": self.interruption_count,
                "faqs_addressed": self.faq_triggered,
                "questions_count": len(self.questions_asked)
            },
            "transcript": self.transcript,
            "lead_quality": self._assess_lead_quality()
        }

    def _assess_lead_quality(self) -> str:
        score = 0
        if self.order_placed:
            return "converted"
        if self.customer_data.get("email"):
            score += 30
        if self.customer_data.get("customer_name"):
            score += 20
        if self.intent == "purchase":
            score += 30
        if len(self.questions_asked) > 2:
            score += 10
        if "custom" in self.faq_triggered:
            score += 10
        if score >= 70:
            return "hot"
        elif score >= 40:
            return "warm"
        else:
            return "cold"


# =========================
# Backend HTTP Helpers
# (Server-side calls — NOT LLM tools)
# =========================
def _post_to_backend(endpoint: str, data: dict, label: str) -> bool:
    """Generic helper to POST data to backend endpoints."""
    try:
        response = requests.post(
            f"{BACKEND_URL}/{endpoint}",
            json=data,
            timeout=10
        )
        if response.status_code == 200:
            logger.info(f"✅ {label} stored successfully")
            return True
        else:
            logger.error(f"❌ {label} failed: {response.text}")
            return False
    except Exception as e:
        logger.error(f"❌ {label} connection failed: {e}")
        return False


def backend_place_order(order_data: dict) -> bool:
    return _post_to_backend("place-order", order_data, "Order")


def backend_call_analytics(analytics_data: dict) -> bool:
    return _post_to_backend("call-analytics", analytics_data, "Analytics")


def backend_store_lead(lead_data: dict) -> bool:
    return _post_to_backend("leads", lead_data, "Lead")


def backend_send_email(email_data: dict) -> bool:
    """
    Sends email notifications via the backend HTTP service.
    Used for internal/system emails (order confirmations, call summaries).
    This is NOT the same as the send_email LLM tool in tools.py.
    """
    return _post_to_backend("send-email", email_data, "Email")


# =========================
# Enhanced Bakery Agent
# =========================
class EnhancedBakeryAssistant(Agent):
    def __init__(self, analytics: CallAnalytics) -> None:
        self.analytics = analytics
        self.on_hold = False
        self.hold_duration = 0
        super().__init__(
            instructions=AGENT_INSTRUCTIONS,  # ← from prompt.py
            tools=[send_email],               # ← from tools.py (LLM can call this)
        )

    async def handle_hold(self, duration: int):
        self.on_hold = True
        self.hold_duration = duration
        self.analytics.hold_count += 1
        logger.info(f"⏸ Holding for {duration} seconds")
        await asyncio.sleep(duration)
        self.on_hold = False
        logger.info("▶️ Resuming from hold")


# =========================
# FAQ Detector
# =========================
def detect_faq(text: str) -> Optional[str]:
    text_lower = text.lower()
    for category, faq in FAQ_KNOWLEDGE.items():
        if any(keyword in text_lower for keyword in faq["keywords"]):
            return faq["answer"]
    return None


# =========================
# LiveKit Server
# =========================
server = AgentServer()


@server.rtc_session()
async def entrypoint(ctx: agents.JobContext):

    logger.info(f"🚀 Session started in room: {ctx.room.name}")

    analytics = CallAnalytics()

    session = AgentSession(
        llm=openai.realtime.RealtimeModel(voice="coral"),
        stt=deepgram.STT(),
        tts=deepgram.TTS(model="aura-luna-en"),
    )

    agent = EnhancedBakeryAssistant(analytics)

    # =========================
    # Avatar Setup (Beyond Presence)
    # =========================
    avatar = bey.AvatarSession(
        avatar_id=os.getenv("BEY_AVATAR_ID"),
    )

    # Start the avatar and wait for it to join the room
    await avatar.start(session, room=ctx.room)
    logger.info("🎭 Avatar joined the room")

    # =========================
    # Handle Customer Speech
    # =========================
    @session.on("user_speech")
    def handle_user_speech(text: str):
        logger.info(f"👤 Customer: {text}")
        analytics.add_transcript("customer", text)
        faq_answer = detect_faq(text)
        if faq_answer:
            logger.info(f"📚 FAQ triggered: {faq_answer}")
            analytics.faq_triggered.append(text[:50])

    # =========================
    # Handle Agent Speech
    # =========================
    @session.on("agent_speech")
    def handle_agent_speech(text: str):
        logger.info(f"🗣 Agent: {text}")
        analytics.add_transcript("agent", text)

        # === ORDER CONFIRMATION ===
        if "ORDER_CONFIRMED:" in text:
            try:
                data = text.split("ORDER_CONFIRMED:")[1].strip()
                parts = [p.strip() for p in data.split("|")]
                if len(parts) == 4:
                    order_data = {
                        "customer_name": parts[0],
                        "email": parts[1],
                        "items": parts[2],
                        "total_price": int(re.sub(r"[^\d]", "", parts[3])),
                        "timestamp": datetime.now().isoformat(),
                        "order_source": "voice_call"
                    }
                    logger.info(f"📦 Order Placed: {order_data}")
                    analytics.customer_data.update({
                        "customer_name": parts[0],
                        "email": parts[1],
                        "order_items": parts[2],
                        "order_value": order_data["total_price"]
                    })
                    analytics.order_placed = True
                    backend_place_order(order_data)
                    backend_send_email({
                        "to": parts[1],
                        "subject": "Order Confirmation - Crincle Cupkakes",
                        "type": "order_confirmation",
                        "data": order_data
                    })
            except Exception as e:
                logger.error(f"❌ Order parsing failed: {e}")

        # === HOT TRANSFER ===
        if "TRANSFER_HOT:" in text:
            reason = text.split("TRANSFER_HOT:")[1].strip()
            logger.warning(f"📞 HOT TRANSFER requested: {reason}")
            analytics.transfer_requested = True
            asyncio.create_task(session.generate_reply(
                instructions=HOT_TRANSFER_INSTRUCTIONS
            ))

        # === COLD TRANSFER ===
        if "TRANSFER_COLD:" in text:
            reason = text.split("TRANSFER_COLD:")[1].strip()
            logger.info(f"📞 COLD TRANSFER requested: {reason}")
            analytics.transfer_requested = True
            asyncio.create_task(session.generate_reply(
                instructions=COLD_TRANSFER_INSTRUCTIONS
            ))

        # === HOLD REQUEST ===
        if "HOLD_REQUEST:" in text:
            try:
                duration = int(re.search(r'\d+', text.split("HOLD_REQUEST:")[1]).group())
                logger.info(f"⏸ Hold requested for {duration} seconds")

                async def handle_hold_sequence():
                    await session.generate_reply(instructions=HOLD_START_INSTRUCTIONS)
                    await agent.handle_hold(duration)
                    await session.generate_reply(instructions=HOLD_END_INSTRUCTIONS)

                asyncio.create_task(handle_hold_sequence())
            except Exception as e:
                logger.error(f"❌ Hold parsing failed: {e}")

    # =========================
    # Interruption Detection
    # =========================
    @session.on("user_started_speaking")
    def on_interruption():
        logger.info("⚡ Customer interrupted")
        analytics.interruption_count += 1

    # =========================
    # Call End Handler
    # =========================
    @session.on("session_ended")
    def on_call_end():
        logger.info("📞 Call ended - Generating analytics...")
        call_summary = analytics.generate_summary()
        backend_call_analytics(call_summary)

        if analytics.customer_data.get("email") or analytics.customer_data.get("customer_name"):
            lead_data = {
                **analytics.customer_data,
                "lead_quality": call_summary["lead_quality"],
                "intent": analytics.intent,
                "source": "voice_call",
                "timestamp": datetime.now().isoformat(),
                "call_duration": call_summary["call_metadata"]["duration_seconds"]
            }
            backend_store_lead(lead_data)

        backend_send_email({
            "to": "team@crinclecupkakes.com",
            "subject": f"Call Summary - {analytics.customer_data.get('customer_name', 'Unknown')}",
            "type": "call_summary",
            "data": call_summary
        })
        logger.info(f"✅ Call Summary: {json.dumps(call_summary, indent=2)}")

    # =========================
    # Start Session
    # =========================
    await session.start(
        room=ctx.room,
        agent=agent,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
            video_enabled=True,   # Required for avatar video stream
        ),
    )

    # =========================
    # Background Audio (typing sounds while agent thinks)
    # =========================
    background_audio = BackgroundAudioPlayer(
        thinking_sound=[
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING, volume=0.7),
            AudioConfig(BuiltinAudioClip.KEYBOARD_TYPING2, volume=0.7),
        ],
    )
    await background_audio.start(room=ctx.room, agent_session=session)
    logger.info("🔊 Background audio started")

    # Initial greeting
    await session.generate_reply(instructions=GREETING_INSTRUCTIONS)


# =========================
# Run App
# =========================
if __name__ == "__main__":
    logger.info("🎬 Starting Enhanced Crincle Cupkakes AI Agent...")
    logger.info("✨ Features: Interruption handling, Call transfer, Hold, FAQ, send_email tool, Analytics")
    agents.cli.run_app(server)
