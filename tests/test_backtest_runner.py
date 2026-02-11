from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pandas as pd

from ai_trading.ai.schemas import LLMDecision
from ai_trading.backtest.ai_provider import AIDecisionProvider
from ai_trading.backtest.runner import run_backtest_suite, run_single_mode
from ai_trading.backtest.types import BacktestConfig, SegmentSpec
from ai_trading.config import Settings
from ai_trading.types import TradeCandidate


def _build_ohlcv(rows: int, step_hours: int, start_price: float, drift: float) -> pd.DataFrame:
    now = datetime.now(UTC)
    times = [now + timedelta(hours=i * step_hours) for i in range(rows)]
    closes = [start_price + i * drift for i in range(rows)]
    return pd.DataFrame(
        {
            "open_time": times,
            "open": closes,
            "high": [c + 10 for c in closes],
            "low": [c - 10 for c in closes],
            "close": closes,
            "volume": [1000.0 for _ in range(rows)],
            "close_time": [t + timedelta(hours=step_hours) for t in times],
        }
    )


class _AlwaysAllowProvider(AIDecisionProvider):
    def evaluate(self, snapshot: object) -> LLMDecision:
        return LLMDecision(decision="ALLOW", confidence=0.9, risk_flags=[], key_reasons=["ok"])


class _AlwaysDenyProvider(AIDecisionProvider):
    def evaluate(self, snapshot: object) -> LLMDecision:
        return LLMDecision(
            decision="DENY",
            confidence=0.0,
            risk_flags=["TEST_DENY"],
            key_reasons=["deny"],
        )


def _candidate_factory(*args: object, **kwargs: object) -> TradeCandidate:
    indicators = args[0]
    price = float(indicators["price"])  # type: ignore[index]
    atr = float(indicators["atr_14_4h"])  # type: ignore[index]
    return TradeCandidate(
        symbol="BTCUSDT",
        side="LONG",
        entry_price=price,
        atr=atr,
        ema20_4h=float(indicators["ema20_4h"]),  # type: ignore[index]
        ema50_1d=float(indicators["ema50_1d"]),  # type: ignore[index]
        trend="UP",
        funding_rate=None,
        open_interest=None,
        reasons=["forced_candidate"],
        created_at=datetime.now(UTC).isoformat(),
    )


def test_run_single_mode_generates_result_structure(monkeypatch: object) -> None:
    from ai_trading.backtest import runner

    monkeypatch.setattr(runner, "generate_candidate", _candidate_factory)
    df_4h = _build_ohlcv(rows=300, step_hours=4, start_price=30_000, drift=2)
    df_1d = _build_ohlcv(rows=150, step_hours=24, start_price=25_000, drift=20)
    settings = Settings(journal_dir="data/journal")

    result = run_single_mode(
        mode="baseline",
        settings=settings,
        config=BacktestConfig(warmup_4h_bars=80, min_1d_bars=20),
        df_4h=df_4h,
        df_1d=df_1d,
        ai_provider=_AlwaysAllowProvider(),
    )
    assert result.mode == "baseline"
    assert "trade_count" in result.metrics
    assert "max_drawdown_pct" in result.metrics
    assert len(result.decisions) > 0


def test_run_single_mode_ai_filter_denied_has_no_trades(monkeypatch: object) -> None:
    from ai_trading.backtest import runner

    monkeypatch.setattr(runner, "generate_candidate", _candidate_factory)
    df_4h = _build_ohlcv(rows=260, step_hours=4, start_price=30_000, drift=1)
    df_1d = _build_ohlcv(rows=130, step_hours=24, start_price=24_000, drift=15)
    settings = Settings(journal_dir="data/journal")

    result = run_single_mode(
        mode="ai_filter",
        settings=settings,
        config=BacktestConfig(warmup_4h_bars=80, min_1d_bars=20),
        df_4h=df_4h,
        df_1d=df_1d,
        ai_provider=_AlwaysDenyProvider(),
    )
    assert int(result.metrics.get("trade_count", 0)) == 0
    assert len(result.decisions) > 0


def test_backtest_suite_writes_layered_outputs(monkeypatch: object, tmp_path: object) -> None:
    from ai_trading.backtest import runner

    monkeypatch.setattr(runner, "generate_candidate", _candidate_factory)
    df_4h = _build_ohlcv(rows=320, step_hours=4, start_price=32_000, drift=2)
    df_1d = _build_ohlcv(rows=170, step_hours=24, start_price=26_000, drift=25)
    settings = Settings(journal_dir=tmp_path)
    output_dir = tmp_path / "backtest"

    first_time = df_4h.iloc[200]["close_time"].isoformat()
    mid_time = df_4h.iloc[260]["close_time"].isoformat()
    last_time = df_4h.iloc[-1]["close_time"].isoformat()
    segments = [
        SegmentSpec(name="trend_window", start_at=first_time, end_at=mid_time),
        SegmentSpec(name="range_window", start_at=mid_time, end_at=last_time),
    ]

    report = run_backtest_suite(
        settings=settings,
        config=BacktestConfig(warmup_4h_bars=80, min_1d_bars=20),
        df_4h=df_4h,
        df_1d=df_1d,
        ai_provider=_AlwaysAllowProvider(),
        output_dir=output_dir,
        source="test",
        segments=segments,
    )

    assert (output_dir / "summary.json").exists()
    assert (output_dir / "go_no_go.md").exists()
    assert (output_dir / "baseline" / "metrics.json").exists()
    assert (output_dir / "ai_filter" / "metrics.json").exists()
    assert (output_dir / "ai_filter_sizing" / "metrics.json").exists()

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["symbol"] == "BTCUSDT"
    assert "go_no_go" in summary
    assert set(report.experiments.keys()) == {"baseline", "ai_filter", "ai_filter_sizing"}
