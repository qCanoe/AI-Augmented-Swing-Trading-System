"""OpenRouter LLM client."""

from __future__ import annotations

import time
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ai_trading.ai.schemas import LLMDecision, MarketSnapshot
from ai_trading.config import Settings
from ai_trading.utils.logging import get_logger, log_llm_call

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(Exception):
    """Base OpenRouter error."""


class OpenRouterAPIError(OpenRouterError):
    """Raised when API transport/request fails."""


class OpenRouterClient:
    """Thin client for OpenRouter chat completion endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("ai_trading.ai.openrouter_client")

    def evaluate(self, snapshot: MarketSnapshot) -> LLMDecision:
        """Evaluate one market snapshot and return a strict decision."""
        started = time.perf_counter()
        try:
            content = self._request_completion(snapshot)
        except OpenRouterAPIError:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log_llm_call(
                self._logger,
                model=self._settings.openrouter_model,
                success=False,
                latency_ms=elapsed_ms,
                reason="api_error",
            )
            raise

        decision = LLMDecision.parse_response_text(content)
        elapsed_ms = (time.perf_counter() - started) * 1000
        success = decision.decision != "DENY" or "INVALID_RESPONSE" not in decision.risk_flags
        log_llm_call(
            self._logger,
            model=self._settings.openrouter_model,
            success=success,
            latency_ms=elapsed_ms,
            decision=decision.decision,
        )
        return decision

    @retry(
        retry=retry_if_exception_type(OpenRouterAPIError),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def _request_completion(self, snapshot: MarketSnapshot) -> str:
        if not self._settings.openrouter_api_key:
            raise OpenRouterAPIError("missing_openrouter_api_key")

        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._settings.openrouter_model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a risk gatekeeper. Return only JSON with keys: "
                        "decision, confidence, risk_flags, key_reasons."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Evaluate this candidate for 3-7 day swing. "
                        f"Snapshot: {snapshot.model_dump_json()}"
                    ),
                },
            ],
        }

        try:
            with httpx.Client(timeout=self._settings.openrouter_timeout) as client:
                response = client.post(_OPENROUTER_URL, headers=headers, json=payload)
                response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise OpenRouterAPIError(str(exc)) from exc

        return _extract_message_content(response.json())


def _extract_message_content(payload: dict[str, Any]) -> str:
    """Read assistant content from OpenRouter response payload."""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return "{}"
    first = choices[0]
    if not isinstance(first, dict):
        return "{}"
    message = first.get("message")
    if not isinstance(message, dict):
        return "{}"
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "{}"
