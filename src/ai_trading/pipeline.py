"""Unified trading cycle pipeline for MVP."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from time import perf_counter
from typing import Literal

from ai_trading.ai.openrouter_client import OpenRouterAPIError, OpenRouterClient
from ai_trading.ai.schemas import LLMDecision, MarketSnapshot
from ai_trading.config import Settings
from ai_trading.data.binance import BinanceDataClient
from ai_trading.exec.paper import PaperExecutor
from ai_trading.features.indicators import compute_indicators
from ai_trading.journal.store import JournalStore
from ai_trading.risk.rules import RiskEngine
from ai_trading.strategy.candidates import generate_candidate
from ai_trading.types import CycleResult, PositionState, TradeCandidate
from ai_trading.utils.logging import get_logger

_SYMBOL = "BTCUSDT"
_LIMIT_4H = 400
_LIMIT_1D = 300


def run_trading_cycle(settings: Settings, dry_run: bool) -> CycleResult:
    """Run one full trading cycle."""
    logger = get_logger("ai_trading.pipeline")
    started = perf_counter()
    journal = JournalStore(settings.journal_dir)
    paper = PaperExecutor(settings.journal_dir)
    risk_engine = RiskEngine(settings)
    cycle_result = CycleResult(status="unknown")

    journal.append(
        "cycle_start",
        {
            "symbol": _SYMBOL,
            "mode": settings.mode.value,
            "dry_run": dry_run,
            "started_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    try:
        data_client = BinanceDataClient(settings)
        df_4h = data_client.fetch_ohlcv(_SYMBOL, "4h", _LIMIT_4H)
        df_1d = data_client.fetch_ohlcv(_SYMBOL, "1d", _LIMIT_1D)
        funding_rate = data_client.fetch_funding_rate(_SYMBOL)
        open_interest = data_client.fetch_open_interest(_SYMBOL)
        indicators = compute_indicators(df_4h, df_1d)
        last_price = float(indicators["price"])

        journal.append(
            "market_data",
            {
                "symbol": _SYMBOL,
                "rows_4h": len(df_4h),
                "rows_1d": len(df_1d),
                "funding_available": funding_rate is not None,
                "open_interest_available": open_interest is not None,
                "last_price": last_price,
            },
        )

        position = paper.position
        if position is not None:
            mtm = paper.mark_to_market(last_price)
            journal.append("position_update", mtm)

            if last_price <= position.stop_loss:
                close_order = _close_position(
                    paper,
                    position,
                    reason="stop_loss",
                    exit_price=last_price,
                    dry_run=dry_run,
                )
                cycle_result.orders.append(close_order)
                journal.append("order", close_order)
                position = paper.position

            if position is not None and risk_engine.check_time_stop(
                position, datetime.now(timezone.utc), settings.max_holding_days
            ):
                close_order = _close_position(
                    paper,
                    position,
                    reason="time_stop",
                    exit_price=last_price,
                    dry_run=dry_run,
                )
                cycle_result.orders.append(close_order)
                journal.append("order", close_order)

        if paper.position is not None:
            return _finish_cycle(
                cycle_result,
                journal,
                started,
                status="position_open_no_new_entry",
            )

        candidate = generate_candidate(
            indicators,
            settings,
            funding_rate=funding_rate,
            open_interest=open_interest,
        )
        if candidate is None:
            return _finish_cycle(cycle_result, journal, started, status="no_signal")

        journal.append("candidate", asdict(candidate))

        snapshot = MarketSnapshot(
            symbol=candidate.symbol,
            trend=candidate.trend,
            atr_quantile=float(indicators["atr_quantile"]),
            atr_label=_atr_label(float(indicators["atr_quantile"])),
            funding_rate=funding_rate,
            funding_available=funding_rate is not None,
            open_interest=open_interest,
            open_interest_available=open_interest is not None,
            indicators={
                "price": float(indicators["price"]),
                "ema20_4h": float(indicators["ema20_4h"]),
                "ema50_1d": float(indicators["ema50_1d"]),
                "atr_14_4h": float(indicators["atr_14_4h"]),
            },
        )

        ai_degraded = False
        try:
            ai_decision = OpenRouterClient(settings).evaluate(snapshot)
        except OpenRouterAPIError as exc:
            ai_degraded = True
            ai_decision = LLMDecision(
                decision="ALLOW",
                confidence=1.0,
                risk_flags=["AI_UNAVAILABLE"],
                key_reasons=[f"fallback_to_rules: {exc}"],
            )
            cycle_result.warnings.append("ai_unavailable_fallback_to_rules")

        cycle_result.decisions.append(ai_decision.model_dump())
        journal.append(
            "ai_decision",
            {
                **ai_decision.model_dump(),
                "degraded_mode": ai_degraded,
            },
        )

        if ai_decision.decision == "DENY":
            return _finish_cycle(cycle_result, journal, started, status="ai_denied")

        risk_stats = paper.get_risk_stats(last_price)
        guard_result = risk_engine.check_global_guards(risk_stats)
        effective_risk_budget = _effective_risk_budget(settings, ai_decision, ai_degraded)

        journal.append(
            "risk_check",
            {
                "global_allowed": guard_result.allowed,
                "guard_reasons": guard_result.reasons,
                "risk_budget_pct": effective_risk_budget,
                **risk_stats,
            },
        )
        if not guard_result.allowed:
            cycle_result.decisions.append(
                {
                    "decision": "DENY",
                    "confidence": 0.0,
                    "risk_flags": ["RISK_GUARD_BLOCK"],
                    "key_reasons": guard_result.reasons,
                }
            )
            return _finish_cycle(cycle_result, journal, started, status="risk_blocked")

        stop_loss = risk_engine.build_stop_loss(
            candidate.entry_price,
            candidate.atr,
            settings.stop_loss_atr_multiplier,
        )
        qty = risk_engine.compute_position_size(
            equity=paper.equity,
            entry=candidate.entry_price,
            stop=stop_loss,
            risk_budget_pct=effective_risk_budget,
        )
        qty = min(
            qty,
            _max_qty_by_exposure(
                paper.equity,
                candidate.entry_price,
                settings.max_total_exposure_pct,
            ),
        )

        if qty <= 0:
            cycle_result.warnings.append("qty_zero_after_risk_controls")
            return _finish_cycle(cycle_result, journal, started, status="risk_rejected")

        order = _open_position(paper, candidate, qty, stop_loss, dry_run)
        cycle_result.orders.append(order)
        journal.append("order", order)
        return _finish_cycle(
            cycle_result,
            journal,
            started,
            status="opened_dry_run" if dry_run else "opened",
        )

    except Exception as exc:  # noqa: BLE001 - top-level guard for loop resilience.
        logger.exception("pipeline_failed", error=str(exc))
        journal.append("error", {"error": str(exc)})
        return _finish_cycle(cycle_result, journal, started, status="failed")


def _open_position(
    paper: PaperExecutor,
    candidate: TradeCandidate,
    qty: float,
    stop_loss: float,
    dry_run: bool,
) -> dict[str, object]:
    if dry_run:
        return {
            "action": "open",
            "symbol": candidate.symbol,
            "side": "BUY",
            "qty": qty,
            "price": candidate.entry_price,
            "stop_loss": stop_loss,
            "status": "dry_run",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    return paper.open_long(candidate, qty, stop_loss)


def _close_position(
    paper: PaperExecutor,
    position: PositionState,
    *,
    reason: str,
    exit_price: float,
    dry_run: bool,
) -> dict[str, object]:
    if dry_run:
        return {
            "action": "close",
            "symbol": position.symbol,
            "side": "SELL",
            "qty": position.qty,
            "price": exit_price,
            "reason": reason,
            "status": "dry_run",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    return paper.close_position(position, reason, exit_price=exit_price)


def _max_qty_by_exposure(equity: float, entry_price: float, max_exposure_pct: float) -> float:
    if equity <= 0 or entry_price <= 0 or max_exposure_pct <= 0:
        return 0.0
    max_notional = equity * max_exposure_pct / 100.0
    return max_notional / entry_price


def _effective_risk_budget(settings: Settings, decision: LLMDecision, ai_degraded: bool) -> float:
    base = settings.risk_per_trade_pct
    if ai_degraded:
        return base * 0.5
    if decision.decision == "REDUCE":
        return base * max(0.0, min(1.0, decision.confidence))
    return base * max(0.5, min(1.0, decision.confidence))


def _atr_label(quantile: float) -> Literal["LOW", "NORMAL", "HIGH"]:
    if quantile < 0.33:
        return "LOW"
    if quantile < 0.8:
        return "NORMAL"
    return "HIGH"


def _finish_cycle(
    result: CycleResult,
    journal: JournalStore,
    started: float,
    *,
    status: str,
) -> CycleResult:
    elapsed_ms = (perf_counter() - started) * 1000
    result.status = status
    result.elapsed_ms = elapsed_ms
    journal.append("cycle_end", {"status": status, "elapsed_ms": elapsed_ms})
    return result
