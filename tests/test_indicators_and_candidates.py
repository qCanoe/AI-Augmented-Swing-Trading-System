from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from ai_trading.config import Settings
from ai_trading.features.indicators import classify_trend, compute_indicators
from ai_trading.strategy.candidates import generate_candidate


def _build_ohlcv(rows: int, step_hours: int, start_price: float, drift: float) -> pd.DataFrame:
    now = datetime.now(UTC)
    times = [now + timedelta(hours=i * step_hours) for i in range(rows)]
    closes = [start_price + i * drift for i in range(rows)]
    data = {
        "open_time": times,
        "open": closes,
        "high": [c + 20 for c in closes],
        "low": [c - 20 for c in closes],
        "close": closes,
        "volume": [1000.0 for _ in range(rows)],
        "close_time": [t + timedelta(hours=step_hours) for t in times],
    }
    return pd.DataFrame(data)


def test_compute_indicators_and_trend_up() -> None:
    df_4h = _build_ohlcv(rows=450, step_hours=4, start_price=40_000, drift=3)
    df_1d = _build_ohlcv(rows=320, step_hours=24, start_price=30_000, drift=30)
    trend = classify_trend(df_1d)
    indicators = compute_indicators(df_4h, df_1d)
    assert trend == "UP"
    assert indicators["trend"] == "UP"
    assert float(indicators["atr_14_4h"]) > 0


def test_generate_candidate_respects_mvp_rules() -> None:
    settings = Settings(journal_dir="data/journal")
    indicators = {
        "price": 50_000.0,
        "ema20_4h": 49_980.0,
        "ema50_1d": 48_000.0,
        "atr_14_4h": 120.0,
        "atr_quantile": 0.5,
        "distance_to_ema20_atr": 0.16,
        "trend": "UP",
    }
    candidate = generate_candidate(indicators, settings, funding_rate=0.001, open_interest=100.0)
    assert candidate is not None
    assert candidate.symbol == "BTCUSDT"
    assert candidate.side == "LONG"


def test_generate_candidate_returns_none_for_non_up_trend() -> None:
    settings = Settings(journal_dir="data/journal")
    indicators = {
        "price": 50_000.0,
        "ema20_4h": 49_980.0,
        "ema50_1d": 48_000.0,
        "atr_14_4h": 120.0,
        "atr_quantile": 0.5,
        "distance_to_ema20_atr": 0.16,
        "trend": "DOWN",
    }
    assert generate_candidate(indicators, settings) is None
