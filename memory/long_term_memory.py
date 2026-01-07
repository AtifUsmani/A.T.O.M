import uuid
from datetime import datetime, timezone
import math
from langchain.agents.middleware import AgentMiddleware, AgentState
# -------------------------------
# Long Term Memory
# -------------------------------
class LongTermMemory:
    """
    Judge-controlled, Chroma-backed long-term memory store.
    """

    REQUIRED_FIELDS = ["type", "importance", "confidence"]

    def __init__(self, store):
        self.store = store

    def _sanitize_metadata(self, meta: dict) -> dict:
        """
        Ensure metadata is Chroma-safe.
        Chroma allows ONLY scalar values.
        """
        clean = {}
        for k, v in meta.items():
            if isinstance(v, list):
                clean[k] = ", ".join(map(str, v))
            elif isinstance(v, dict):
                clean[k] = str(v)
            else:
                clean[k] = v
        return clean

    # -------------------------------
    # VALIDATION
    # -------------------------------

    def _validate_metadata(self, metadata: dict):
        if not metadata:
            return False, "metadata missing"

        for field in self.REQUIRED_FIELDS:
            if field not in metadata:
                return False, f"missing field: {field}"

        if not isinstance(metadata["importance"], int) or not (1 <= metadata["importance"] <= 5):
            return False, "importance must be int 1–5"

        if not isinstance(metadata["confidence"], (float, int)) or not (0 <= metadata["confidence"] <= 1):
            return False, "confidence must be float 0–1"

        return True, None

    # -------------------------------
    # ADD MEMORY
    # -------------------------------

    def add(self, text: str, metadata: dict):
        if not text or not text.strip():
            return

        ok, err = self._validate_metadata(metadata)
        if not ok:
            return

        memory_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        # 1️⃣ Always define meta FIRST
        meta = dict(metadata)

        # 2️⃣ Normalize tags safely
        tags = meta.get("tags", "")
        if isinstance(tags, list):
            tags = ", ".join(map(str, tags))

        # 3️⃣ Update meta
        meta.update({
            "memory_id": memory_id,
            "created_at": now,
            "last_accessed": now,
            "access_count": 0,
            "strength": meta["importance"] * meta["confidence"],
            "source": meta.get("source", "conversation"),
            "tags": tags,
        })

        # 4️⃣ Sanitize metadata (CRITICAL)
        meta = self._sanitize_metadata(meta)

        # 5️⃣ Write to Chroma
        self.store.add_texts(
            texts=[text.strip()],
            metadatas=[meta],
            ids=[memory_id],
        )

    # -------------------------------
    # RUNTIME QUERY (NO SCORES)
    # -------------------------------

    def query(self, query: str, k=5, type_filter=None):
        if not query or not query.strip():
            return []

        try:
            search_kwargs = {}
            if type_filter:
                search_kwargs["filter"] = {"type": type_filter}

            docs = self.store.similarity_search(
                query=query,
                k=k,
                **search_kwargs,
            )

            return [
                {
                    "text": doc.page_content,
                    "metadata": doc.metadata,
                }
                for doc in docs
            ]

        except Exception as e:
            print("❌ Memory query failed:", e)
            return []

    # -------------------------------
    # SEARCH (MANAGEMENT / CONSOLIDATION)
    # -------------------------------

    def search(self, query: str, top_k=5):
        """
        Used ONLY for consolidation & updates.
        Returns similarity scores + ids.
        """
        if not query or not query.strip():
            return []

        try:
            results = self.store.similarity_search_with_score(
                query=query,
                k=top_k,
            )

            out = []
            for doc, dist in results:
                try:
                    similarity = 1.0 / (1.0 + float(dist))
                except Exception:
                    similarity = 0.0

                meta = doc.metadata or {}
                out.append({
                    "id": meta.get("memory_id"),
                    "text": doc.page_content,
                    "metadata": meta,
                    "score": similarity,
                })

            return out

        except Exception:
            return []

    # -------------------------------
    # UPDATE MEMORY (SAFE)
    # -------------------------------

    def update(self, memory_id: str, new_text: str, new_metadata: dict = None):
        if not memory_id or not new_text or not new_text.strip():
            return

        try:
            existing = self.store.get(ids=[memory_id])
            if not existing or not existing.get("ids"):
                return

            old_meta = existing["metadatas"][0]

            if new_metadata:
                old_meta.update(new_metadata)

            old_meta["strength"] = (
                old_meta.get("importance", 1)
                * old_meta.get("confidence", 0.0)
            )

            old_meta = self._sanitize_metadata(old_meta)

            self.store.delete(ids=[memory_id])
            self.store.add_texts(
                texts=[new_text.strip()],
                metadatas=[old_meta],
                ids=[memory_id],
            )

        except Exception:
            pass


class MemoryRetrievalMiddleware(AgentMiddleware):
    """
    KV-cache-safe memory retrieval.
    Mutates a fixed memory slot instead of inserting messages.
    """

    def __init__(self, memory, k=5, max_items=4):
        self.memory = memory
        self.k = k
        self.max_items = max_items

    def before_model(self, state: AgentState, runtime):
        print("🔥 MemoryRetrievalMiddleware.before_model CALLED")
        print("[TEST] Message types:", [m.type for m in state["messages"]])
        print(f"All memories: {self.memory.store.get()}")

        self.memory.add(
            "User is building ATOM as a local-first AI OS.",
            {
                "type": "project",
                "importance": 5,
                "confidence": 1.0,
            },
        )

        print(f"Manual Search test for ATOM: {self.memory.query('ATOM', k=5)}")

        assert any(m.type == "system" for m in state["messages"]), \
            "❌ No SystemMessage in state"

        messages = state.get("messages", [])
        if not messages:
            print("[MEMORY] No messages in state")
            return None

        # Find base system message
        system_msg = next(
            (m for m in messages if m.type == "system"),
            None,
        )

        if not system_msg:
            print("[MEMORY] No system message found")
            print("[MEMORY] Message types:", [m.type for m in messages])
            return None

        print("[TEST] System prompt content:\n", system_msg.content)

        assert "[LONG_TERM_MEMORY]" in system_msg.content, \
            "❌ Memory slot missing from system prompt"

        # Last user message
        last_user = next(
            (m.content for m in reversed(messages) if m.type == "human"),
            None,
        )

        if not last_user:
            print("[MEMORY] No human message found")
            return None

        if len(last_user) < 8:
            print("[MEMORY] User message too short:", repr(last_user))
            return None

        # Retrieve memories
        memories = self.memory.query(last_user, k=self.k)

        if not memories:
            memory_block = "(empty)"
        else:
            now = datetime.now(timezone.utc)
            scored = []
            normalized = []

            for m in memories:
                if isinstance(m, dict):
                    text = m.get("text", "")
                    meta = m.get("metadata", {})
                elif isinstance(m, str):
                    text = m
                    meta = {}
                else:
                    continue

                normalized.append({
                    "text": text,
                    "metadata": meta,
                })

                strength = meta.get("strength", 1.0)

                try:
                    last = datetime.fromisoformat(meta.get("last_accessed"))
                    recency = math.exp(
                        -(now - last).total_seconds() / 86_400
                    )
                except Exception:
                    recency = 1.0

                scored.append((strength * recency, m))

            top = sorted(
                scored,
                key=lambda x: x[0],
                reverse=True,
            )[:self.max_items]

            memory_block = "\n".join(
                f"- {m['text']}"
                for _, m in top
            )

            # Update access metadata (lightweight reinforcement)
            for _, m in top:
                meta = m["metadata"]
                meta["last_accessed"] = now.isoformat()
                meta["access_count"] = meta.get("access_count", 0) + 1

        print("[MEMORY] Retrieved:", [m["text"] for m in memories])

        # 🔒 SLOT REPLACEMENT (cache-safe)
        system_msg.content = system_msg.content.replace(
            "[LONG_TERM_MEMORY]\n(empty)",
            "[LONG_TERM_MEMORY]\n" + memory_block,
        )

        return None  # DO NOT return messages
