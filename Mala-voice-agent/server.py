"""
server.py — FastAPI HTTP server that runs on Railway alongside the agent.

Provides:
  POST /token  → generates a LiveKit token for the frontend
  GET  /health → Railway health check

Run with:
  uvicorn server:app --host 0.0.0.0 --port 8000
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from livekit.api import AccessToken, VideoGrants
from dotenv import load_dotenv

load_dotenv(".env.local")

app = FastAPI()

# ── CORS ─────────────────────────────────────────────────────────
# Add your Vercel URL here after you deploy
ALLOWED_ORIGINS = [
    os.getenv("FRONTEND_URL", "*"),   # set FRONTEND_URL=https://your-app.vercel.app in Railway
    "http://localhost:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Models ───────────────────────────────────────────────────────
class TokenRequest(BaseModel):
    room: str = "crincle-cupkakes"
    identity: str = "customer"


# ── Routes ───────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """Railway uses this to confirm the service is alive."""
    return {"status": "ok", "service": "Crincle Cupkakes API"}


@app.post("/token")
async def generate_token(req: TokenRequest):
    """
    Called by the Vercel frontend when a customer clicks 'Start talking to Sana'.
    Returns a short-lived LiveKit JWT token + the LiveKit server URL.
    The token lets the customer join the room without exposing API credentials.
    """
    api_key     = os.getenv("LIVEKIT_API_KEY")
    api_secret  = os.getenv("LIVEKIT_API_SECRET")
    livekit_url = os.getenv("LIVEKIT_URL")

    if not api_key or not api_secret or not livekit_url:
        raise HTTPException(
            status_code=500,
            detail="LiveKit credentials not configured on Railway"
        )

    try:
        token = (
            AccessToken(api_key, api_secret)
            .with_identity(req.identity)
            .with_name("Customer")
            .with_grants(VideoGrants(
                room_join=True,
                room=req.room,
                can_publish=True,       # customer sends mic audio
                can_subscribe=True,     # customer receives avatar video + audio
            ))
            .to_jwt()
        )

        return {
            "token": token,
            "url": livekit_url,
            "room": req.room,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
