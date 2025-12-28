from fastapi import APIRouter
from fastapi.responses import JSONResponse
from debug.tool_calls import get_tool_log
import datetime

router = APIRouter(prefix="/api", tags=["tools"])

@router.get("/tools")
async def get_tools():
    tools = [
        {
            "name": "weather_lookup",
            "description": "Fetches real-time weather information based on coordinates.",
            "parameters": ["latitude", "longitude"]
        },
        {
            "name": "system_health_check",
            "description": "Evaluates internal ATOM subsystems and returns health metrics.",
            "parameters": []
        },
        {
            "name": "robotic_arm_control",
            "description": "Controls robotic actuators for movement operations.",
            "parameters": ["shoulder", "elbow", "wrist", "speed"]
        },
        {
            "name": "memory_store",
            "description": "Stores important contextual information into long-term memory.",
            "parameters": ["content"]
        }
    ]

    return JSONResponse({"tools": tools})

@router.get("/tools/usage")
def get_tool_usage():
    return {"usage": get_tool_log()}