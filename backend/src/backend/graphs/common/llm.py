"""Chat model client and prompt loader. Provider is set by LLM_PROVIDER (openai | groq)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from backend.config import get_settings


@lru_cache
def get_chat_llm(temperature: float = 0.0) -> BaseChatModel:
    s = get_settings()
    if s.llm_provider == "groq":
        from langchain_groq import ChatGroq
        return ChatGroq(model=s.llm_model, temperature=temperature, api_key=s.groq_api_key,
                        timeout=s.llm_timeout, max_retries=1)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=s.llm_model, temperature=temperature, api_key=s.openai_api_key,
                      timeout=s.llm_timeout, max_retries=1)


def structured(schema, temperature: float = 0.0):
    """LLM that returns an instance of `schema` (a Pydantic model)."""
    method = "json_schema" if get_settings().llm_provider == "openai" else "function_calling"
    return get_chat_llm(temperature).with_structured_output(schema, method=method)


def load_prompt(path: Path) -> str:
    return path.read_text(encoding="utf-8")
