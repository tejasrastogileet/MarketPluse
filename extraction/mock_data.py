"""
Deterministic synthetic data generator.

Used two places:
  1. Local development / CI tests, so the test suite doesn't depend on
     Yahoo Finance or FRED being reachable (or rate-limiting us).
  2. As a documented fallback if you want to demo the pipeline offline.

Set USE_MOCK_DATA=true to make extract_prices.py / extract_macro.py call
these functions instead of hitting the real APIs. The output schema exactly
matches what the real extractors produce, so everything downstream (load,
dbt, dashboard) is identical either way.
"""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from extraction.config import settings, MACRO_SERIES


def _business_days(end: datetime, n_days: int) -> pd.DatetimeIndex:
    start = end - timedelta(days=int(n_days * 1.45))  # pad for weekends/holidays
    return pd.bdate_range(start=start, end=end)[-n_days:]


def generate_mock_prices(tickers=None, lookback_days=None, seed=42) -> pd.DataFrame:
    """Random-walk OHLCV data that looks structurally like real market data."""
    tickers = tickers or settings.tickers
    lookback_days = lookback_days or settings.lookback_days
    dates = _business_days(datetime.utcnow(), lookback_days)

    frames = []
    for i, ticker in enumerate(tickers):
        ticker_rng = np.random.default_rng(seed + i)
        start_price = ticker_rng.uniform(20, 500)
        daily_returns = ticker_rng.normal(loc=0.0004, scale=0.018, size=len(dates))
        close = start_price * np.cumprod(1 + daily_returns)
        open_ = close * (1 + ticker_rng.normal(0, 0.004, size=len(dates)))
        high = np.maximum(open_, close) * (1 + np.abs(ticker_rng.normal(0, 0.006, size=len(dates))))
        low = np.minimum(open_, close) * (1 - np.abs(ticker_rng.normal(0, 0.006, size=len(dates))))
        volume = ticker_rng.integers(1_000_000, 80_000_000, size=len(dates))

        frames.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "trade_date": dates,
                    "open": open_.round(2),
                    "high": high.round(2),
                    "low": low.round(2),
                    "close": close.round(2),
                    "volume": volume,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def generate_mock_macro(lookback_days=None, seed=7) -> pd.DataFrame:
    """Monthly-ish macro series resampled to a daily grid via forward-fill,
    mirroring how FRED series behave (low frequency, sparsely updated)."""
    lookback_days = lookback_days or settings.lookback_days
    rng = np.random.default_rng(seed)
    dates = _business_days(datetime.utcnow(), lookback_days)

    frames = []
    base_values = {
        "treasury_10y": 4.2,
        "unemployment_rate": 3.9,
        "cpi_all_items": 310.0,
        "fed_funds_rate": 5.1,
    }
    for series_name in MACRO_SERIES:
        base = base_values[series_name]
        walk = np.cumsum(rng.normal(0, 0.02, size=len(dates)))
        values = base + walk
        frames.append(
            pd.DataFrame(
                {
                    "series_id": series_name,
                    "obs_date": dates,
                    "value": values.round(3),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


if __name__ == "__main__":
    prices = generate_mock_prices()
    macro = generate_mock_macro()
    print(f"Generated {len(prices):,} price rows across {prices['ticker'].nunique()} tickers")
    print(f"Generated {len(macro):,} macro observation rows across {macro['series_id'].nunique()} series")
    print(prices.head())
    print(macro.head())
