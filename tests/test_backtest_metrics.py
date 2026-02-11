from __future__ import annotations

from ai_trading.backtest.metrics import (
    compute_segment_metrics,
    compute_summary_metrics,
    evaluate_go_no_go,
)
from ai_trading.backtest.types import EquityPoint, ExperimentResult, SegmentSpec, TradeRecord


def test_compute_summary_metrics_fields() -> None:
    equity = [
        EquityPoint(timestamp="2024-01-01T00:00:00+00:00", equity=10_000.0, regime="UP"),
        EquityPoint(timestamp="2024-01-02T00:00:00+00:00", equity=9_800.0, regime="UP"),
        EquityPoint(timestamp="2024-01-03T00:00:00+00:00", equity=10_200.0, regime="UP"),
    ]
    trades = [
        TradeRecord(
            mode="baseline",
            symbol="BTCUSDT",
            opened_at="2024-01-01T00:00:00+00:00",
            closed_at="2024-01-02T00:00:00+00:00",
            close_reason="stop_loss",
            qty=1.0,
            entry_price=10_000.0,
            exit_price=9_800.0,
            stop_loss=9_850.0,
            pnl=-200.0,
            pnl_pct=-2.0,
            ai_decision="ALLOW",
            ai_confidence=1.0,
        ),
        TradeRecord(
            mode="baseline",
            symbol="BTCUSDT",
            opened_at="2024-01-02T00:00:00+00:00",
            closed_at="2024-01-03T00:00:00+00:00",
            close_reason="time_stop",
            qty=1.0,
            entry_price=9_900.0,
            exit_price=10_300.0,
            stop_loss=9_700.0,
            pnl=400.0,
            pnl_pct=4.04,
            ai_decision="ALLOW",
            ai_confidence=1.0,
        ),
    ]
    metrics = compute_summary_metrics(equity, trades)
    assert int(metrics["trade_count"]) == 2
    assert float(metrics["max_drawdown_pct"]) >= 0.0
    assert metrics["max_drawdown_recovery_bars"] is not None


def test_compute_segment_metrics_and_go_no_go() -> None:
    baseline = ExperimentResult(mode="baseline")
    ai = ExperimentResult(mode="ai_filter_sizing")
    baseline.equity_curve = [
        EquityPoint(timestamp="2024-01-01T00:00:00+00:00", equity=10_000.0, regime="UP"),
        EquityPoint(timestamp="2024-01-02T00:00:00+00:00", equity=9_600.0, regime="UP"),
        EquityPoint(timestamp="2024-01-03T00:00:00+00:00", equity=9_900.0, regime="UP"),
    ]
    ai.equity_curve = [
        EquityPoint(timestamp="2024-01-01T00:00:00+00:00", equity=10_000.0, regime="UP"),
        EquityPoint(timestamp="2024-01-02T00:00:00+00:00", equity=9_800.0, regime="UP"),
        EquityPoint(timestamp="2024-01-03T00:00:00+00:00", equity=10_100.0, regime="UP"),
    ]
    baseline.trades = []
    ai.trades = []
    segments = [
        SegmentSpec(
            name="trend_window",
            start_at="2024-01-01T00:00:00+00:00",
            end_at="2024-01-02T12:00:00+00:00",
        ),
        SegmentSpec(
            name="range_window",
            start_at="2024-01-02T12:00:00+00:00",
            end_at="2024-01-03T00:00:00+00:00",
        ),
    ]
    baseline.segment_metrics = compute_segment_metrics(
        baseline.equity_curve,
        baseline.trades,
        segments,
    )
    ai.segment_metrics = compute_segment_metrics(ai.equity_curve, ai.trades, segments)
    baseline.metrics = compute_summary_metrics(baseline.equity_curve, baseline.trades)
    ai.metrics = compute_summary_metrics(ai.equity_curve, ai.trades)

    gate = evaluate_go_no_go({"baseline": baseline, "ai_filter_sizing": ai})
    assert "go" in gate
    assert "checks" in gate
