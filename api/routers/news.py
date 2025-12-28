from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import httpx
import os
import time
import uuid
from datetime import datetime
import yaml

router = APIRouter(prefix="/api", tags=["news"])

with open("config.yaml", "r") as file:
    config = yaml.safe_load(file) or {}

NEWS_API_KEY = config["NEWS_API_KEY"]
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"

CACHE_TTL = 60 * 5  # 5 minutes
news_cache = {"data": None, "timestamp": 0}


async def fetch_real_news():
    if not NEWS_API_KEY:
        raise RuntimeError("NEWS_API_KEY is not set")

    params = {
        "language": "en",
        "pageSize": 10,
        "country": "us",   # change if you want geo news
        "apiKey": NEWS_API_KEY,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        res = await client.get(NEWS_API_URL, params=params)

    if res.status_code != 200:
        raise RuntimeError("Failed to fetch news feed")

    payload = res.json()

    if "articles" not in payload:
        raise RuntimeError("Invalid News API response")

    articles = []
    for article in payload["articles"]:
        articles.append({
            "id": str(uuid.uuid4()),
            "source": (article["source"]["name"] or "Unknown"),
            "headline": article.get("title") or "Untitled",
            "summary": (article.get("description") or "No summary available."),
            "timestamp": article.get("publishedAt") or datetime.utcnow().isoformat() + "Z",
        })

    return articles


# ---------- API Route ----------
@router.get("/news")
async def get_news():
    global news_cache

    # Serve from cache if fresh
    if news_cache["data"] and (time.time() - news_cache["timestamp"] < CACHE_TTL):
        return JSONResponse({"articles": news_cache["data"]})

    try:
        articles = await fetch_real_news()

        # save cache
        news_cache["data"] = articles
        news_cache["timestamp"] = time.time()

        return JSONResponse({"articles": articles})

    except Exception as e:
        # graceful fallback mock so UI doesn't break
        fallback = [
            {
                "id": str(uuid.uuid4()),
                "source": "System",
                "headline": "Live news temporarily unavailable",
                "summary": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            }
        ]
        return JSONResponse({"articles": fallback})
