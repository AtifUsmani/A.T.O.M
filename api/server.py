# api/server.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import chat, stream, stt, system, health, weather, boot_status, memory, tools, news, tts, speech
import signal
import sys, yaml
from core.config import cfg

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

app = FastAPI(title="ATOM API", version="1.0")

@app.on_event("startup")
def init_tts():
    try:
        tts_cfg = cfg.get("tts", {})

        if not tts_cfg.get("enabled", False):
            print("🔇 TTS disabled in config")
            return

        engine_name = tts_cfg.get("engine")

        from tts.registry import TTS_ENGINES
        from tts.voice import set_voice_engine

        engine_cls = TTS_ENGINES.get(engine_name)
        if not engine_cls:
            raise RuntimeError(
                f"Unknown TTS engine '{engine_name}'. "
                f"Available: {', '.join(TTS_ENGINES)}"
            )

        engine = engine_cls()   # ✅ correct
        set_voice_engine(engine)

        mode = getattr(engine, "engine_name", engine_cls.__name__)
        print(f"🔥 FastAPI TTS Engine Initialized ({mode})")

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
app.include_router(speech.router)

def graceful_exit(*args):
    print("\n\n[INFO] Shutting down ATOM...")

    if cfg["ROBOTIC_ARM"]:
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