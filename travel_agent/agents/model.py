import httpx
from urllib.parse import urlparse
from langchain_openai import ChatOpenAI

from travel_agent.config import Settings


def create_model(
    config: Settings, client: httpx.AsyncClient, *, max_tokens: int = 1800
) -> ChatOpenAI:
    return ChatOpenAI(
        model=config.model,
        api_key=config.token.get_secret_value(),
        base_url=config.base_url,
        http_async_client=client,
        max_retries=0,
        timeout=config.deadline,
        max_tokens=max_tokens,
        use_responses_api=False,
        extra_body={"reasoning": {"effort": "none"}} if urlparse(config.base_url).hostname == "polza.ai" else None,
    )
