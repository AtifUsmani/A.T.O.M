from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import tts.voice as voice
from fastapi.responses import StreamingResponse, FileResponse
import io
import wave
import soundfile as sf
import tempfile
import os
import inspect

router = APIRouter(prefix="/api/tts", tags=["TTS"])

class TTSRequest(BaseModel):
    text: str

from core.config import cfg as config

def get_tts_status():
    from tts.voice import voiceEngine

    tts_cfg = config.get("tts", {})

    if not tts_cfg.get("enabled", False):
        return {
            "status": "Disabled",
            "mode": "Off"
        }

    if not voiceEngine:
        return {
            "status": "Offline",
            "detail": "TTS engine not initialized"
        }

    return {
        "status": getattr(voiceEngine, "status", "Unknown"),
        "mode": getattr(voiceEngine, "engine_name", "unknown")
    }


@router.get("/health")
async def tts_health():
    import tts.voice as voice

    print("DEBUG TTS HEALTH — voiceEngine =", voice.voiceEngine)

    return get_tts_status()


# @router.post("/speak")
# async def tts_speak(req: TTSRequest):
#     """
#     Push text into the TTS speech queue.
#     Will NOT block. Returns immediately.
#     """
#     if not voice.voiceEngine:
#         raise HTTPException(status_code=503, detail="TTS engine not initialized")

#     try:
#         clean = voice.voiceEngine.clean_for_tts(req.text)

#         # streaming system uses queue
#         voice.voiceEngine.text_queue.put(clean)

#         return {
#             "status": "queued",
#             "text": clean
#         }

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"TTS failed: {e}")

# @router.post("/generate")
# async def tts_generate(req: TTSRequest):
#     if not voice.voiceEngine:
#         raise HTTPException(status_code=503, detail="TTS engine not initialized")

#     try:
#         text = voice.voiceEngine.clean_for_tts(req.text)

#         # temp wav file
#         with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
#             wav_path = tmp.name

#         # --- EDGE TTS SUPPORT ---
#         if hasattr(voice.voiceEngine, "VOICE"):
#             # Edge-TTS
#             import edge_tts
#             communicate = edge_tts.Communicate(text, voice.voiceEngine.VOICE)
#             await communicate.save(wav_path)
#         else:
#             # Piper fallback
#             with wave.open(wav_path, "wb") as wav_file:
#                 voice.voiceEngine.voice.synthesize_wav(text, wav_file)

#         # return wav bytes
#         with open(wav_path, "rb") as f:
#             audio_bytes = f.read()

#         os.remove(wav_path)
#         return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/wav")

#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"TTS generate failed: {e}")

@router.post("/generate")
async def tts_generate(req: TTSRequest):
    engine = voice.voiceEngine

    if not engine:
        raise HTTPException(status_code=503, detail="TTS engine not initialized")

    try:
        text = engine.clean_for_tts(req.text) if hasattr(engine, "clean_for_tts") else req.text

        # --- SUPERSONIC / FILE-BASED ENGINE PATH ---
        if hasattr(engine, "text_to_wav"):
            engine.text_to_wav(text)

            wav_path = "tts/output.wav"
            if not os.path.exists(wav_path):
                raise RuntimeError("TTS engine did not produce output.wav")

            with open(wav_path, "rb") as f:
                audio_bytes = f.read()

        # --- BYTE-BASED ENGINE PATH (future-proof) ---
        elif hasattr(engine, "synthesize_to_wav"):
            result = engine.synthesize_to_wav(text)
            audio_bytes = await result if inspect.isawaitable(result) else result

        else:
            raise RuntimeError("Unsupported TTS engine")

        return StreamingResponse(
            io.BytesIO(audio_bytes),
            media_type="audio/wav"
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"TTS generate failed ({engine.__class__.__name__}): {e}"
        )