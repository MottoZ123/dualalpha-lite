"""Robust OpenAI-compatible chat-completions client shared by all scripts."""

from __future__ import annotations

import random
import time
from typing import Any

import requests

from .config import ProviderConfig


class LLMError(RuntimeError):
    pass


def _completion_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith(("/v1", "/v3", "/api/v3")):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def chat_completion_text(
    config: ProviderConfig,
    messages: list[dict[str, Any]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 4000,
    max_retries: int | None = None,
    timeout_seconds: int | None = None,
    extra_payload: dict[str, Any] | None = None,
    session: Any = requests,
) -> str:
    config.validate()
    attempts = max(1, max_retries if max_retries is not None else config.max_retries)
    timeout = timeout_seconds or config.timeout_seconds
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if config.name == "deepseek" and config.model.startswith("deepseek-v4-"):
        payload["thinking"] = {"type": config.thinking_mode or "enabled"}
        payload["reasoning_effort"] = config.reasoning_effort or "high"
    if extra_payload:
        payload.update(extra_payload)
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}

    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            response = session.post(
                _completion_url(config.base_url),
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            if response.status_code >= 400:
                body = (response.text or "")[:300]
                error = LLMError(f"{config.name} HTTP {response.status_code}: {body}")
                if response.status_code not in {408, 409, 425, 429} and response.status_code < 500:
                    raise error
                last_error = error
            else:
                data = response.json()
                choices = data.get("choices") or []
                if not choices:
                    raise LLMError(f"{config.name} 返回缺少 choices")
                content = (choices[0].get("message") or {}).get("content")
                if content is None:
                    raise LLMError(f"{config.name} 返回缺少 message.content")
                if isinstance(content, list):
                    content = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
                text = str(content).strip()
                if not text:
                    raise LLMError(f"{config.name} 返回空白 message.content")
                return text
        except (requests.RequestException, ValueError, KeyError, TypeError, LLMError) as exc:
            last_error = exc
            if isinstance(exc, LLMError) and "HTTP 4" in str(exc) and not any(code in str(exc) for code in ("408", "409", "425", "429")):
                raise
        if attempt + 1 < attempts:
            time.sleep(min(2 ** attempt + random.uniform(0, 0.3), 8.0))
    raise LLMError(f"{config.name} 调用失败（{attempts} 次尝试）：{last_error}")
