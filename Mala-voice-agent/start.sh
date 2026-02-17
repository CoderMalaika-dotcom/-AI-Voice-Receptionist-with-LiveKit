#!/bin/bash
# start.sh — Railway start command
# Runs the FastAPI token server AND the LiveKit agent at the same time

echo "🚀 Starting Crincle Cupkakes services..."

# Start FastAPI server in the background (handles /token and /health)
uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} &

# Start the LiveKit agent (handles voice calls)
python Agent.py start

# If agent exits, kill the server too
kill %1
