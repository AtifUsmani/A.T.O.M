# api/server.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import chat, stream, stt, system, health, weather, boot_status, memory, tools, news, tts
import signal
import sys, yaml
from tts.voice import set_voice_engine
from tts.tts_edge import TTS as EdgeTTS
from tts.tts_piper import TTS as PiperTTS

with open("config.yaml", "r") as f:
    cfg = yaml.safe_load(f) or {}

try:
    from core.lms import LMSTUDIO
    LMS = LMSTUDIO()
    try:
        LMS.load_model()
    except Exception as e:
        print(f"[ERROR] Failed to initialize Model: {e}")
    try:
        LMS.load_summary_model()
    except Exception as e:
        print(f"[ERROR] Failed to initialize Summary Model: {e}")

except Exception as e:
    print(f"[ERROR] Failed to initialize Model: {e}")

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file) or {}

app = FastAPI(title="ATOM API", version="1.0")


@app.on_event("startup")
def init_tts():
    if not cfg.get("USE_TTS", False):
        return

    try:
        if cfg.get("USE_EDGE_TTS", False):
            engine = EdgeTTS()
        else:
            engine = PiperTTS()

        set_voice_engine(engine)
        print("🔥 FastAPI TTS Engine Initialized")
    except Exception as e:
        print("❌ Failed to init TTS:", e)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api/chat", tags=["chat"])  # Gives full output
app.include_router(stream.router, prefix="/api/chat/stream", tags=["stream"])      # Gives chunks in output for streaming
app.include_router(system.router, prefix="/api/system", tags=["system"])        
app.include_router(stt.router, prefix="/api/stt", tags=["stt"])
app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(weather.router)
app.include_router(boot_status.router)
app.include_router(memory.router)
app.include_router(tools.router)
app.include_router(news.router)
app.include_router(tts.router)

def graceful_exit(*args):
    print("\n\n[INFO] Shutting down ATOM...")

    if config["ROBOTIC_ARM"]:
        try:
            from tools.tools import close_connections
            close_connections()
        except Exception as e:
            print(f"[WARN] Failed to close tool connections: {e}")
    else:
        pass

    try:
        LMS.unload_model()
    except Exception as e:
        print(f"[WARN] Failed to unload model: {e}")
    
    print("\n[INFO] Exit complete. Goodbye.")
    sys.exit(0)

# Catch Ctrl+C globally
signal.signal(signal.SIGINT, graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)