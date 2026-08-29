"""LLM factory — swap between OpenAI and AWS Bedrock with one env var.

This abstraction is a deliberate portfolio talking point: the agent logic is
provider-agnostic, so migrating an enterprise workload from OpenAI to Bedrock
(for data-residency or procurement reasons) is a config change, not a rewrite.
"""
from langchain_core.language_models.chat_models import BaseChatModel

from argus.config import settings


def get_llm() -> BaseChatModel:
    if settings.llm_provider.lower() == "bedrock":
        from langchain_aws import ChatBedrockConverse

        return ChatBedrockConverse(
            model=settings.bedrock_model_id,
            region_name=settings.aws_region,
            provider="anthropic",
            temperature=0,
        )

    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
