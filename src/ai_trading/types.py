"""Shared domain types for the MVP trading pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Side = Literal["LONG"]


@dataclass(slots=True)
class TradeCandidate:
    """A deterministic trade candidate produced by strategy rules."""

    symbol: str
    side: Side
    entry_price: float
    atr: float
    ema20_4h: float
    ema50_1d: float
    trend: Literal["UP", "DOWN", "NEUTRAL"]
    funding_rate: float | None
    open_interest: float | None
    reasons: list[str]
    created_at: str


@dataclass(slots=True)
class PositionState:
    """Current paper position state."""

    symbol: str
    side: Side
    qty: float
    entry_price: float
    stop_loss: float
    opened_at: str
    unrealized_pnl: float = 0.0


@dataclass(slots=True)
class CycleResult:
    """Outcome of one pipeline cycle run."""

    status: str
    decisions: list[dict[str, object]] = field(default_factory=list)
    orders: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


@dataclass(slots=True)
class RiskCheckResult:
    """Result of global risk guard checks."""

    allowed: bool
    risk_budget_pct: float
    reasons: list[str] = field(default_factory=list)
