"""Binance market data client for MVP."""

from __future__ import annotations

from typing import Any

import pandas as pd  # type: ignore[import-untyped]
from binance.client import Client  # type: ignore[import-untyped]

from ai_trading.config import Settings
from ai_trading.utils.logging import get_logger


class BinanceDataClient:
    """Read-only client for OHLCV/funding/OI."""

    _INTERVAL_MAP = {
        "4h": Client.KLINE_INTERVAL_4HOUR,
        "1d": Client.KLINE_INTERVAL_1DAY,
    }

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._logger = get_logger("ai_trading.data.binance")
        self._client = Client(
            api_key=settings.binance_api_key or None,
            api_secret=settings.binance_api_secret or None,
            testnet=settings.binance_testnet,
        )

    def fetch_ohlcv(self, symbol: str, interval: str, limit: int) -> pd.DataFrame:
        """Fetch futures klines and return normalized dataframe."""
        resolved_interval = self._INTERVAL_MAP.get(interval.lower())
        if resolved_interval is None:
            raise ValueError(f"unsupported_interval: {interval}")

        rows = self._client.futures_klines(symbol=symbol, interval=resolved_interval, limit=limit)
        df = pd.DataFrame(
            rows,
            columns=[
                "open_time",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "close_time",
                "quote_asset_volume",
                "number_of_trades",
                "taker_buy_base_asset_volume",
                "taker_buy_quote_asset_volume",
                "ignore",
            ],
        )
        if df.empty:
            raise RuntimeError("empty_ohlcv_response")

        numeric_cols = ["open", "high", "low", "close", "volume"]
        for col in numeric_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
        df = df.dropna(subset=numeric_cols).reset_index(drop=True)
        return df[["open_time", "open", "high", "low", "close", "volume", "close_time"]]

    def fetch_funding_rate(self, symbol: str) -> float | None:
        """Fetch latest funding rate. Returns None on failure."""
        try:
            rows = self._client.futures_funding_rate(symbol=symbol, limit=1)
            if not rows:
                return None
            row = rows[-1]
            value = row.get("fundingRate")
            return float(value) if value is not None else None
        except Exception as exc:  # noqa: BLE001 - keep pipeline resilient.
            self._logger.warning("funding_fetch_failed", symbol=symbol, error=str(exc))
            return None

    def fetch_open_interest(self, symbol: str) -> float | None:
        """Fetch latest open interest. Returns None on failure."""
        try:
            payload: dict[str, Any] = self._client.futures_open_interest(symbol=symbol)
            value = payload.get("openInterest")
            return float(value) if value is not None else None
        except Exception as exc:  # noqa: BLE001 - keep pipeline resilient.
            self._logger.warning("oi_fetch_failed", symbol=symbol, error=str(exc))
            return None
