from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from ai_trading.ai.openrouter_client import OpenRouterAPIError
from ai_trading.ai.schemas import LLMDecision
from ai_trading.config import Settings
from ai_trading.pipeline import run_trading_cycle
from ai_trading.types import TradeCandidate


def _build_ohlcv(rows: int, step_hours: int, start_price: float, drift: float) -> pd.DataFrame:
    now = datetime.now(UTC)
    times = [now + timedelta(hours=i * step_hours) for i in range(rows)]
    closes = [start_price + i * drift for i in range(rows)]
    return pd.DataFrame(
        {
            "open_time": times,
            "open": closes,
            "high": [c + 20 for c in closes],
            "low": [c - 20 for c in closes],
            "close": closes,
            "volume": [1000.0 for _ in range(rows)],
            "close_time": [t + timedelta(hours=step_hours) for t in times],
        }
    )


class _FakeBinanceDataClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def fetch_ohlcv(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        if interval == "4h":
            return _build_ohlcv(rows=450, step_hours=4, start_price=40_000, drift=3)
        return _build_ohlcv(rows=320, step_hours=24, start_price=30_000, drift=30)

    def fetch_funding_rate(self, symbol: str) -> float | None:
        return 0.001

    def fetch_open_interest(self, symbol: str) -> float | None:
        return 1234.5


class _FakeOpenRouterAllow:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(self, snapshot: object) -> LLMDecision:
        return LLMDecision(
            decision="ALLOW",
            confidence=0.8,
            risk_flags=[],
            key_reasons=["looks good"],
        )


class _FakeOpenRouterError:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def evaluate(self, snapshot: object) -> LLMDecision:
        raise OpenRouterAPIError("timeout")


def test_pipeline_allow_path(monkeypatch: object, tmp_path: object) -> None:
    from ai_trading import pipeline

    monkeypatch.setattr(pipeline, "BinanceDataClient", _FakeBinanceDataClient)
    monkeypatch.setattr(pipeline, "OpenRouterClient", _FakeOpenRouterAllow)
    monkeypatch.setattr(
        pipeline,
        "generate_candidate",
        lambda *args, **kwargs: TradeCandidate(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=50_000.0,
            atr=120.0,
            ema20_4h=49_980.0,
            ema50_1d=48_000.0,
            trend="UP",
            funding_rate=0.001,
            open_interest=1234.5,
            reasons=["test_candidate"],
            created_at=datetime.now(UTC).isoformat(),
        ),
    )

    settings = Settings(journal_dir=tmp_path)
    result = run_trading_cycle(settings, dry_run=True)
    assert result.status == "opened_dry_run"
    assert len(result.orders) == 1


def test_pipeline_ai_degrade_path(monkeypatch: object, tmp_path: object) -> None:
    from ai_trading import pipeline

    monkeypatch.setattr(pipeline, "BinanceDataClient", _FakeBinanceDataClient)
    monkeypatch.setattr(pipeline, "OpenRouterClient", _FakeOpenRouterError)
    monkeypatch.setattr(
        pipeline,
        "generate_candidate",
        lambda *args, **kwargs: TradeCandidate(
            symbol="BTCUSDT",
            side="LONG",
            entry_price=50_000.0,
            atr=120.0,
            ema20_4h=49_980.0,
            ema50_1d=48_000.0,
            trend="UP",
            funding_rate=0.001,
            open_interest=1234.5,
            reasons=["test_candidate"],
            created_at=datetime.now(UTC).isoformat(),
        ),
    )

    settings = Settings(journal_dir=tmp_path)
    result = run_trading_cycle(settings, dry_run=True)
    assert result.status == "opened_dry_run"
    assert "ai_unavailable_fallback_to_rules" in result.warnings
