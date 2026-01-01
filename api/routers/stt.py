from stt.stt import STT
from fastapi import APIRouter, HTTPException
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pydantic import BaseModel
import base64
import uuid
import time
import logging

logger = logging.getLogger("stt")
logger.setLevel(logging.DEBUG)

router = APIRouter()

stt = STT(mode='normal')

executor = ThreadPoolExecutor(max_workers=1)


from fastapi import UploadFile, File

@router.get("/health")
async def stt_health():
    """
    Reports whether STT engine is initialized and available.
    Does NOT trigger microphone or transcription.
    """

    try:
        # If STT object exists, attempt a lightweight internal readiness check
        if stt is None:
            return {"status": "Offline"}

        # Many engines have `.running`, `.alive`, or similar.
        # If yours doesn't, this won't break — it's optional.
        if hasattr(stt, "running") and not stt.running:
            return {"status": "Offline"}

        return {"status": "Listening"}

    except Exception as e:
        print("STT HEALTH ERROR:", e)
        return {"status": "Offline", "error": str(e)}

@router.post("/file")
async def stt_from_file(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    text = stt.transcribe_for_api(audio_bytes)
    return {"text": text}

@router.post("/")
async def stt_endpoint():
    """
    Performs blocking speech recognition until user finishes speaking.
    Runs in a separate thread so FastAPI's event loop never blocks.
    """

    loop = asyncio.get_event_loop()

    # Run blocking STT in thread
    text = await loop.run_in_executor(executor, stt.normal_stt)

    return {"text": text}


@router.post("/shutdown")
async def shutdown_stt_endpoint():
    """
    Gracefully shuts down the STT engine.
    """

    loop = asyncio.get_event_loop()

    await loop.run_in_executor(executor, stt.shutdown_stt)

    return {"status": "STT engine shut down"}

class STTJsonRequest(BaseModel):
    audio: str   # base64 or data URI


@router.post("")
async def stt_from_json(req: STTJsonRequest):
    req_id = str(uuid.uuid4())[:8]
    start = time.time()

    logger.info(f"[{req_id}] STT request received")

    try:
        audio_str = req.audio

        if not audio_str:
            logger.error(f"[{req_id}] Missing audio field")
            raise HTTPException(status_code=400, detail="audio field is empty")

        # Strip data URI header if present
        if "," in audio_str:
            logger.debug(f"[{req_id}] Detected data URI format, stripping header")
            audio_str = audio_str.split(",", 1)[1]

        # Log length BEFORE decoding so we know client behavior
        logger.debug(f"[{req_id}] Base64 length: {len(audio_str)}")

        try:
            audio_bytes = base64.b64decode(audio_str)
        except Exception as decode_err:
            logger.exception(f"[{req_id}] Base64 decode failed")
            raise HTTPException(status_code=400, detail=f"Invalid base64 audio: {decode_err}")

        logger.debug(f"[{req_id}] Decoded bytes size: {len(audio_bytes)} bytes")

        # OPTIONAL: Write incoming audio to disk for debugging
        try:
            debug_path = f"/tmp/stt_{req_id}.wav"
            with open(debug_path, "wb") as f:
                f.write(audio_bytes)
            logger.info(f"[{req_id}] Saved debug audio: {debug_path}")
        except Exception as save_err:
            logger.warning(f"[{req_id}] Failed to save debug audio: {save_err}")

        # Actual STT call
        logger.info(f"[{req_id}] Starting transcription...")
        text = stt.transcribe_for_api(audio_bytes)
        duration = time.time() - start

        logger.info(f"[{req_id}] STT Success in {duration:.2f}s -> '{text}'")

        return {
            "text": text,
            "debug": {
                "request_id": req_id,
                "duration_sec": round(duration, 2),
                "bytes_received": len(audio_bytes),
            }
        }

    except HTTPException:
        raise

    except Exception as e:
        logger.exception(f"[{req_id}] STT crashed unexpectedly")
        raise HTTPException(status_code=500, detail=f"STT failed [{req_id}]: {e}")