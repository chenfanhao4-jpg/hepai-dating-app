"""Minimal server-side Alibaba Cloud Bailian Chat Completions client.

This module deliberately has no browser-facing key handling. Call it only from
an authenticated backend after memory consent and content-safety checks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx


class BailianConfigurationError(RuntimeError):
    pass


class BailianServiceError(RuntimeError):
    pass


@dataclass(frozen=True)
class BailianConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float = 60.0

    @classmethod
    def from_env(cls) -> "BailianConfig":
        base_url = os.getenv("BAILIAN_BASE_URL", "").strip().rstrip("/")
        api_key = os.getenv("BAILIAN_API_KEY", "").strip()
        model = os.getenv("BAILIAN_MODEL", "qwen-flash").strip()
        timeout = os.getenv("BAILIAN_TIMEOUT_SECONDS", "60").strip()
        if not base_url or "YOUR_WORKSPACE_ID" in base_url:
            raise BailianConfigurationError("BAILIAN_BASE_URL is not configured")
        if not api_key or api_key == "replace_with_server_side_secret":
            raise BailianConfigurationError("BAILIAN_API_KEY is not configured")
        try:
            timeout_seconds = float(timeout)
        except ValueError as exc:
            raise BailianConfigurationError("BAILIAN_TIMEOUT_SECONDS must be numeric") from exc
        if timeout_seconds < 5 or timeout_seconds > 180:
            raise BailianConfigurationError("BAILIAN_TIMEOUT_SECONDS must be between 5 and 180")
        return cls(base_url, api_key, model, timeout_seconds)


async def chat_completion(
    messages: list[dict[str, str]],
    *,
    max_tokens: int = 900,
    temperature: float = 0.5,
) -> str:
    """Send one chat request and return only its user-facing answer.

    Do not pass another user's messages or an unbounded transcript. The caller
    must build a minimized context from the authenticated user's permitted data.
    """
    config = BailianConfig.from_env()
    if not messages:
        raise ValueError("messages must not be empty")
    if max_tokens < 1 or max_tokens > 4096:
        raise ValueError("max_tokens must be between 1 and 4096")

    url = f"{config.base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as exc:
        raise BailianServiceError("模型服务响应超时，请稍后重试") from exc
    except httpx.HTTPStatusError as exc:
        # Do not include upstream response bodies: they may echo user content.
        raise BailianServiceError(f"模型服务返回 HTTP {exc.response.status_code}") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise BailianServiceError("无法连接模型服务") from exc

    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise BailianServiceError("模型服务返回格式不完整") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise BailianServiceError("模型服务没有返回文本")
    return answer.strip()
