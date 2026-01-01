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
        full = ""
        for chunk in brain.generate_chunks(user_input, config["USER_ID"]):
            full += str(chunk)
            yield json.dumps({
                "text": full
            }) + "\n"
            await asyncio.sleep(0)
            print("RAW CHUNK:", repr(chunk))

        # optional explicit done message
        yield json.dumps({"done": True}) + "\n"
    except Exception as e:
        yield json.dumps({"error": str(e)}) + "\n"

@router.post("")
async def stream(request: Request):
    body = await request.json()
    user = body.get("command", "")

    return StreamingResponse(
        stream_generator(user),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )