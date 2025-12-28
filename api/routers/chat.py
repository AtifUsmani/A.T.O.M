# api/routers/chat.py

from fastapi import APIRouter, Request
from core.llm import LLM
import yaml
import json
import asyncio
from fastapi.responses import StreamingResponse
router = APIRouter()
brain = LLM()

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file) or {}

async def stream_generator(user_input: str):
    try:
        full_text = ""

        for chunk in brain.generate_chunks(user_input, config["USER_ID"]):
            full_text += str(chunk)
            await asyncio.sleep(0)

        # 👇 FRONTEND expects {"text": "..."}
        yield json.dumps({"text": full_text})

    except Exception as e:
        yield json.dumps({"error": str(e)})

@router.post("")
async def stream(request: Request):
    body = await request.json()
    user = body.get("command", "")

    return StreamingResponse(
        stream_generator(user),
        media_type="application/json"
    )