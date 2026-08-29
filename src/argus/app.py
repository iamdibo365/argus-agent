"""Slack entrypoint for Argus using Bolt + Socket Mode.

Socket Mode means the agent connects OUT to Slack over a websocket —
no public HTTP endpoint, no API Gateway, no request-URL verification.
Perfect for running as a long-lived container on ECS Fargate.
"""
from dotenv import load_dotenv
load_dotenv()
import logging
import re

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from argus.agent import run_agent
from argus.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("argus")

app = App(token=settings.slack_bot_token)

MENTION_RE = re.compile(r"<@[A-Z0-9]+>")


def _handle(text: str, channel: str, thread_ts: str, say):
    clean = MENTION_RE.sub("", text).strip()
    if not clean:
        say(text="Hi, I'm Argus. Ask me about your Google Drive docs or this Slack workspace.",
            thread_ts=thread_ts)
        return
    contextualized = (
        f"(Context: this conversation is happening in Slack channel id {channel}. "
        f"When the user says 'this channel' or 'here', use that id.)\n\n{clean}"
    )
    try:
        answer = run_agent(contextualized, thread_id=f"{channel}:{thread_ts}")
    except Exception:
        logger.exception("Agent run failed")
        answer = "Something went wrong on my end — check the logs (and the LangSmith trace)."
    say(text=answer, thread_ts=thread_ts)


@app.event("app_mention")
def on_mention(event, say):
    _handle(
        text=event["text"],
        channel=event["channel"],
        thread_ts=event.get("thread_ts") or event["ts"],
        say=say,
    )


@app.event("message")
def on_dm(event, say):
    # Respond to direct messages; ignore channel chatter, bot echoes, and edits
    if event.get("channel_type") != "im" or event.get("bot_id") or event.get("subtype"):
        return
    _handle(
        text=event.get("text", ""),
        channel=event["channel"],
        thread_ts=event.get("thread_ts") or event["ts"],
        say=say,
    )


if __name__ == "__main__":
    logger.info("Starting Argus (Socket Mode)...")
    SocketModeHandler(app, settings.slack_app_token).start()
