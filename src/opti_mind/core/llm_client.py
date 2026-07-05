"""Pluggable LLM client layer for OptiMind.

This module defines the ILLMClient protocol and concrete adapters for common
providers (OpenAI, Kimi, Ollama). New providers can be added by implementing
ILLMClient and registering them in create_llm_client().
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Protocol, cast, runtime_checkable

from pydantic import BaseModel, Field, SecretStr

from opti_mind.config import Settings, get_settings


class LLMResponse(BaseModel):
    """Normalized response from any LLM provider."""

    content: str
    model: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class ILLMClient(Protocol):
    """Contract for a pluggable LLM client."""

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        """Send a chat request and return the normalized response.

        Args:
            messages: List of {"role": "system|user|assistant", "content": "..."}.
            **kwargs: Provider-specific options.

        Returns:
            Normalized LLMResponse.
        """
        ...


class OpenAILLMClient:
    """OpenAI-compatible LLM client (OpenAI, Kimi, Azure, etc.)."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        temperature: float = 0.1,
        timeout: float | None = None,
    ) -> None:
        from langchain_openai import ChatOpenAI

        self._model = model
        # ChatOpenAI expects a SecretStr; pass the raw key, it will wrap it.
        self._client = ChatOpenAI(
            model=model,
            api_key=SecretStr(api_key),
            base_url=base_url,
            temperature=temperature,
            timeout=timeout,
        )

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        response = self._client.invoke(messages, **kwargs)
        return LLMResponse(content=str(response.content), model=self._model)


class OllamaLLMClient:
    """Local LLM client via Ollama API."""

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        timeout: float | None = None,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        import requests

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self.temperature},
        }
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.timeout,
            **kwargs,
        )
        response.raise_for_status()
        data = response.json()
        return LLMResponse(content=data["message"]["content"], model=self.model)


class AnthropicLLMClient:
    """Anthropic API-compatible client (also works with Anthropic-compatible
    proxies such as the Kimi coding endpoint).
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str | None = None,
        temperature: float = 0.1,
        timeout: float | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "The 'anthropic' package is required for the anthropic provider. "
                "Install it with: pip install anthropic"
            ) from exc

        self.model = model
        self.temperature = temperature
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        if timeout:
            client_kwargs["timeout"] = timeout
        self._client = anthropic.Anthropic(**client_kwargs)

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> LLMResponse:
        system_prompt: str | None = None
        chat_messages: list[dict[str, str]] = []
        for message in messages:
            if message["role"] == "system":
                system_prompt = message["content"]
            else:
                chat_messages.append({"role": message["role"], "content": message["content"]})

        response = self._client.messages.create(
            model=self.model,
            messages=cast(Any, chat_messages),
            system=cast(Any, system_prompt),
            temperature=self.temperature,
            max_tokens=kwargs.pop("max_tokens", 4096),
            **kwargs,
        )
        content = "".join(
            cast(Any, block).text
            for block in response.content
            if getattr(block, "type", None) == "text"
        )
        return LLMResponse(content=content, model=self.model)


def _build_client(provider: str, settings: Settings) -> ILLMClient:
    """Build a concrete client for the given provider from settings."""
    if provider == "openai":
        base_url = settings.llm_base_url or "https://api.openai.com/v1"
        if not settings.llm_api_key:
            raise ValueError("LLM provider 'openai' requires an API key.")
        return OpenAILLMClient(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=base_url,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
        )

    if provider == "kimi":
        base_url = settings.llm_base_url or "https://api.moonshot.cn/v1"
        if not settings.llm_api_key:
            raise ValueError("LLM provider 'kimi' requires an API key.")
        return OpenAILLMClient(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=base_url,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
        )

    if provider == "ollama":
        base_url = settings.llm_base_url or "http://localhost:11434"
        return OllamaLLMClient(
            model=settings.llm_model,
            base_url=base_url,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
        )

    if provider == "anthropic":
        base_url = settings.llm_base_url or "https://api.anthropic.com"
        if not settings.llm_api_key:
            raise ValueError("LLM provider 'anthropic' requires an API key.")
        return AnthropicLLMClient(
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            base_url=base_url,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout,
        )

    raise ValueError(
        f"Unknown LLM provider: {provider}. Supported: openai, kimi, ollama, anthropic."
    )


@lru_cache(maxsize=1)
def _cached_client() -> ILLMClient:
    """Return the shared singleton LLM client (cached for the process)."""
    settings = get_settings()
    return _build_client(settings.llm_provider, settings)


def create_llm_client(provider: str | None = None) -> ILLMClient:
    """Create or return the shared LLM client.

    A single cached instance is reused across all layers (data, modeling,
    decision) to avoid repeated initialization and to reuse HTTP connections.

    Args:
        provider: Optional provider name. If omitted, read from settings.

    Returns:
        An ILLMClient implementation.

    Raises:
        ValueError: If the provider is unknown or misconfigured.
    """
    settings = get_settings()
    if provider is None or provider == settings.llm_provider:
        return _cached_client()
    return _build_client(provider, settings)


def reset_llm_client_cache() -> None:
    """Clear the cached client (used by tests that override settings)."""
    _cached_client.cache_clear()
