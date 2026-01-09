import hashlib
from langchain.agents.middleware import AgentMiddleware, AgentState

# ----------------------------------------
# Utilities
# ----------------------------------------

def stable_prompt_hash(messages):
    """
    Hash ONLY the KV-cacheable prefix:
    - system
    - injected memory slot
    - all messages before last human
    """
    parts = []
    for m in messages[:-1]:
        parts.append(f"{m.type}:{m.content.strip()}")
    joined = "\n".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def count_tokens(messages, tokenizer):
    return sum(len(tokenizer.encode(m.content)) for m in messages)


def extract_memory_block(system_text):
    start = "<<<LONG_TERM_MEMORY_START>>>"
    end = "<<<LONG_TERM_MEMORY_END>>>"
    if start not in system_text or end not in system_text:
        return None
    return system_text.split(start)[1].split(end)[0]


# ----------------------------------------
# KV Cache Monitor
# ----------------------------------------

class KVCacheMonitor:
    def __init__(self):
        self.last_hash = None

    def check(self, prompt_hash):
        reused = prompt_hash == self.last_hash
        self.last_hash = prompt_hash
        return reused


# ----------------------------------------
# Debug Middleware
# ----------------------------------------

class BigDebugMiddleware(AgentMiddleware):
    """
    READ-ONLY debug middleware.
    Measures:
    - KV cache reuse eligibility
    - Prompt drift
    - Memory injection health
    - Token counts
    """

    def __init__(self, tokenizer, kv_monitor=None, debug=True):
        self.tokenizer = tokenizer
        self.kv_monitor = kv_monitor or KVCacheMonitor()
        self.debug = debug
        self.turn = 0

    def before_model(self, state: AgentState, runtime):
        self.turn += 1
        messages = state.get("messages", [])

        if not messages:
            return None

        # -----------------------------
        # Identify system + last user
        # -----------------------------
        system_msg = next((m for m in messages if m.type == "system"), None)
        last_user = next((m for m in reversed(messages) if m.type == "human"), None)

        if not system_msg or not last_user:
            return None

        # -----------------------------
        # Memory slot inspection
        # -----------------------------
        memory_block = extract_memory_block(system_msg.content)

        if memory_block is None:
            memory_lines = []
            memory_tokens = 0
            memory_ok = False
        else:
            memory_lines = [
                line.strip("- ").strip()
                for line in memory_block.splitlines()
                if line.strip("- ").strip()
            ]

            memory_tokens = len(self.tokenizer.encode(memory_block))
            memory_ok = True

        # -----------------------------
        # Prompt hashing (KV cache)
        # -----------------------------
        prompt_hash = stable_prompt_hash(messages)
        kv_reused = self.kv_monitor.check(prompt_hash)

        # -----------------------------
        # Token counts
        # -----------------------------
        total_prompt_tokens = count_tokens(messages, self.tokenizer)

        # -----------------------------
        # Logging
        # -----------------------------
        if self.debug:
            print("\n================ DEBUG TURN =================")
            print(f"[TURN] {self.turn}")
            print(f"[KV] prefix reusable: {kv_reused}")
            print(f"[PROMPT] total tokens: {total_prompt_tokens}")
            print(f"[MEMORY] slot present: {memory_ok}")
            print(f"[MEMORY] items: {len(memory_lines)}")
            print(f"[MEMORY] tokens: {memory_tokens}")
            print(f"[MEMORY] contents: {memory_lines}")
            print("============================================\n")

        # -----------------------------
        # Health summary (single line)
        # -----------------------------
        print(
            f"[HEALTH] "
            f"KV={'HIT' if kv_reused else 'MISS'} | "
            f"PromptTokens={total_prompt_tokens} | "
            f"MemoryTokens={memory_tokens} | "
            f"MemoryItems={len(memory_lines)}"
        )

        return None  # READ-ONLY

from tiktoken import get_encoding

tokenizer = get_encoding("cl100k_base")
kv_monitor = KVCacheMonitor()

debug_middleware = BigDebugMiddleware(
    tokenizer=tokenizer,
    kv_monitor=kv_monitor,
    debug=True
)