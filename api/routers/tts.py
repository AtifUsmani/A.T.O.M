from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from tts.voice import voiceEngine
import yaml

router = APIRouter(prefix="/api/tts", tags=["TTS"])

class TTSRequest(BaseModel):
    text: str


with open("config.yaml", "r") as f:
    config = yaml.safe_load(f) or {}

def get_tts_status():
    from tts.voice import voiceEngine

    # If user disabled TTS
    if not config.get("USE_TTS", False):
        return {
            "status": "Disabled",
            "mode": "Off"
        }

    if not voiceEngine:
        return {
            "status": "Offline",
            "detail": "TTS engine not initialized in runtime"
        }

    running = getattr(voiceEngine, "running", False)

    mode = "Edge-TTS" if hasattr(voiceEngine, "VOICE") else "Piper"

    return {
        "status": "Online" if running else "Idle",
        "mode": mode
    }


@router.get("/health")
async def tts_health():
    from tts.voice import voiceEngine

    print("DEBUG TTS HEALTH — voiceEngine =", voiceEngine)

    return get_tts_status()


@router.post("/speak")
async def tts_speak(req: TTSRequest):
    """
    Push text into the TTS speech queue.
    Will NOT block. Returns immediately.
    """
    if not voiceEngine:
        raise HTTPException(status_code=503, detail="TTS engine not initialized")

    try:
        clean = voiceEngine.clean_for_tts(req.text)

        # streaming system uses queue
        voiceEngine.text_queue.put(clean)

        return {
            "status": "queued",
            "text": clean
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {e}")
