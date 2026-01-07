from langchain.agents.middleware import AgentMiddleware, AgentState
from datetime import datetime, timezone
import math
import re

def render_memory_block(memories, max_items=4):
    # dedupe while preserving order
    seen = set()
    unique = []
    for m in memories:
        t = m["text"]
        if t and t not in seen:
            seen.add(t)
            unique.append(t)

    slots = unique[:max_items]
    while len(slots) < max_items:
        slots.append("")

    return "\n".join(f"- {s}" if s else "- " for s in slots)

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
        normalized = []
        
        assert any(m.type == "system" for m in state["messages"]), \
            "❌ No SystemMessage in state"
        messages = state.get("messages", [])
        if not messages:
            print("[MEMORY] No messages in state")
            return None

        # Find base system message
        system_msg = next(
            (m for m in messages if m.type == "system"),
            None
        )
        if not system_msg:
            print("[MEMORY] No system message found")
            print("[MEMORY] Message types:", [m.type for m in messages])
            return None

        assert "<<<LONG_TERM_MEMORY_START>>>" in system_msg.content, \
            "❌ Memory slot START marker missing from system prompt"

        assert "<<<LONG_TERM_MEMORY_END>>>" in system_msg.content, \
            "❌ Memory slot END marker missing from system prompt"


        # Last user message
        last_user = next(
            (m.content for m in reversed(messages) if m.type == "human"),
            None
        )
        # if not last_user or len(last_user) < 8:
        #     return None
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
                    "metadata": meta
                })

                strength = meta.get("strength", 1.0)

                try:
                    last = datetime.fromisoformat(meta.get("last_accessed"))
                    recency = math.exp(-(now - last).total_seconds() / 86_400)
                except Exception:
                    recency = 1.0

                scored.append((strength * recency, {
                    "text": text,
                    "metadata": meta
                }))

            top = sorted(scored, key=lambda x: x[0], reverse=True)[:self.max_items]

            memory_block = "\n".join(
                f"- {m['text']}" for _, m in top
            )

            # Update access metadata (lightweight reinforcement)
            for _, m in top:
                meta = m["metadata"]
                meta["last_accessed"] = now.isoformat()
                meta["access_count"] = meta.get("access_count", 0) + 1

        # print("[MEMORY] Retrieved:", [m["text"] for m in memories])

        # 🔒 SLOT REPLACEMENT (cache-safe)
        # system_msg.content = system_msg.content.replace(
        #     "[LONG_TERM_MEMORY]\n(empty)",
        #     "[LONG_TERM_MEMORY]\n" + memory_block
        # )
        
        block = render_memory_block(normalized, self.max_items)

        system_msg.content = re.sub(
            r"<<<LONG_TERM_MEMORY_START>>>.*?<<<LONG_TERM_MEMORY_END>>>",
            "<<<LONG_TERM_MEMORY_START>>>\n"
            + block +
            "\n<<<LONG_TERM_MEMORY_END>>>",
            system_msg.content,
            flags=re.DOTALL
        )

        # print("[TEST] System prompt content:\n", system_msg.content)

        return None  # DO NOT return messages
