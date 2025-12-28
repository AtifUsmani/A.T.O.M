#llm.py

from langchain.agents import create_agent, AgentState
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langchain.messages import ToolMessage, RemoveMessage
from langchain.agents.middleware import ToolRetryMiddleware, FilesystemFileSearchMiddleware, wrap_tool_call, before_model, SummarizationMiddleware
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from tools.tools import tools
from tools.system_tools import system_tools
from langgraph.runtime import Runtime
from typing import Any
from memory.long_term_memory import LongTermMemory
from memory.memory_write_middleware import AsyncMemoryWriteMiddleware
from debug.token_debug_middleware import TokenDebugMiddleware
from debug.json_logging_middleware import JSONLoggingMiddleware
from embedding.embedding_client import FastAPIEmbeddings
from memory.chroma_store import get_chroma_store
from memory.memory_injection import PeriodicJudgeMiddleware, JudgedMemoryInjectionMiddleware
from tts.middleware import TTSMiddleware

# Load the prompt from a text file
with open("prompt.txt", "r", encoding="utf-8") as f:
    atom_prompt = f.read()

@wrap_tool_call
def handle_tool_errors(request, handler):
    """Handle tool execution errors with custom messages."""
    try:
        return handler(request)
    except Exception as e:
        return ToolMessage(
            content=f"Tool error: Please check your input and try again. ({str(e)})",
            tool_call_id=request.tool_call["id"]
        )

@before_model
def trim_messages(state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
    """Keep only the last few messages to fit context window."""
    messages = state["messages"]

    if len(messages) <= 3:
        return None

    first_msg = messages[0]
    recent_messages = messages[-3:] if len(messages) % 2 == 0 else messages[-4:]
    new_messages = [first_msg] + recent_messages

    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            *new_messages
        ]
    }

class LLM():
    def __init__(self, tools=tools + system_tools,
             system_prompt=atom_prompt,
             config_file="config.yaml"):

        import yaml
        from pathlib import Path

        self.config_file = config_file
        self.tools = tools
        self.system_prompt = system_prompt
        self.judge_model_ready = False

        # -----------------------------
        # Load YAML config safely
        # -----------------------------
        try:
            if not Path(self.config_file).exists():
                raise FileNotFoundError(f"Config file '{self.config_file}' not found.")

            with open(self.config_file, "r") as file:
                config = yaml.safe_load(file) or {}
        except Exception as e:
            print(f"[ERROR] Failed to load configuration: {e}")
            config = {}

        # -----------------------------
        # Extract config with fallbacks
        # -----------------------------
        try:
            llm_cfg = config.get("LLM", {})
            self.model_name = llm_cfg.get("MODEL_NAME", "qwen/qwen3-vl-4b")
            self.summary_model_name = llm_cfg.get("SUMMARY_MODEL_NAME", "qwen/qwen3-1.7b")
            self.base_url = llm_cfg.get("BASE_URL", "http://localhost:1234/v1")
            self.api_key = llm_cfg.get("API_KEY", "no-key-required")
            self.embedding_url = config['EMBEDDING_SERVER_BASE_URL']
        except Exception as e:
            print(f"[ERROR] Invalid config format: {e}")
            self.model_name = "qwen/qwen3-vl-4b"
            self.summary_model_name = "qwen/qwen3-1.7b"
            self.base_url = "http://localhost:1234/v1"
            self.api_key = "no-key-required"
            self.embedding_url = "http://localhost:2000/v1"

        # -----------------------------
        # Safe Model Initialization
        # -----------------------------
        try:
            self.model = ChatOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.model_name,
                streaming=True,
                verbose=False,
                temperature=0,
                max_tokens=1024,
                max_retries=3,
                timeout=600
            )

            self.summary_model = ChatOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                model=self.summary_model_name,
                streaming=False,
                temperature=0,
                max_retries=3,
                timeout=400
            )
            self.judge_model_ready = True
        except Exception as e:
            print(f"[ERROR] Failed to initialize ChatOpenAI model: {e}")
            self.judge_model_ready = False
            self.model = None

        # client = chromadb.PersistentClient(path="./atom_db")
        self.embeddings = FastAPIEmbeddings(base_url=self.embedding_url)
        self.store = get_chroma_store()

        self.long_term_memory = LongTermMemory(store=self.store)
        # memory_retriever = MemoryRetrievalMiddleware(self.long_term_memory)
        memory_writer = AsyncMemoryWriteMiddleware(self.long_term_memory, self.summary_model)
        debugger = TokenDebugMiddleware(tokenizer=self.model.get_num_tokens)

        # -----------------------------
        # Validate tools list
        # -----------------------------
        if not isinstance(self.tools, (list, tuple)):
            print("[WARN] Tools must be a list/tuple. Converting to empty list.")
            self.tools = []

        # -----------------------------
        # Safe Agent Initialization
        # -----------------------------
        try:
            if self.model is None:
                raise RuntimeError("Model is not initialized. Agent cannot be created.")

            self.agent = create_agent(
                self.model,
                tools=self.tools,
                system_prompt=self.system_prompt,
                middleware=[
                    # debugger,
                    JSONLoggingMiddleware(output_file='atom_logs.json'),
                    TTSMiddleware(),
                    PeriodicJudgeMiddleware(self.summary_model, self.store, config['USER_ID'], 10),
                    JudgedMemoryInjectionMiddleware(config['USER_ID']),
                    trim_messages,
                    SummarizationMiddleware(
                        model=self.summary_model,
                        trigger=("tokens", 8000),
                        keep=("messages", 20),
                    ),
                    memory_writer,
                    ToolRetryMiddleware(
                        max_retries=3,
                        backoff_factor=2.0,
                        initial_delay=1.0,
                    ),
                    FilesystemFileSearchMiddleware(
                        root_path=Path(__file__).resolve(),
                        use_ripgrep=True,
                    ),
                    handle_tool_errors,
                ],
                checkpointer=InMemorySaver(),
                # debug=True,
                store=self.store
            )
        except Exception as e:
            print(f"[ERROR] Failed to create agent: {e}")
            self.agent = None

    def retrieve_context(self, user_input: str) -> str:
        # Retrieve similar memories
        results = self.store.similarity_search(user_input, k=1)

        # results = self.store.similarity_search_by_vector(
        #     embedding=self.embeddings.embed_query(user_input), k=3
        # )

        if not results:
            return ""

        # Debug logging
        print(f"✅ Retrieved {len(results)} memories")
        print(f"✅ Collection size: {self.store._collection.count()}")

        memories = "\n".join(
            f"- {doc.page_content} (source={doc.metadata})"
            for doc in results
        )

        return f"## Memories of user\n{memories}"

    def give_output(self, role_input, role):        
        response = self.agent.invoke(
            {"messages": [{"role": str(role), "content": str(role_input)}]},
            {"configurable": {"thread_id": "1"}},
        )

        ai_message = response['messages'][-1].content

        print(ai_message)
        return ai_message

    # def generate_chunks(self, user_input: str, user_id: str):
    #     # rel_mem = self.retrieve_context(user_input=user_input)
    #     # print(rel_mem)
    #     for token, metadata in self.agent.stream(
    #         {"messages": [
    #             # {"role": "system", "content": self.system_prompt},
    #             {"role": "user", "content": str(user_input)}
    #             ]},
    #         {"configurable": {"thread_id": user_id}},
    #         stream_mode="messages",
    #     ):
    #         output_chunk = None
    #         # --- NEW FILTER LOGIC ---
    #         # Only act when node is "model"
    #         if metadata.get("langgraph_node") == "model":
    #             # token.content_blocks is a list of dicts like:
    #             # [{'type': 'text', 'text': 'Good'}]
    #             for block in token.content_blocks:
    #                 if block.get("type") == "text":
    #                     # print(block.get("text"), end="")   # prints continuous text

    #                     output_chunk = block.get("text")
                    
    #         # --- END OF NEW LOGIC ---

    #         # --- ORIGINAL DEBUG PRINT (kept as requested, but you may comment out) ---
    #         # print(f"\nnode: {metadata['langgraph_node']}")
    #         # print(f"content: {token.content_blocks}")
    #         # print("\n")
    #         # --------------------------------------------
    #             # --- YIELD ONLY IF VALID ---
    #         if output_chunk is not None:
    #             yield output_chunk

    def generate_chunks(self, user_input: str, user_id: str):
        for token, metadata in self.agent.stream(
            {
                "messages": [
                    {"role": "user", "content": str(user_input)}
                ]
            },
            {"configurable": {"thread_id": user_id}},
            stream_mode="messages",
        ):
            # only handle model chunks
            if metadata.get("langgraph_node") != "model":
                continue

            for block in token.content_blocks:
                if block.get("type") == "text":
                    text = block.get("text")
                    if text:
                        yield text
