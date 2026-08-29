"""Smoke tests — run with: PYTHONPATH=src pytest tests/ (requires env vars set)."""
from argus.config import settings


def test_settings_load():
    assert settings.llm_provider in ("openai", "bedrock")


def test_tools_registered():
    from argus.tools import ALL_TOOLS
    names = {t.name for t in ALL_TOOLS}
    assert names == {
        "search_drive",
        "read_drive_file",
        "send_slack_message",
        "get_channel_history",
    }
