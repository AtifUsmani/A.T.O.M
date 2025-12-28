# api/routers/stream.py

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from core.llm import LLM
import json
import asyncio
import yaml

router = APIRouter()
brain = LLM()

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file) or {}

async def stream_generator(user_input: str):
    try:
        for chunk in brain.generate_chunks(user_input, config["USER_ID"]):
            # send ONLY the new piece
            yield str(chunk)
            await asyncio.sleep(0)

    except Exception as e:
        yield f"ERROR: {str(e)}"

@router.post("")
async def stream(request: Request):
    body = await request.json()
    user = body.get("command", "")

    return StreamingResponse(
        stream_generator(user),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )