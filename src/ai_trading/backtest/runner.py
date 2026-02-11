"""Backtest runner for BTC-only phase-1 experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Mapping, cast

import pandas as pd  # type: ignore[import-untyped]

from ai_trading.ai.openrouter_client import OpenRouterAPIError
from ai_trading.ai.schemas import LLMDecision, MarketSnapshot
from ai_trading.backtest.ai_provider import AIDecisionProvider
from ai_trading.backtest.metrics import (
    build_default_segments,
    compute_segment_metrics,
    compute_summary_metrics,
    equity_points_as_rows,
    evaluate_go_no_go,
    trade_records_as_rows,
)
from ai_trading.backtest.types import (
    BacktestConfig,
    BacktestReport,
    EquityPoint,
    ExperimentMode,
    ExperimentResult,
    SegmentSpec,
    TradeRecord,
)
from ai_trading.config import Settings
from ai_trading.features.indicators import compute_indicators
from ai_trading.risk.rules import RiskEngine
from ai_trading.strategy.candidates import generate_candidate

if TYPE_CHECKING:
    from ai_trading.types import PositionState

_EXPERIMENT_MODES: tuple[ExperimentMode, ...] = (
    "baseline",
    "ai_filter",
    "ai_filter_sizing",
)


@dataclass(slots=True)
class _OpenPosition:
    symbol: str
    qty: float
    entry_price: float
    stop_loss: float
    opened_at: str
    ai_decision: str
    ai_confidence: float


def run_backtest_suite(
    *,
    settings: Settings,
    config: BacktestConfig,
    df_4h: pd.DataFrame,
    df_1d: pd.DataFrame,
    ai_provider: AIDecisionProvider,
    output_dir: Path,
    source: str,
    segments: list[SegmentSpec] | None = None,
) -> BacktestReport:
    """Run baseline + AI modes and write layered artifacts."""
    experiments: dict[ExperimentMode, ExperimentResult] = {}
    for mode in _EXPERIMENT_MODES:
        experiments[mode] = run_single_mode(
            mode=mode,
            settings=settings,
            config=config,
            df_4h=df_4h,
            df_1d=df_1d,
            ai_provider=ai_provider,
        )

    if segments is None:
        segments = build_default_segments(experiments["baseline"].equity_curve)

    for result in experiments.values():
        result.segment_metrics = compute_segment_metrics(
            result.equity_curve,
            result.trades,
            segments,
        )

    go_no_go = evaluate_go_no_go({mode: result for mode, result in experiments.items()})
    report = BacktestReport(
        symbol=config.symbol,
        started_at=datetime.now(timezone.utc).isoformat(),
        source=source,
        segments=segments,
        experiments=experiments,
        go_no_go=go_no_go,
    )
    write_backtest_artifacts(output_dir=output_dir, report=report)
    return report


def run_single_mode(
    *,
    mode: ExperimentMode,
    settings: Settings,
    config: BacktestConfig,
    df_4h: pd.DataFrame,
    df_1d: pd.DataFrame,
    ai_provider: AIDecisionProvider,
) -> ExperimentResult:
    """Run one experiment mode over the same historical data."""
    if config.warmup_4h_bars <= 0:
        raise ValueError("warmup_4h_bars_must_be_positive")
    if len(df_4h) <= config.warmup_4h_bars:
        raise ValueError("insufficient_4h_bars_for_warmup")

    risk_engine = RiskEngine(settings)
    result = ExperimentResult(mode=mode)

    equity = config.initial_equity
    week_start_equity = equity
    week_id: int | None = None
    consecutive_losses = 0
    position: _OpenPosition | None = None
    slippage = config.slippage_bps / 10_000.0

    for idx in range(config.warmup_4h_bars, len(df_4h)):
        current_row = df_4h.iloc[idx]
        now = _to_utc_iso(current_row["close_time"])
        current_week_id = datetime.fromisoformat(now).isocalendar()[1]
        if week_id is None:
            week_id = current_week_id
        elif current_week_id != week_id:
            week_start_equity = equity
            week_id = current_week_id

        bars_4h = df_4h.iloc[: idx + 1]
        bars_1d = df_1d[df_1d["close_time"] <= current_row["close_time"]]
        if len(bars_1d) < config.min_1d_bars:
            continue

        try:
            indicators = compute_indicators(bars_4h, bars_1d)
        except ValueError as exc:
            result.warnings.append(f"indicator_error:{exc}")
            continue

        regime = str(indicators["trend"])
        close_price = float(current_row["close"])
        low_price = float(current_row["low"])

        if position is not None:
            closed = _try_close_open_position(
                result=result,
                position=position,
                now=now,
                close_price=close_price,
                low_price=low_price,
                slippage=slippage,
                risk_engine=risk_engine,
                max_holding_days=settings.max_holding_days,
            )
            if closed is not None:
                realized_pnl = closed["pnl"]
                equity += realized_pnl
                consecutive_losses = consecutive_losses + 1 if realized_pnl < 0 else 0
                position = None
                result.equity_curve.append(EquityPoint(timestamp=now, equity=equity, regime=regime))
                continue

            unrealized = (close_price - position.entry_price) * position.qty
            result.equity_curve.append(
                EquityPoint(timestamp=now, equity=equity + unrealized, regime=regime)
            )
            continue

        result.equity_curve.append(EquityPoint(timestamp=now, equity=equity, regime=regime))
        candidate = generate_candidate(indicators, settings, funding_rate=None, open_interest=None)
        if candidate is None:
            continue

        snapshot = _build_snapshot(candidate.symbol, candidate.trend, indicators)
        ai_decision = _resolve_ai_decision(mode=mode, ai_provider=ai_provider, snapshot=snapshot)
        result.decisions.append(
            {
                "timestamp": now,
                "mode": mode,
                "decision": ai_decision.decision,
                "confidence": ai_decision.confidence,
                "risk_flags": ai_decision.risk_flags,
            }
        )
        if mode != "baseline" and ai_decision.decision == "DENY":
            continue

        weekly_drawdown_pct = 0.0
        if week_start_equity > 0:
            weekly_drawdown_pct = max(0.0, (week_start_equity - equity) / week_start_equity * 100.0)
        guard_result = risk_engine.check_global_guards(
            {
                "consecutive_losses": consecutive_losses,
                "weekly_drawdown_pct": weekly_drawdown_pct,
                "total_exposure_pct": 0.0,
            }
        )
        if not guard_result.allowed:
            result.warnings.append(f"risk_guard_block:{','.join(guard_result.reasons)}")
            continue

        risk_budget_pct = _resolve_risk_budget(mode, settings.risk_per_trade_pct, ai_decision)
        stop_loss = risk_engine.build_stop_loss(
            candidate.entry_price,
            candidate.atr,
            settings.stop_loss_atr_multiplier,
        )
        qty = risk_engine.compute_position_size(
            equity=equity,
            entry=candidate.entry_price,
            stop=stop_loss,
            risk_budget_pct=risk_budget_pct,
        )
        qty = min(
            qty,
            _max_qty_by_exposure(
                equity=equity,
                entry_price=candidate.entry_price,
                max_exposure_pct=settings.max_total_exposure_pct,
            ),
        )
        if qty <= 0:
            result.warnings.append("qty_zero_after_risk")
            continue

        entry_fill = candidate.entry_price * (1.0 + slippage)
        position = _OpenPosition(
            symbol=candidate.symbol,
            qty=qty,
            entry_price=entry_fill,
            stop_loss=stop_loss,
            opened_at=now,
            ai_decision=ai_decision.decision,
            ai_confidence=ai_decision.confidence,
        )

    if position is not None and len(df_4h) > 0:
        final_row = df_4h.iloc[-1]
        close_time = _to_utc_iso(final_row["close_time"])
        close_price = float(final_row["close"])
        exit_fill = close_price * (1.0 - slippage)
        pnl = (exit_fill - position.entry_price) * position.qty
        equity += pnl
        result.trades.append(
            TradeRecord(
                mode=mode,
                symbol=position.symbol,
                opened_at=position.opened_at,
                closed_at=close_time,
                close_reason="end_of_data",
                qty=position.qty,
                entry_price=position.entry_price,
                exit_price=exit_fill,
                stop_loss=position.stop_loss,
                pnl=pnl,
                pnl_pct=_safe_pct(pnl, position.entry_price * position.qty),
                ai_decision=position.ai_decision,
                ai_confidence=position.ai_confidence,
            )
        )
        result.equity_curve.append(
            EquityPoint(
                timestamp=close_time,
                equity=equity,
                regime=str(result.equity_curve[-1].regime if result.equity_curve else "UNKNOWN"),
            )
        )

    result.metrics = compute_summary_metrics(result.equity_curve, result.trades)
    return result


def write_backtest_artifacts(output_dir: Path, report: BacktestReport) -> None:
    """Persist backtest outputs grouped by mode + segment."""
    output_dir.mkdir(parents=True, exist_ok=True)
    for mode, experiment in report.experiments.items():
        mode_dir = output_dir / mode
        mode_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(trade_records_as_rows(experiment.trades)).to_csv(
            mode_dir / "trades.csv",
            index=False,
        )
        pd.DataFrame(equity_points_as_rows(experiment.equity_curve)).to_csv(
            mode_dir / "equity_curve.csv", index=False
        )
        _write_json(mode_dir / "metrics.json", experiment.metrics)
        _write_json(mode_dir / "segment_metrics.json", experiment.segment_metrics)

    summary = {
        "symbol": report.symbol,
        "started_at": report.started_at,
        "source": report.source,
        "segments": [asdict(segment) for segment in report.segments],
        "experiments": {
            mode: {
                "metrics": experiment.metrics,
                "segment_metrics": experiment.segment_metrics,
                "warnings": experiment.warnings,
            }
            for mode, experiment in report.experiments.items()
        },
        "go_no_go": report.go_no_go,
    }
    _write_json(output_dir / "summary.json", summary)
    _write_go_no_go_markdown(output_dir / "go_no_go.md", summary)


def _try_close_open_position(
    *,
    result: ExperimentResult,
    position: _OpenPosition,
    now: str,
    close_price: float,
    low_price: float,
    slippage: float,
    risk_engine: RiskEngine,
    max_holding_days: int,
) -> dict[str, float] | None:
    reason: str | None = None
    raw_exit_price: float | None = None

    if low_price <= position.stop_loss:
        reason = "stop_loss"
        raw_exit_price = position.stop_loss
    else:
        should_time_stop = risk_engine.check_time_stop(
            position=_to_position_state(position),
            now=datetime.fromisoformat(now),
            max_holding_days=max_holding_days,
        )
        if should_time_stop:
            reason = "time_stop"
            raw_exit_price = close_price

    if reason is None or raw_exit_price is None:
        return None

    exit_fill = raw_exit_price * (1.0 - slippage)
    pnl = (exit_fill - position.entry_price) * position.qty
    result.trades.append(
        TradeRecord(
            mode=result.mode,
            symbol=position.symbol,
            opened_at=position.opened_at,
            closed_at=now,
            close_reason=reason,
            qty=position.qty,
            entry_price=position.entry_price,
            exit_price=exit_fill,
            stop_loss=position.stop_loss,
            pnl=pnl,
            pnl_pct=_safe_pct(pnl, position.entry_price * position.qty),
            ai_decision=position.ai_decision,
            ai_confidence=position.ai_confidence,
        )
    )
    return {"pnl": pnl}


def _resolve_ai_decision(
    *,
    mode: ExperimentMode,
    ai_provider: AIDecisionProvider,
    snapshot: MarketSnapshot,
) -> LLMDecision:
    if mode == "baseline":
        return LLMDecision(
            decision="ALLOW",
            confidence=1.0,
            risk_flags=[],
            key_reasons=["baseline_no_ai"],
        )
    try:
        return ai_provider.evaluate(snapshot)
    except OpenRouterAPIError as exc:
        return LLMDecision(
            decision="ALLOW",
            confidence=0.5,
            risk_flags=["AI_UNAVAILABLE"],
            key_reasons=[f"fallback_to_rules:{exc}"],
        )


def _resolve_risk_budget(mode: ExperimentMode, base: float, decision: LLMDecision) -> float:
    confidence = max(0.0, min(1.0, decision.confidence))
    if mode == "ai_filter_sizing":
        return base * confidence
    return base


def _build_snapshot(
    symbol: str,
    trend: str,
    indicators: dict[str, float | str],
) -> MarketSnapshot:
    atr_quantile = float(indicators["atr_quantile"])
    normalized_trend: Literal["UP", "DOWN", "NEUTRAL"]
    if trend in {"UP", "DOWN", "NEUTRAL"}:
        normalized_trend = cast(Literal["UP", "DOWN", "NEUTRAL"], trend)
    else:
        normalized_trend = "NEUTRAL"
    return MarketSnapshot(
        symbol=symbol,
        trend=normalized_trend,
        atr_quantile=atr_quantile,
        atr_label=_atr_label(atr_quantile),
        funding_rate=None,
        funding_available=False,
        open_interest=None,
        open_interest_available=False,
        indicators={
            "price": float(indicators["price"]),
            "ema20_4h": float(indicators["ema20_4h"]),
            "ema50_1d": float(indicators["ema50_1d"]),
            "atr_14_4h": float(indicators["atr_14_4h"]),
        },
    )


def _atr_label(quantile: float) -> Literal["LOW", "NORMAL", "HIGH"]:
    if quantile < 0.33:
        return "LOW"
    if quantile < 0.8:
        return "NORMAL"
    return "HIGH"


def _max_qty_by_exposure(equity: float, entry_price: float, max_exposure_pct: float) -> float:
    if equity <= 0 or entry_price <= 0 or max_exposure_pct <= 0:
        return 0.0
    max_notional = equity * max_exposure_pct / 100.0
    return max_notional / entry_price


def _safe_pct(value: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return value / denominator * 100.0


def _to_position_state(position: _OpenPosition) -> PositionState:
    from ai_trading.types import PositionState

    return PositionState(
        symbol=position.symbol,
        side="LONG",
        qty=position.qty,
        entry_price=position.entry_price,
        stop_loss=position.stop_loss,
        opened_at=position.opened_at,
        unrealized_pnl=0.0,
    )


def _to_utc_iso(raw_timestamp: object) -> str:
    if isinstance(raw_timestamp, pd.Timestamp):
        ts = (
            raw_timestamp.tz_convert("UTC")
            if raw_timestamp.tzinfo
            else raw_timestamp.tz_localize("UTC")
        )
        timestamp = cast(datetime, ts.to_pydatetime())
        return timestamp.isoformat()
    if isinstance(raw_timestamp, datetime):
        if raw_timestamp.tzinfo is None:
            return raw_timestamp.replace(tzinfo=timezone.utc).isoformat()
        return raw_timestamp.astimezone(timezone.utc).isoformat()
    raise TypeError("unsupported_timestamp_type")


def _write_json(path: Path, payload: object) -> None:
    import json

    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _write_go_no_go_markdown(path: Path, summary: Mapping[str, object]) -> None:
    raw_go_no_go = summary.get("go_no_go")
    go_no_go: Mapping[str, object]
    if isinstance(raw_go_no_go, Mapping):
        go_no_go = raw_go_no_go
    else:
        go_no_go = {}
    raw_checks = go_no_go.get("checks")
    checks: Mapping[str, object]
    if isinstance(raw_checks, Mapping):
        checks = raw_checks
    else:
        checks = {}
    lines = [
        "# Go / No-Go Review",
        "",
        f"- Decision: {'GO' if bool(go_no_go.get('go')) else 'NO-GO'}",
        f"- Selected AI Mode: {go_no_go.get('selected_ai_mode', 'n/a')}",
        "",
        "## Checks",
    ]
    for key, value in checks.items():
        lines.append(f"- {key}: {'PASS' if bool(value) else 'FAIL'}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
