"""Backtest package exports."""

from ai_trading.backtest.ai_provider import (
    AIDecisionProvider,
    HeuristicDecisionProvider,
    OpenRouterDecisionProvider,
)
from ai_trading.backtest.data import (
    fetch_binance_history_with_cache,
    load_ohlcv_csv,
    normalize_ohlcv,
)
from ai_trading.backtest.runner import run_backtest_suite, run_single_mode
from ai_trading.backtest.types import (
    BacktestConfig,
    BacktestReport,
    ExperimentMode,
    SegmentSpec,
)

__all__ = [
    "AIDecisionProvider",
    "BacktestConfig",
    "BacktestReport",
    "ExperimentMode",
    "HeuristicDecisionProvider",
    "OpenRouterDecisionProvider",
    "SegmentSpec",
    "fetch_binance_history_with_cache",
    "load_ohlcv_csv",
    "normalize_ohlcv",
    "run_backtest_suite",
    "run_single_mode",
]
