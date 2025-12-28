# debug/tool_calls.py
from datetime import datetime

TOOL_CALL_LOG = []

def record_tool_call(tool, metadata=None):
    TOOL_CALL_LOG.append({
        "tool": tool,
        "metadata": metadata or {},
        "timestamp": datetime.now().isoformat()
    })

def get_tool_log():
    return TOOL_CALL_LOG
