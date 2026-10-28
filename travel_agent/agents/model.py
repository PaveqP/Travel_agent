import logging
import time
from typing import Any
from uuid import UUID

import httpx
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.messages.utils import count_tokens_approximately
from langchain_core.outputs import LLMResult
from langchain_openai import ChatOpenAI

from travel_agent.config import Settings


class UsageLogger(AsyncCallbackHandler):
    def __init__(self) -> None:
        self.started: dict[UUID, float] = {}

    async def on_chat_model_start(self, serialized: dict[str, Any], messages: list[list[BaseMessage]], *,
                                  run_id: UUID, metadata: dict[str, Any] | None = None, **kwargs: Any) -> None:
        self.started[run_id] = time.monotonic()
        logging.getLogger(__name__).info('request=%s thread=%s role=%s estimated_input_tokens=%s',
            run_id, (metadata or {}).get('thread_id'), (metadata or {}).get('role'),
            sum(count_tokens_approximately(batch, tools=kwargs.get('invocation_params', {}).get('tools')) for batch in messages))

    async def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        started = self.started.pop(run_id, time.monotonic())
        logging.getLogger(__name__).info('request=%s llm_duration_ms=%s outcome=ok', run_id, round((time.monotonic() - started) * 1000))
        for batch in response.generations:
            for generation in batch:
                usage = getattr(getattr(generation, 'message', None), 'usage_metadata', None)
                if usage:
                    logging.getLogger(__name__).info('request=%s input_tokens=%s output_tokens=%s total_tokens=%s',
                        run_id, usage.get('input_tokens'), usage.get('output_tokens'), usage.get('total_tokens'))

    async def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        started = self.started.pop(run_id, time.monotonic())
        logging.getLogger(__name__).warning('request=%s llm_duration_ms=%s outcome=%s', run_id, round((time.monotonic() - started) * 1000), type(error).__name__)


def create_model(
    config: Settings, client: httpx.AsyncClient, *, max_tokens: int = 1800, timeout: float = 45,
    role: str = 'unspecified',
) -> ChatOpenAI:
    return ChatOpenAI(
        model=config.model,
        api_key=config.token.get_secret_value(),
        base_url=config.base_url,
        http_async_client=client,
        max_retries=0,
        timeout=timeout,
        max_tokens=max_tokens,
        use_responses_api=False,
        callbacks=[UsageLogger()],
        metadata={'role': role},
    )
