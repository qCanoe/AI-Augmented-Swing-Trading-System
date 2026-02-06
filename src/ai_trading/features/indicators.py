"""Indicator computation for MVP strategy."""

from __future__ import annotations

from typing import Literal

import pandas as pd  # type: ignore[import-untyped]


def classify_trend(df_1d: pd.DataFrame) -> Literal["UP", "DOWN", "NEUTRAL"]:
    """Classify trend using EMA20/EMA50 direction and slope."""
    if len(df_1d) < 60:
        return "NEUTRAL"

    ema20 = _ema(df_1d["close"], 20)
    ema50 = _ema(df_1d["close"], 50)
    if len(ema20) < 2 or len(ema50) < 2:
        return "NEUTRAL"

    ema20_last = float(ema20.iloc[-1])
    ema50_last = float(ema50.iloc[-1])
    ema20_prev = float(ema20.iloc[-2])
    ema50_prev = float(ema50.iloc[-2])

    if ema20_last > ema50_last and ema20_last > ema20_prev and ema50_last > ema50_prev:
        return "UP"
    if ema20_last < ema50_last and ema20_last < ema20_prev and ema50_last < ema50_prev:
        return "DOWN"
    return "NEUTRAL"


def compute_atr_quantile(atr_series: pd.Series, lookback: int = 180) -> float:
    """Compute current ATR quantile over lookback window."""
    clean = atr_series.dropna()
    if clean.empty:
        return 1.0

    sample = clean.iloc[-lookback:]
    current = float(sample.iloc[-1])
    rank = float((sample <= current).sum())
    return rank / float(len(sample))


def compute_indicators(df_4h: pd.DataFrame, df_1d: pd.DataFrame) -> dict[str, float | str]:
    """Compute the full indicator snapshot used by strategy + AI."""
    if df_4h.empty or df_1d.empty:
        raise ValueError("input_ohlcv_empty")

    if not _is_time_ascending(df_4h) or not _is_time_ascending(df_1d):
        raise ValueError("ohlcv_timestamp_not_ascending")

    ema20_4h_series = _ema(df_4h["close"], 20)
    ema50_4h_series = _ema(df_4h["close"], 50)
    ema20_1d_series = _ema(df_1d["close"], 20)
    ema50_1d_series = _ema(df_1d["close"], 50)
    atr_series = _atr(df_4h, period=14)
    atr_quantile = compute_atr_quantile(atr_series)
    atr_value = float(atr_series.dropna().iloc[-1])
    last_close = float(df_4h["close"].iloc[-1])
    ema20_4h = float(ema20_4h_series.iloc[-1])
    ema50_1d = float(ema50_1d_series.iloc[-1])
    trend = classify_trend(df_1d)

    if atr_value <= 0:
        raise ValueError("atr_non_positive")

    distance_to_ema20_atr = abs(last_close - ema20_4h) / atr_value

    return {
        "price": last_close,
        "ema20_4h": ema20_4h,
        "ema50_4h": float(ema50_4h_series.iloc[-1]),
        "ema20_1d": float(ema20_1d_series.iloc[-1]),
        "ema50_1d": ema50_1d,
        "atr_14_4h": atr_value,
        "atr_quantile": atr_quantile,
        "distance_to_ema20_atr": float(distance_to_ema20_atr),
        "trend": trend,
    }


def _is_time_ascending(df: pd.DataFrame) -> bool:
    open_time = df.get("open_time")
    if open_time is None:
        return False
    return bool(pd.Series(open_time).is_monotonic_increasing)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr_components = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    )
    tr = tr_components.max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()
