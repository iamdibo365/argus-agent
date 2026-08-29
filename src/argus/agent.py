"""Argus core agent — a LangGraph ReAct agent with Slack + Google Drive tools.

Observability: set LANGSMITH_TRACING=true and LANGSMITH_API_KEY to get full
trace trees (every LLM call and tool invocation) in LangSmith automatically.
"""
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from argus.llm import get_llm
from argus.tools import ALL_TOOLS

SYSTEM_PROMPT = """You are Argus, an AI operations agent embedded in this team's Slack workspace
with read access to the team's Google Drive.

Capabilities:
- Search Google Drive and read the contents of Docs, Sheets, Slides, and text files.
- Read recent Slack channel history and post messages to channels.

Behavior:
- Be concise. Slack is a chat medium — answer in short, well-formatted messages.
- When asked about documents, ALWAYS search Drive first rather than guessing.
- Cite the file name you pulled information from.
- If a request is ambiguous, ask one clarifying question instead of assuming.
- Never fabricate file contents. If you can't find something, say so.
- Only post to other channels when explicitly asked to."""

# In-memory conversation state, keyed by Slack thread. For production,
# swap MemorySaver for a persistent checkpointer (e.g., Postgres/DynamoDB).
_checkpointer = MemorySaver()

_agent = create_react_agent(
    model=get_llm(),
    tools=ALL_TOOLS,
    prompt=SYSTEM_PROMPT,
    checkpointer=_checkpointer,
)


def run_agent(user_message: str, thread_id: str) -> str:
    """Run one agent turn. `thread_id` scopes conversation memory to a Slack thread."""
    result = _agent.invoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content
