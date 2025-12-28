from fastapi import APIRouter
from core import main
import httpx
from memory.chroma_store import get_client
from api.routers.tts import get_tts_status

router = APIRouter()

def status(value, ok="Running", off="Offline"):
    return ok if value else off

def check_chroma():
    try:
        client = get_client()
        # This will raise if DB path missing / corrupted / not reachable
        client.list_collections()
        return "Connected"
    except Exception as e:
        print(f"[HEALTH] Chroma check failed: {e}")
        return "Offline"

# =========================
# Embeddings Server (REAL CHECK)
# =========================
async def check_embeddings():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://127.0.0.1:2000/health")
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "healthy":
                    return "Online"
        return "Offline"
    except Exception:
        return "Offline"
    
async def check_stt():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            r = await client.get("http://127.0.0.1:8000/api/stt/health")
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "Listening":
                    return "Online"
        return "Offline"
    except Exception:
        return "Offline"

@router.get("")
async def system_health():
    # =========================
    # LLM
    # =========================
    llm_status = "Running" if getattr(main, "brain", None) else "Offline"

    # =========================
    # Embeddings Server
    # =========================
    LMS = getattr(main, "LMS", None)
    embeddings_status = await check_embeddings()

    # =========================
    # ChromaDB
    # =========================
    chroma_status = check_chroma()

    # =========================
    # Judge / Summary Model
    # =========================
    try:
        judge_status = (
            "Running"
            if getattr(main.brain, "judge_model_ready", False)
            else "Offline"
        )
    except:
        judge_status = "Offline"


    # =========================
    # TTS
    # =========================
    tts = get_tts_status()
    tts_mode = tts.get("mode", "Disabled")
    tts_state = "Online" if tts.get("status") == "Online" else "Offline"

    # =========================
    # STT
    # =========================
    stt_status = await check_stt()

    return {
        "llmStatus": llm_status,
        "embeddingsServer": embeddings_status,
        "chromaDb": chroma_status,
        "judgeModel": judge_status,
        "ttsMode": tts_mode,
        "stt": stt_status,
    }