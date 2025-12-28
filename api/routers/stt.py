from stt.stt import STT
from fastapi import APIRouter
import asyncio
from concurrent.futures import ThreadPoolExecutor

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