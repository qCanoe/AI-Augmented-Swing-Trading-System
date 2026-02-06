"""Paper trading executor with persistent local state."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ai_trading.types import PositionState, TradeCandidate


@dataclass(slots=True)
class _PaperState:
    equity: float
    initial_equity: float
    consecutive_losses: int
    week_start_equity: float
    week_start_date: str
    position: PositionState | None


class PaperExecutor:
    """Simulated execution for one-symbol long-only MVP."""

    def __init__(
        self,
        journal_dir: Path,
        *,
        slippage_bps: float = 2.0,
        initial_equity: float = 10_000.0,
    ) -> None:
        self._slippage_bps = slippage_bps
        self._state_file = journal_dir / "paper_state.json"
        self._state = self._load_state(initial_equity)

    @property
    def equity(self) -> float:
        return self._state.equity

    @property
    def position(self) -> PositionState | None:
        return self._state.position

    def open_long(self, candidate: TradeCandidate, qty: float, stop_loss: float) -> dict[str, Any]:
        """Open a long position with configured slippage."""
        if qty <= 0:
            raise ValueError("qty_must_be_positive")
        if self._state.position is not None:
            raise RuntimeError("position_already_open")
        fill_price = candidate.entry_price * (1.0 + self._slippage_bps / 10_000.0)
        position = PositionState(
            symbol=candidate.symbol,
            side="LONG",
            qty=float(qty),
            entry_price=float(fill_price),
            stop_loss=float(stop_loss),
            opened_at=datetime.now(timezone.utc).isoformat(),
            unrealized_pnl=0.0,
        )
        self._state.position = position
        self._persist()
        return {
            "action": "open",
            "symbol": candidate.symbol,
            "side": "BUY",
            "qty": float(qty),
            "price": float(fill_price),
            "stop_loss": float(stop_loss),
            "status": "filled",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def close_position(
        self,
        position: PositionState,
        reason: str,
        *,
        exit_price: float | None = None,
    ) -> dict[str, Any]:
        """Close current position and realize PnL."""
        active = self._state.position
        if active is None:
            raise RuntimeError("no_open_position")
        if active.symbol != position.symbol:
            raise RuntimeError("position_mismatch")

        raw_exit = active.entry_price if exit_price is None else exit_price
        fill_price = raw_exit * (1.0 - self._slippage_bps / 10_000.0)
        pnl = (fill_price - active.entry_price) * active.qty
        self._state.equity += pnl
        self._update_consecutive_losses(pnl)
        self._roll_week_if_needed()
        self._state.position = None
        self._persist()
        return {
            "action": "close",
            "symbol": active.symbol,
            "side": "SELL",
            "qty": active.qty,
            "price": float(fill_price),
            "reason": reason,
            "realized_pnl": float(pnl),
            "status": "filled",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def mark_to_market(self, last_price: float) -> dict[str, Any]:
        """Update unrealized PnL for current position."""
        position = self._state.position
        if position is None:
            return {
                "has_position": False,
                "unrealized_pnl": 0.0,
                "equity": self._state.equity,
            }
        position.unrealized_pnl = (last_price - position.entry_price) * position.qty
        self._state.position = position
        self._persist()
        return {
            "has_position": True,
            "symbol": position.symbol,
            "last_price": float(last_price),
            "unrealized_pnl": float(position.unrealized_pnl),
            "equity": self._state.equity + position.unrealized_pnl,
        }

    def get_risk_stats(self, last_price: float | None = None) -> dict[str, float | int]:
        """Provide account-level stats needed by risk guards."""
        self._roll_week_if_needed()
        if self._state.week_start_equity > 0:
            weekly_drawdown_pct = (
                (self._state.week_start_equity - self._state.equity)
                / self._state.week_start_equity
                * 100
            )
        else:
            weekly_drawdown_pct = 0.0
        weekly_drawdown_pct = max(
            0.0, weekly_drawdown_pct
        )
        exposure_pct = 0.0
        if self._state.position is not None:
            mark_price = last_price if last_price is not None else self._state.position.entry_price
            notional = self._state.position.qty * mark_price
            if self._state.equity > 0:
                exposure_pct = notional / self._state.equity * 100
        return {
            "consecutive_losses": self._state.consecutive_losses,
            "weekly_drawdown_pct": float(weekly_drawdown_pct),
            "total_exposure_pct": float(exposure_pct),
        }

    def _load_state(self, initial_equity: float) -> _PaperState:
        if not self._state_file.exists():
            return _PaperState(
                equity=initial_equity,
                initial_equity=initial_equity,
                consecutive_losses=0,
                week_start_equity=initial_equity,
                week_start_date=datetime.now(timezone.utc).date().isoformat(),
                position=None,
            )

        raw = json.loads(self._state_file.read_text(encoding="utf-8"))
        position_payload = raw.get("position")
        position = PositionState(**position_payload) if isinstance(position_payload, dict) else None
        return _PaperState(
            equity=float(raw.get("equity", initial_equity)),
            initial_equity=float(raw.get("initial_equity", initial_equity)),
            consecutive_losses=int(raw.get("consecutive_losses", 0)),
            week_start_equity=float(raw.get("week_start_equity", initial_equity)),
            week_start_date=str(
                raw.get(
                    "week_start_date",
                    datetime.now(timezone.utc).date().isoformat(),
                )
            ),
            position=position,
        )

    def _persist(self) -> None:
        payload: dict[str, Any] = {
            "equity": self._state.equity,
            "initial_equity": self._state.initial_equity,
            "consecutive_losses": self._state.consecutive_losses,
            "week_start_equity": self._state.week_start_equity,
            "week_start_date": self._state.week_start_date,
            "position": asdict(self._state.position) if self._state.position else None,
        }
        serialized = json.dumps(payload, ensure_ascii=True, indent=2)
        self._state_file.write_text(serialized, encoding="utf-8")

    def _update_consecutive_losses(self, pnl: float) -> None:
        if pnl < 0:
            self._state.consecutive_losses += 1
        else:
            self._state.consecutive_losses = 0

    def _roll_week_if_needed(self) -> None:
        now = datetime.now(timezone.utc).date()
        current_week = now.isocalendar()[1]
        state_week = datetime.fromisoformat(self._state.week_start_date).date().isocalendar()[1]
        if current_week != state_week:
            self._state.week_start_equity = self._state.equity
            self._state.week_start_date = now.isoformat()
