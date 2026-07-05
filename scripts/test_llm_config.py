"""Diagnostic script to verify LLM provider configuration.

Run from the project root:

    python scripts/test_llm_config.py

It reads the current OptiMind settings and probes the most likely endpoints
for both OpenAI-compatible and Anthropic-compatible providers.
"""

from __future__ import annotations

from typing import Any

import requests

from opti_mind.config import get_settings


def _mask_key(key: str) -> str:
    if not key:
        return "(empty)"
    if len(key) <= 8:
        return "***"
    return f"{key[:3]}...{key[-4:]}"


def _try_openai(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    """Probe an OpenAI-compatible /chat/completions endpoint."""
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hello"}],
        "temperature": 0.1,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        return {
            "url": url,
            "status": response.status_code,
            "text": response.text[:500],
        }
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "status": None, "error": str(exc)}


def _try_anthropic(base_url: str, api_key: str, model: str) -> dict[str, Any]:
    """Probe an Anthropic-compatible /v1/messages endpoint."""
    url = base_url.rstrip("/") + "/v1/messages"
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "hello"}],
        "max_tokens": 1024,
        "temperature": 0.1,
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        return {
            "url": url,
            "status": response.status_code,
            "text": response.text[:500],
        }
    except Exception as exc:  # noqa: BLE001
        return {"url": url, "status": None, "error": str(exc)}


def main() -> None:
    settings = get_settings()

    print("Current OptiMind LLM settings:")
    print(f"  provider: {settings.llm_provider}")
    print(f"  model:    {settings.llm_model}")
    print(f"  base_url: {settings.llm_base_url or '(default)'}")
    print(f"  api_key:  {_mask_key(settings.llm_api_key)}")
    print()

    base_url = settings.llm_base_url or ""
    if not base_url:
        print("ERROR: llm_base_url is empty. Please set OPTI_MIND_LLM_BASE_URL.")
        return

    print(f"Probing OpenAI-compatible endpoint with model={settings.llm_model}...")
    openai_result = _try_openai(base_url, settings.llm_api_key, settings.llm_model)
    print(f"  URL:    {openai_result['url']}")
    print(f"  Status: {openai_result.get('status')}")
    if "error" in openai_result:
        print(f"  Error:  {openai_result['error']}")
    else:
        print(f"  Body:   {openai_result['text']}")
    print()

    print(f"Probing Anthropic-compatible endpoint with model={settings.llm_model}...")
    anthropic_result = _try_anthropic(
        base_url, settings.llm_api_key, settings.llm_model
    )
    print(f"  URL:    {anthropic_result['url']}")
    print(f"  Status: {anthropic_result.get('status')}")
    if "error" in anthropic_result:
        print(f"  Error:  {anthropic_result['error']}")
    else:
        print(f"  Body:   {anthropic_result['text']}")
    print()

    if openai_result.get("status") == 200:
        print("Result: use OPTI_MIND_LLM_PROVIDER=openai (or kimi)")
    elif anthropic_result.get("status") == 200:
        print("Result: use OPTI_MIND_LLM_PROVIDER=anthropic")
    else:
        print("Result: neither OpenAI nor Anthropic endpoint returned 200.")
        print("Check your base_url, api_key, and model name.")


if __name__ == "__main__":
    main()
