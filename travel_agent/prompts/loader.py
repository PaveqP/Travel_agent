from functools import lru_cache
from pathlib import Path
from typing import Literal

PromptName = Literal[
    "supervisor", "transport", "stays", "experience", "response", "research", "request", "planner"
]
PROMPT_NAMES = (
    "supervisor",
    "transport",
    "stays",
    "experience",
    "response",
    "research",
    "request",
    "planner",
)


@lru_cache(maxsize=8)
def load_prompt(name: PromptName) -> str:
    if name not in PROMPT_NAMES:
        raise ValueError("Unknown agent prompt")
    text = (Path(__file__).parent / f"{name}.md").read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Empty prompt: {name}")
    return text


def read_prompts() -> dict[str, str]:
    return {name: load_prompt(name) for name in PROMPT_NAMES}
