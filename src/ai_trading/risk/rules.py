"""Hard risk control rules for MVP."""

from __future__ import annotations

from datetime import datetime

from ai_trading.config import Settings
from ai_trading.types import PositionState, RiskCheckResult


class RiskEngine:
    """Rule-based risk controls."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def check_global_guards(self, journal_stats: dict[str, float | int]) -> RiskCheckResult:
        """Validate global guard rails from recent account stats."""
        reasons: list[str] = []

        consecutive_losses = int(journal_stats.get("consecutive_losses", 0))
        weekly_drawdown_pct = float(journal_stats.get("weekly_drawdown_pct", 0.0))
        total_exposure_pct = float(journal_stats.get("total_exposure_pct", 0.0))

        if consecutive_losses >= self._settings.max_consecutive_losses:
            reasons.append("max_consecutive_losses_reached")
        if weekly_drawdown_pct >= self._settings.max_weekly_drawdown_pct:
            reasons.append("max_weekly_drawdown_reached")
        if total_exposure_pct > self._settings.max_total_exposure_pct:
            reasons.append("max_total_exposure_exceeded")

        return RiskCheckResult(
            allowed=not reasons,
            risk_budget_pct=self._settings.risk_per_trade_pct,
            reasons=reasons,
        )

    def compute_position_size(
        self,
        equity: float,
        entry: float,
        stop: float,
        risk_budget_pct: float,
    ) -> float:
        """Compute position size from risk-per-trade budget."""
        if equity <= 0 or entry <= 0 or stop <= 0:
            return 0.0
        per_unit_risk = entry - stop
        if per_unit_risk <= 0:
            return 0.0
        risk_amount = equity * (risk_budget_pct / 100.0)
        qty = risk_amount / per_unit_risk
        return max(0.0, float(qty))

    def build_stop_loss(self, entry: float, atr: float, atr_multiplier: float) -> float:
        """Build long stop loss from ATR."""
        if entry <= 0 or atr <= 0 or atr_multiplier <= 0:
            return 0.0
        stop = entry - atr * atr_multiplier
        return max(0.0, float(stop))

    def check_time_stop(
        self,
        position: PositionState,
        now: datetime,
        max_holding_days: int,
    ) -> bool:
        """Check whether position exceeded max holding duration."""
        opened_at = datetime.fromisoformat(position.opened_at)
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=now.tzinfo)
        held_days = (now - opened_at).total_seconds() / 86400
        return held_days >= float(max_holding_days)
