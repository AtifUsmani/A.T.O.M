from langchain.agents.middleware import AgentMiddleware, AgentState
from datetime import datetime, timezone
import math
import re

MEMORY_SLOTS = 4          # number of lines
CHARS_PER_SLOT = 96       # characters per slot (pick once)

def fixed_width(text: str, width: int) -> str:
    text = normalize_memory_text(text)

    if len(text) > width:
        text = text[:width]

    # Right-pad with spaces to enforce fixed size
    return text + (" " * (width - len(text)))

def normalize_memory_text(text: str) -> str:
    if not text:
        return ""

    # Remove newlines (critical)
    text = text.replace("\n", " ").replace("\r", " ")

    # Collapse whitespace
    text = re.sub(r"\s+", " ", text)

    # ASCII-only (recommended for tokenizer stability)
    text = text.encode("ascii", "ignore").decode()

    # Prevent marker injection
    text = text.replace("<", "").replace(">", "")

    return text.strip()

def render_memory_block(memories):
    """
    memories: list of dicts with at least {"text": "..."}
    Returns a KV-stable memory block string.
    """
    lines = []

    for i in range(MEMORY_SLOTS):
        text = memories[i]["text"] if i < len(memories) else ""
        payload = fixed_width(text, CHARS_PER_SLOT)
        lines.append(f"[{i+1:02d}] {payload}")

    return "\n".join(lines)

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

            top = sorted(scored, key=lambda x: x[0], reverse=True)[:MEMORY_SLOTS]


            # Update access metadata (lightweight reinforcement)
            for _, m in top:
                meta = m["metadata"]
                meta["last_accessed"] = now.isoformat()
                meta["access_count"] = meta.get("access_count", 0) + 1

        # print("[MEMORY] Retrieved:", [m["text"] for m in memories])
        
        top_memories = [m for _, m in top]

        block = render_memory_block(top_memories)

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
