from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_trading.config import Settings
from ai_trading.risk.rules import RiskEngine
from ai_trading.types import PositionState


def test_compute_position_size() -> None:
    engine = RiskEngine(Settings(journal_dir="data/journal"))
    qty = engine.compute_position_size(
        equity=10_000,
        entry=50_000,
        stop=49_500,
        risk_budget_pct=0.5,
    )
    assert qty > 0


def test_check_time_stop() -> None:
    engine = RiskEngine(Settings(journal_dir="data/journal"))
    opened_at = (datetime.now(UTC) - timedelta(days=8)).isoformat()
    position = PositionState(
        symbol="BTCUSDT",
        side="LONG",
        qty=0.1,
        entry_price=50_000,
        stop_loss=49_000,
        opened_at=opened_at,
        unrealized_pnl=0.0,
    )
    assert engine.check_time_stop(position, datetime.now(UTC), max_holding_days=7)


def test_global_guards_block() -> None:
    settings = Settings(journal_dir="data/journal")
    engine = RiskEngine(settings)
    result = engine.check_global_guards(
        {
            "consecutive_losses": settings.max_consecutive_losses,
            "weekly_drawdown_pct": 0.0,
            "total_exposure_pct": 0.0,
        }
    )
    assert not result.allowed
