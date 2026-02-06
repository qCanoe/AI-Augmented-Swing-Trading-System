"""Deterministic candidate generation for MVP."""

from __future__ import annotations

from datetime import datetime, timezone

from ai_trading.config import Settings
from ai_trading.types import TradeCandidate

_MVP_SYMBOL = "BTCUSDT"


def generate_candidate(
    indicators: dict[str, float | str],
    settings: Settings,
    *,
    funding_rate: float | None = None,
    open_interest: float | None = None,
) -> TradeCandidate | None:
    """Generate one long-only BTC candidate from indicator snapshot."""
    trend = str(indicators["trend"])
    if trend != "UP":
        return None

    atr = float(indicators["atr_14_4h"])
    atr_quantile = float(indicators["atr_quantile"])
    distance_to_ema20_atr = float(indicators["distance_to_ema20_atr"])
    entry_price = float(indicators["price"])
    ema20_4h = float(indicators["ema20_4h"])
    ema50_1d = float(indicators["ema50_1d"])

    if atr <= 0:
        return None
    if atr_quantile > settings.atr_high_quantile:
        return None
    if distance_to_ema20_atr > settings.pullback_atr_threshold:
        return None

    reasons = [
        "trend_up_1d",
        "pullback_near_ema20_4h",
        "atr_not_extreme",
    ]
    return TradeCandidate(
        symbol=_MVP_SYMBOL,
        side="LONG",
        entry_price=entry_price,
        atr=atr,
        ema20_4h=ema20_4h,
        ema50_1d=ema50_1d,
        trend="UP",
        funding_rate=funding_rate,
        open_interest=open_interest,
        reasons=reasons,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
