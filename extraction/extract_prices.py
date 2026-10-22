"""
Extracts daily OHLCV price data for the configured ticker list from Yahoo
Finance (via yfinance - free, no API key required).

Falls back to synthetic data when USE_MOCK_DATA=true, so the rest of the
pipeline (load -> dbt -> dashboard) can be developed/tested without hitting
a live API or needing network access.
"""
import logging
import sys

import pandas as pd

from extraction.config import settings
from extraction import mock_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def extract_prices() -> pd.DataFrame:
    if settings.use_mock_data:
        logger.info("USE_MOCK_DATA=true -> generating synthetic OHLCV data")
        return mock_data.generate_mock_prices()

    import yfinance as yf  # imported lazily so mock mode never needs it installed
    import pandas_market_calendars as mcal

    logger.info(
        "Downloading %d days of OHLCV for %d tickers from Yahoo Finance",
        settings.lookback_days,
        len(settings.tickers),
    )
    raw = yf.download(
        tickers=settings.tickers,
        period=f"{settings.lookback_days}d",
        interval="1d",
        group_by="ticker",
        auto_adjust=True,
        threads=True,
        progress=False,
    )

    # Yahoo occasionally serves a garbage placeholder bar for a single ticker
    # on a date its NYSE session hasn't actually closed yet - observed as a
    # ~13x price spike isolated to one ticker on market holidays, or on
    # today's still-in-progress session if this runs pre/mid-market. Keep
    # only dates whose NYSE session has genuinely closed.
    now_utc = pd.Timestamp.now(tz="UTC")
    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=(now_utc - pd.Timedelta(days=settings.lookback_days + 10)).date(),
        end_date=now_utc.date(),
    )
    closed_sessions = set(schedule.index[schedule["market_close"] <= now_utc].date)

    frames = []
    for ticker in settings.tickers:
        try:
            df = raw[ticker].reset_index()
        except (KeyError, IndexError):
            logger.warning("No data returned for %s, skipping", ticker)
            continue
        df = df.rename(
            columns={
                "Date": "trade_date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        df["ticker"] = ticker
        df = df[df["trade_date"].dt.date.isin(closed_sessions)]
        frames.append(df[["ticker", "trade_date", "open", "high", "low", "close", "volume"]])

    if not frames:
        raise RuntimeError("yfinance returned no usable data for any configured ticker")

    result = pd.concat(frames, ignore_index=True).dropna(subset=["close"])
    logger.info("Extracted %d price rows across %d tickers", len(result), result["ticker"].nunique())
    return result


if __name__ == "__main__":
    df = extract_prices()
    print(df.tail())
    sys.exit(0)
