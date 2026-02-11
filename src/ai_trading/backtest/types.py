"""Shared types for backtest workflow."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ExperimentMode = Literal["baseline", "ai_filter", "ai_filter_sizing"]


@dataclass(slots=True)
class SegmentSpec:
    """Named time range for segmented evaluation."""

    name: str
    start_at: str
    end_at: str


@dataclass(slots=True)
class BacktestConfig:
    """Runtime parameters for one backtest run."""

    symbol: str = "BTCUSDT"
    initial_equity: float = 10_000.0
    slippage_bps: float = 2.0
    warmup_4h_bars: int = 200
    min_1d_bars: int = 60


@dataclass(slots=True)
class TradeRecord:
    """Executed trade with realized pnl."""

    mode: ExperimentMode
    symbol: str
    opened_at: str
    closed_at: str
    close_reason: str
    qty: float
    entry_price: float
    exit_price: float
    stop_loss: float
    pnl: float
    pnl_pct: float
    ai_decision: str
    ai_confidence: float


@dataclass(slots=True)
class EquityPoint:
    """Equity curve point at one candle close."""

    timestamp: str
    equity: float
    regime: str


@dataclass(slots=True)
class ExperimentResult:
    """Result bundle for one experiment mode."""

    mode: ExperimentMode
    trades: list[TradeRecord] = field(default_factory=list)
    equity_curve: list[EquityPoint] = field(default_factory=list)
    decisions: list[dict[str, object]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metrics: dict[str, float | int | None] = field(default_factory=dict)
    segment_metrics: dict[str, dict[str, float | int | None]] = field(default_factory=dict)


@dataclass(slots=True)
class BacktestReport:
    """Full report across all experiment modes."""

    symbol: str
    started_at: str
    source: str
    segments: list[SegmentSpec]
    experiments: dict[ExperimentMode, ExperimentResult]
    go_no_go: dict[str, object]
