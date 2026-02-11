"""Metrics and reporting rules for backtest experiments."""

from __future__ import annotations

from datetime import datetime
from statistics import fmean
from typing import Iterable, Mapping, Sequence

from ai_trading.backtest.types import EquityPoint, ExperimentResult, SegmentSpec, TradeRecord


def build_default_segments(equity_curve: Sequence[EquityPoint]) -> list[SegmentSpec]:
    """Create two non-overlapping default windows from one equity curve."""
    if len(equity_curve) < 2:
        return []
    mid = len(equity_curve) // 2
    first = SegmentSpec(
        name="window_a",
        start_at=equity_curve[0].timestamp,
        end_at=equity_curve[mid - 1].timestamp if mid > 0 else equity_curve[0].timestamp,
    )
    second = SegmentSpec(
        name="window_b",
        start_at=equity_curve[mid].timestamp,
        end_at=equity_curve[-1].timestamp,
    )
    return [first, second]


def compute_summary_metrics(
    equity_curve: Sequence[EquityPoint],
    trades: Sequence[TradeRecord],
) -> dict[str, float | int | None]:
    """Compute key metrics for one experiment."""
    if not equity_curve:
        return {
            "trade_count": 0,
            "total_return_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_recovery_bars": None,
            "expectancy_per_trade": 0.0,
            "trade_frequency_per_30d": 0.0,
            "win_rate_pct": 0.0,
        }

    values = [point.equity for point in equity_curve]
    start = values[0]
    end = values[-1]
    total_return_pct = ((end / start) - 1.0) * 100 if start > 0 else 0.0

    max_drawdown_pct, recovery_bars = _max_drawdown_with_recovery(values)
    expectancy = fmean(trade.pnl for trade in trades) if trades else 0.0
    win_count = sum(1 for trade in trades if trade.pnl > 0)
    win_rate = (win_count / len(trades) * 100.0) if trades else 0.0

    started_at = _parse_iso(equity_curve[0].timestamp)
    ended_at = _parse_iso(equity_curve[-1].timestamp)
    duration_days = max(1e-9, (ended_at - started_at).total_seconds() / 86400.0)
    frequency_per_30d = len(trades) / duration_days * 30.0

    return {
        "trade_count": len(trades),
        "total_return_pct": float(total_return_pct),
        "max_drawdown_pct": float(max_drawdown_pct),
        "max_drawdown_recovery_bars": recovery_bars,
        "expectancy_per_trade": float(expectancy),
        "trade_frequency_per_30d": float(frequency_per_30d),
        "win_rate_pct": float(win_rate),
    }


def compute_segment_metrics(
    equity_curve: Sequence[EquityPoint],
    trades: Sequence[TradeRecord],
    segments: Sequence[SegmentSpec],
) -> dict[str, dict[str, float | int | None]]:
    """Compute metrics for each named segment."""
    output: dict[str, dict[str, float | int | None]] = {}
    for segment in segments:
        start = _parse_iso(segment.start_at)
        end = _parse_iso(segment.end_at)
        segment_equity = [
            point
            for point in equity_curve
            if start <= _parse_iso(point.timestamp) <= end
        ]
        segment_trades = [
            trade for trade in trades if start <= _parse_iso(trade.closed_at) <= end
        ]
        output[segment.name] = compute_summary_metrics(segment_equity, segment_trades)
    return output


def evaluate_go_no_go(
    experiments: Mapping[str, ExperimentResult],
) -> dict[str, object]:
    """Evaluate whether results meet the minimum gate for live implementation."""
    baseline = experiments.get("baseline")
    ai_sizing = experiments.get("ai_filter_sizing")
    ai_filter = experiments.get("ai_filter")
    candidate = ai_sizing or ai_filter

    if baseline is None or candidate is None:
        return {
            "go": False,
            "reason": "missing_baseline_or_ai_results",
            "checks": {},
        }

    baseline_m = baseline.metrics
    ai_m = candidate.metrics

    baseline_dd = _float_metric(baseline_m, "max_drawdown_pct")
    ai_dd = _float_metric(ai_m, "max_drawdown_pct")
    baseline_recovery = _int_metric(baseline_m, "max_drawdown_recovery_bars")
    ai_recovery = _int_metric(ai_m, "max_drawdown_recovery_bars")

    drawdown_improved = ai_dd < baseline_dd or (
        baseline_recovery is not None
        and ai_recovery is not None
        and ai_recovery < baseline_recovery
    )

    baseline_freq = _float_metric(baseline_m, "trade_frequency_per_30d")
    ai_freq = _float_metric(ai_m, "trade_frequency_per_30d")
    frequency_reduced = ai_freq <= baseline_freq

    baseline_expectancy = _float_metric(baseline_m, "expectancy_per_trade")
    ai_expectancy = _float_metric(ai_m, "expectancy_per_trade")
    if baseline_expectancy > 0:
        expectancy_ok = ai_expectancy >= baseline_expectancy * 0.9
    else:
        expectancy_ok = ai_expectancy >= baseline_expectancy

    segment_consistency = _segment_consistency_ok(
        baseline.segment_metrics,
        candidate.segment_metrics,
    )

    checks = {
        "drawdown_or_recovery_improved": drawdown_improved,
        "frequency_reduced": frequency_reduced,
        "expectancy_not_significantly_worse": expectancy_ok,
        "segment_consistency": segment_consistency,
    }
    go = all(checks.values())
    return {
        "go": go,
        "selected_ai_mode": candidate.mode,
        "checks": checks,
    }


def _max_drawdown_with_recovery(values: Sequence[float]) -> tuple[float, int | None]:
    if not values:
        return 0.0, None
    peak_value = values[0]
    peak_idx = 0
    max_dd = 0.0
    trough_idx = 0
    peak_idx_for_max_dd = 0

    for idx, value in enumerate(values):
        if value > peak_value:
            peak_value = value
            peak_idx = idx
        drawdown = 0.0 if peak_value <= 0 else (peak_value - value) / peak_value * 100.0
        if drawdown > max_dd:
            max_dd = drawdown
            trough_idx = idx
            peak_idx_for_max_dd = peak_idx

    if max_dd <= 0:
        return 0.0, 0

    recovery_bars: int | None = None
    target = values[peak_idx_for_max_dd]
    for idx in range(trough_idx + 1, len(values)):
        if values[idx] >= target:
            recovery_bars = idx - trough_idx
            break
    return max_dd, recovery_bars


def _segment_consistency_ok(
    baseline_segments: dict[str, dict[str, float | int | None]],
    ai_segments: dict[str, dict[str, float | int | None]],
) -> bool:
    comparable = sorted(set(baseline_segments) & set(ai_segments))
    if not comparable:
        return False

    improving_count = 0
    for name in comparable:
        base_dd = _float_metric(baseline_segments[name], "max_drawdown_pct")
        ai_dd = _float_metric(ai_segments[name], "max_drawdown_pct")
        if ai_dd <= base_dd:
            improving_count += 1
    return improving_count >= max(1, len(comparable) // 2)


def _float_metric(metrics: dict[str, float | int | None], key: str) -> float:
    value = metrics.get(key)
    if value is None:
        return 0.0
    return float(value)


def _int_metric(metrics: dict[str, float | int | None], key: str) -> int | None:
    value = metrics.get(key)
    if value is None:
        return None
    return int(value)


def _parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)


def trade_records_as_rows(records: Iterable[TradeRecord]) -> list[dict[str, object]]:
    """Convert trade records to serializable row dicts."""
    return [
        {
            "mode": row.mode,
            "symbol": row.symbol,
            "opened_at": row.opened_at,
            "closed_at": row.closed_at,
            "close_reason": row.close_reason,
            "qty": row.qty,
            "entry_price": row.entry_price,
            "exit_price": row.exit_price,
            "stop_loss": row.stop_loss,
            "pnl": row.pnl,
            "pnl_pct": row.pnl_pct,
            "ai_decision": row.ai_decision,
            "ai_confidence": row.ai_confidence,
        }
        for row in records
    ]


def equity_points_as_rows(points: Iterable[EquityPoint]) -> list[dict[str, object]]:
    """Convert equity points to serializable row dicts."""
    return [
        {"timestamp": point.timestamp, "equity": point.equity, "regime": point.regime}
        for point in points
    ]
