import asyncio
from langchain.agents.middleware import AgentMiddleware, wrap_tool_call
from api.routers.speech import speech_event_queue


def emit_sse(event: dict):
    """
    Reliable push into FastAPI asyncio queue
    Works even inside blocking tool threads.
    """
    try:
        loop = asyncio.get_running_loop()
        loop.call_soon_threadsafe(
            lambda: asyncio.create_task(speech_event_queue.put(event))
        )
    except RuntimeError:
        asyncio.run(speech_event_queue.put(event))


class TTSMiddlewareFrontend(AgentMiddleware):
    """
    Same behavior as CLI TTS middleware
    but instead of speaking -> pushes SSE events
    """

    def after_model(self, state, runtime):
        try:
            latest = state["messages"][-1]
            text = getattr(latest, "content", None)

            if not text:
                return state

            # don't speak tool JSON / dict blobs
            if isinstance(text, dict):
                return state

            emit_sse({
                "type": "speak",
                "text": text
            })

            # print("🔥 SSE SPEAK:", text)

        except Exception as e:
            print("after_model SSE error:", e)

        return state

    @wrap_tool_call
    def silence_during_tool(request, handler):
        try:
            emit_sse({"type": "silence"})
            # print("🤫 SSE SILENCE")
        except:
            pass

        return handler(request)
