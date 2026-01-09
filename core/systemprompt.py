from langchain.agents.middleware import AgentMiddleware
from langchain.messages import SystemMessage

class EnsureSystemPromptMiddleware(AgentMiddleware):
    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt

    def before_agent(self, state, runtime):
        messages = state.get("messages", [])

        if not any(m.type == "system" for m in messages):
            messages.insert(0, SystemMessage(content=self.system_prompt))