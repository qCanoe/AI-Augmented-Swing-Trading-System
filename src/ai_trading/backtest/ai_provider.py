"""AI decision providers used by backtests."""

from __future__ import annotations

from typing import Protocol

from ai_trading.ai.openrouter_client import OpenRouterClient
from ai_trading.ai.schemas import LLMDecision, MarketSnapshot
from ai_trading.config import Settings


class AIDecisionProvider(Protocol):
    """Provider interface for AI backtest decisions."""

    def evaluate(self, snapshot: MarketSnapshot) -> LLMDecision:
        """Return one strict decision for the given snapshot."""


class OpenRouterDecisionProvider:
    """Production provider backed by OpenRouter."""

    def __init__(self, settings: Settings) -> None:
        self._client = OpenRouterClient(settings)

    def evaluate(self, snapshot: MarketSnapshot) -> LLMDecision:
        return self._client.evaluate(snapshot)


class HeuristicDecisionProvider:
    """Deterministic fallback provider for reproducible offline backtests."""

    def evaluate(self, snapshot: MarketSnapshot) -> LLMDecision:
        if snapshot.event_risk == "YES":
            return LLMDecision(
                decision="DENY",
                confidence=0.0,
                risk_flags=["EVENT"],
                key_reasons=["macro_event_window"],
            )
        if snapshot.atr_label == "HIGH":
            return LLMDecision(
                decision="REDUCE",
                confidence=0.5,
                risk_flags=["VOLATILE"],
                key_reasons=["atr_high"],
            )
        if (
            snapshot.funding_available
            and snapshot.funding_rate is not None
            and snapshot.funding_rate > 0.01
        ):
            return LLMDecision(
                decision="REDUCE",
                confidence=0.6,
                risk_flags=["CROWDING"],
                key_reasons=["funding_extreme_positive"],
            )
        return LLMDecision(
            decision="ALLOW",
            confidence=0.85,
            risk_flags=[],
            key_reasons=["regime_supportive"],
        )
