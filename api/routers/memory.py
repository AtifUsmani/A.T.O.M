from fastapi import APIRouter
from memory.chroma_store import get_chroma_store
from datetime import datetime

router = APIRouter(
    prefix="/api/memory",
    tags=["Memory"]
)

@router.get("")
async def get_recent_memory():
    try:
        store = get_chroma_store()

        results = store.get(
            include=["documents", "metadatas"]
        )

        documents = results.get("documents", []) or []
        metadatas = results.get("metadatas", []) or []

        memory_items = []

        for doc, meta in zip(documents, metadatas):
            timestamp = (
                meta.get("timestamp")
                or meta.get("time")
                or datetime.utcnow().isoformat()
            )

            memory_items.append({
                "content": doc,
                "timestamp": timestamp
            })

        # newest ➜ oldest
        memory_items.sort(
            key=lambda x: x["timestamp"],
            reverse=True
        )

        memory_items = memory_items[:15]

        return {"memory": memory_items}

    except Exception as e:
        print("MEMORY API ERROR:", e)
        return {
            "memory": [],
            "error": str(e)
        }
