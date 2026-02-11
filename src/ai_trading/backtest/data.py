"""Historical data loading helpers for backtests."""

from __future__ import annotations

from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from ai_trading.config import Settings
from ai_trading.data.binance import BinanceDataClient

_REQUIRED_COLUMNS = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
]


def load_ohlcv_csv(path: Path) -> pd.DataFrame:
    """Load OHLCV data from CSV and normalize schema."""
    df = pd.read_csv(path)
    return normalize_ohlcv(df)


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Validate/normalize dataframe to the expected OHLCV shape."""
    missing = [col for col in _REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"missing_ohlcv_columns: {','.join(missing)}")

    normalized = df[_REQUIRED_COLUMNS].copy()
    normalized["open_time"] = pd.to_datetime(normalized["open_time"], utc=True)
    normalized["close_time"] = pd.to_datetime(normalized["close_time"], utc=True)
    numeric_cols = ["open", "high", "low", "close", "volume"]
    for col in numeric_cols:
        normalized[col] = pd.to_numeric(normalized[col], errors="coerce")

    normalized = normalized.dropna(subset=numeric_cols + ["open_time", "close_time"])
    normalized = normalized.sort_values("open_time").reset_index(drop=True)
    if normalized.empty:
        raise ValueError("normalized_ohlcv_empty")
    if not bool(normalized["open_time"].is_monotonic_increasing):
        raise ValueError("ohlcv_not_monotonic_after_normalization")
    return normalized


def fetch_binance_history_with_cache(
    settings: Settings,
    *,
    symbol: str,
    limit_4h: int,
    limit_1d: int,
    cache_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Fetch Binance OHLCV with optional local CSV cache."""
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_4h = cache_dir / f"{symbol.lower()}_4h.csv"
        cache_1d = cache_dir / f"{symbol.lower()}_1d.csv"
        if cache_4h.exists() and cache_1d.exists():
            return load_ohlcv_csv(cache_4h), load_ohlcv_csv(cache_1d)
    else:
        cache_4h = None
        cache_1d = None

    client = BinanceDataClient(settings)
    df_4h = normalize_ohlcv(client.fetch_ohlcv(symbol, "4h", limit_4h))
    df_1d = normalize_ohlcv(client.fetch_ohlcv(symbol, "1d", limit_1d))

    if cache_4h is not None and cache_1d is not None:
        df_4h.to_csv(cache_4h, index=False)
        df_1d.to_csv(cache_1d, index=False)
    return df_4h, df_1d
