"""Slack tools exposed to the agent (beyond the reply the bot sends automatically)."""
from langchain_core.tools import tool
from slack_sdk import WebClient

from argus.config import settings


def _client() -> WebClient:
    return WebClient(token=settings.slack_bot_token)


@tool
def send_slack_message(channel: str, text: str) -> str:
    """Post a message to a Slack channel. `channel` may be a channel id (C0123...)
    or a name like #general. The bot must be a member of the channel."""
    resp = _client().chat_postMessage(channel=channel, text=text)
    return f"Message posted to {channel} (ts={resp['ts']})."


@tool
def get_channel_history(channel: str, limit: int = 20) -> str:
    """Fetch the most recent messages from a Slack channel (default 20, max 50).
    Useful for summarizing discussions or finding context. `channel` is a channel id."""
    limit = min(limit, 50)
    client = _client()
    resp = client.conversations_history(channel=channel, limit=limit)
    messages = resp.get("messages", [])
    if not messages:
        return "No messages found in that channel."

    lines = []
    for m in reversed(messages):  # oldest first
        user = m.get("user", m.get("bot_id", "unknown"))
        lines.append(f"[{user}]: {m.get('text', '')}")
    return "\n".join(lines)
