from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import httpx
import time
import asyncio

router = APIRouter(prefix="/api", tags=["weather"])

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# ---- Simple in-memory cache ----
CACHE_TTL = 60 * 5  # 5 minutes
weather_cache = {}
cache_lock = asyncio.Lock()
# --------------------------------


@router.post("/weather")
async def get_weather(payload: dict):
    lat = payload.get("latitude")
    lon = payload.get("longitude")

    if lat is None or lon is None:
        raise HTTPException(400, "Latitude and Longitude are required")

    # Normalize cache key to avoid unnecessary misses
    key = (round(float(lat), 2), round(float(lon), 2))

    async with cache_lock:
        cached = weather_cache.get(key)
        if cached and (time.time() - cached["timestamp"] < CACHE_TTL):
            return JSONResponse(cached["data"])

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["temperature_2m", "weather_code", "wind_speed_10m"],
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "sunrise",
            "sunset",
        ],
        "timezone": "auto",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(OPEN_METEO_URL, params=params)

        if response.status_code != 200:
            raise HTTPException(500, "Failed to fetch weather data from Open-Meteo")

        data = response.json()

        # Store to cache
        async with cache_lock:
            weather_cache[key] = {
                "data": data,
                "timestamp": time.time()
            }

        return JSONResponse(data)

    except Exception as e:
        raise HTTPException(500, f"Weather service error: {str(e)}")
