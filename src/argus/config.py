"""Central configuration loaded from environment variables (.env in local dev)."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # LLM
    llm_provider: str = "openai"          # "openai" | "bedrock"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    aws_region: str = "us-east-1"
    bedrock_model_id: str = "us.anthropic.claude-3-5-sonnet-20241022-v2:0"

    # Slack
    slack_bot_token: str = ""
    slack_app_token: str = ""

    # Google Drive
    google_application_credentials: str = "./service-account.json"
    google_drive_folder_id: str = "1MNC2Tm-dy8bPOFoUtOk39NxSZ0rzgvgV,rIPvjNPsdiAfB0EJm4Fycmj28Cl3J_7I,1B9hNb1PfaR3HXEQbJWgpFmJCBekBKdjR"


settings = Settings()
