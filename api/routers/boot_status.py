from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import asyncio
import httpx
import yaml

router = APIRouter(prefix="/api", tags=["boot"])

with open("config.yaml", "r") as f:
    config = yaml.safe_load(f) or {}

# =========================
# HEALTH HELPERS
# =========================
async def check_atom_core():
    try:
        from core import main
        # If initialize() ran, brain + LMS exist
        if hasattr(main, "brain"):
            return True
        return False
    except Exception:
        return False


async def check_memory_engine():
    try:
        from memory.chroma_store import get_client
        client = get_client()
        _ = client.heartbeat()      # will throw if dead
        return True
    except Exception:
        return False


async def check_embeddings_server():
    try:
        url = config.get("EMBEDDING_SERVER_BASE_URL", "http://localhost:2000")
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{url.replace('/v1','')}/health")
            return res.status_code == 200
    except Exception:
        return False


async def check_robotics():
    try:
        # If robotic arm not even enabled → fail
        if not config.get("ROBOTIC_ARM", False):
            return False

        from tools import tools

        # If initialization failed earlier, robotarm = None
        if getattr(tools, "robotarm", None) is None:
            return False
        
        return True

    except Exception:
        return False

MODULE_CHECKS = {
    "ATOM_CORE": check_atom_core,
    "MEMORY_ENGINE": check_memory_engine,
    "EMBEDDINGS_SERVER": check_embeddings_server,
    "ROBOTICS_INTERFACE": check_robotics,
}


# =========================
# BOOT ENDPOINT
# =========================
@router.post("/boot-status")
async def boot_status(payload: dict):
    module = payload.get("module")

    if not module:
        raise HTTPException(400, "Missing module field")

    # cinematic delay so UI animation looks sexy 😎
    await asyncio.sleep(0.35)

    if module not in MODULE_CHECKS:
        return JSONResponse({"status": "error"})

    is_ok = await MODULE_CHECKS[module]()

    if is_ok:
        return JSONResponse({"status": "ok"})

    return JSONResponse({"status": "error"})
