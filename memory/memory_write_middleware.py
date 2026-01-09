from pydantic import BaseModel, Field
from typing import List, Literal, Optional
import json
import time
import threading
from langchain.agents.middleware import AgentMiddleware

class MemoryWriteDecision(BaseModel):
    store: bool = Field(description="Whether to store the memory")

    text: Optional[str] = Field(
        default=None,
        description="ONE short factual sentence for long-term memory"
    )

    type: Optional[Literal[
        "project",
        "goal",
        "preference",
        "skill",
        "fact",
        "concern"
    ]] = None

    importance: Optional[int] = Field(ge=1, le=5)
    confidence: Optional[float] = Field(ge=0.0, le=1.0)

    tags: List[str] = Field(default_factory=list)

class ConsolidationDecision(BaseModel):
    action: Literal[
        "keep_existing",
        "add_new",
        "replace_best"
    ]

    updated_text: Optional[str] = None
class AsyncMemoryWriteMiddleware(AgentMiddleware):
    """
    Judge-controlled, async, KV-safe long-term memory writer.
    """

    def __init__(self, memory, judge_model):
        self.memory = memory
        self.judge = judge_model

    # -------------------------------
    # UTIL
    # -------------------------------
    def _run_async(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    # -------------------------------
    # AFTER AGENT
    # -------------------------------
    def after_agent(self, state, runtime):
        messages = state.get("messages", [])
        if not messages:
            return None

        last_user = next((m for m in reversed(messages) if m.type == "human"), None)
        last_ai   = next((m for m in reversed(messages) if m.type == "ai"), None)

        if not last_user or not last_ai:
            return None

        user_text = last_user.content
        ai_text   = last_ai.content

        def background_task():
            print("\n🧠 [MEMORY] Evaluating candidate memory")

            # ====================================================
            # JUDGE #1 — MEMORY FORMATION
            # ====================================================
            judge1 = self.judge.with_structured_output(MemoryWriteDecision)

            prompt = f"""
You are a long-term memory detection engine for an AI assistant.

Your task is to decide whether this interaction contains
STABLE, DECLARATIVE information about the USER that should
be remembered long-term.

DEFAULT:
- Store memory if it is a clear statement about the user's
  identity, preferences, goals, projects, skills, or emotional state.

DO NOT STORE (store=false) if the user message is:
- a greeting or social nicety (e.g. "hello", "how are you")
- a question seeking information
- small talk or phatic conversation
- a command or instruction
- temporary or situational information
- a joke or casual remark

IMPORTANT RULES:
- QUESTIONS are NEVER long-term memory by themselves.
- Only store DECLARATIVE statements about the user.
- If the user is NOT stating something ABOUT THEMSELVES, do NOT store.
ABSOLUTE CONSTRAINT (MUST FOLLOW):
- NEVER store information about the assistant itself.
- NEVER store statements beginning with or implying "I" that refer to the assistant.
- If the statement is not ABOUT THE USER, set store=false.
- Long-term memory is ONLY about the USER.
- NEVER store information about the assistant itself.
- Statements starting with:
  "I am", "I was", "I do", "I prioritize"
  MUST result in store=false.
- Assistant identity, behavior, or capabilities
  are NOT memory.
ABSOLUTE RULE:
If the memory text would describe the assistant
(e.g. "I am ATOM", "I assist with tasks", "I am designed to"),
you MUST set store=false.

Only store information that would still be true weeks later.

Clarification:
- "I" refers to the USER, not the assistant.
- If "I" refers to the assistant, do NOT store.

If store=true, you MUST:
- Provide "text": ONE short factual sentence about the user.
- Choose a type from: project | goal | preference | skill | fact | concern
- Set importance (1–5) and confidence (0.0–1.0)

If the information does not meet the above criteria, set store=false.

User said:
{user_text}

Assistant replied:
{ai_text}
"""

            try:
                decision: MemoryWriteDecision = judge1.invoke(prompt)

                # --- normalize confidence ---
                if decision.confidence is not None and decision.confidence > 1.0:
                    decision.confidence = decision.confidence / 100.0

                # --- hard validation ---
                if not decision.store:
                    return

                if not decision.text or not decision.type:
                    return

                if not (0.0 <= decision.confidence <= 1.0):
                    print("❌ [MEMORY] Invalid confidence after normalization")
                    return
            except Exception as e:
                print("❌ [MEMORY] Judge #1 schema failure:", e)
                return

            if not decision.store:
                print("🚫 [MEMORY] Judge rejected memory")
                print("    ↳ User:", user_text)
                print("    ↳ Assistant:", ai_text)
                return

            if not decision.text or not decision.type:
                print("❌ [MEMORY] Judge #1 violated contract:", decision)
                return

            # Normalize type aliases
            TYPE_ALIASES = {
                "personal-preference": "preference",
                "personal preference": "preference",
                "identity-fact": "fact"
            }
            mem_type = TYPE_ALIASES.get(decision.type, decision.type)

            print(f"✅ [MEMORY] Candidate accepted → '{decision.text}'")
            print(
                f"📌 Type={mem_type} "
                f"Importance={decision.importance} "
                f"Confidence={decision.confidence}"
            )

            # ====================================================
            # RETRIEVE SIMILAR MEMORIES
            # ====================================================
            similar = self.memory.search(
                query=decision.text,
                top_k=5
            )

            same_type = [
                m for m in similar
                if m.get("metadata", {}).get("type") == mem_type
            ]

            print(f"🔎 [MEMORY] Found {len(same_type)} similar memories of same type")

            # ====================================================
            # FAST PATH — NO SIMILARS
            # ====================================================
            if not same_type:
                print("➕ [MEMORY] No similar memories → saving new memory")
                self.memory.add(
                    text=decision.text,
                    metadata={
                        "type": mem_type,
                        "importance": decision.importance,
                        "confidence": decision.confidence,
                        "tags": decision.tags,
                        "timestamp": time.time()
                    }
                )
                print("💾 [MEMORY] Memory saved")
                return

            # ====================================================
            # JUDGE #2 — CONSOLIDATION
            # ====================================================
            judge2 = self.judge.with_structured_output(ConsolidationDecision)

            consolidation_prompt = f"""
You are a long-term memory consolidation engine.

NEW memory:
{decision.model_dump()}

EXISTING similar memories:
{json.dumps(same_type, indent=2)}

Choose ONE action:
- keep_existing
- add_new
- replace_best

Rules:
- Replace if new memory is clearer or more important
- Skip if redundant or weaker
- Add if meaningfully different

If replace_best:
- You MUST provide updated_text
"""

            try:
                consolidation: ConsolidationDecision = judge2.invoke(consolidation_prompt)
            except Exception as e:
                print("❌ [MEMORY] Judge #2 schema failure:", e)
                return

            action = consolidation.action
            print(f"🧠 [MEMORY] Consolidation decision → {action}")

            if action == "keep_existing":
                print("🛑 [MEMORY] Existing memory retained")
                return

            if action == "replace_best":
                best = max(same_type, key=lambda m: m.get("score", 0))
                if not consolidation.updated_text:
                    print("❌ [MEMORY] replace_best missing updated_text")
                    return

                self.memory.update(
                    memory_id=best["id"],
                    new_text=consolidation.updated_text
                )
                print("♻️ [MEMORY] Memory replaced")
                return

            # add_new
            self.memory.add(
                text=decision.text,
                metadata={
                    "type": mem_type,
                    "importance": decision.importance,
                    "confidence": decision.confidence,
                    "tags": decision.tags,
                    "timestamp": time.time()
                }
            )
            print("➕ [MEMORY] Additional memory saved")

        # ----------------------------------
        # HARD MEMORY WRITE GATE (CRITICAL)
        # ----------------------------------
        MIN_CHARS = 12
        BANNED_UTTERANCES = {
            "hi", "hello", "hey", "thanks", "ok", "okay", "cool", "lol"
        }

        user_text_clean = user_text.strip().lower()

        if len(user_text_clean) < MIN_CHARS:
            print(f"🚫 [MEMORY] Write skipped (too short): {repr(user_text)}")
            return None

        if user_text_clean in BANNED_UTTERANCES:
            print(f"🚫 [MEMORY] Write skipped (greeting/filler): {repr(user_text)}")
            return None

        self._run_async(background_task)
        return None