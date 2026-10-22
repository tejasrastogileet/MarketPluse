"""
Unit tests using the synthetic mock data generator - no network access or
live API credentials required, so these run the same in CI as on a laptop
with no internet.
"""
import pandas as pd

from extraction import mock_data


def test_mock_prices_schema():
    df = mock_data.generate_mock_prices(tickers=["AAPL", "MSFT"], lookback_days=100)
    expected_cols = {"ticker", "trade_date", "open", "high", "low", "close", "volume"}
    assert expected_cols.issubset(df.columns)
    assert df["ticker"].nunique() == 2
    assert len(df) == 200  # 2 tickers * 100 days


def test_mock_prices_no_nulls_in_close():
    df = mock_data.generate_mock_prices(tickers=["AAPL"], lookback_days=50)
    assert df["close"].notna().all()
    assert (df["close"] > 0).all()


def test_mock_prices_high_gte_low():
    df = mock_data.generate_mock_prices(tickers=["AAPL", "TSLA", "NVDA"], lookback_days=200)
    assert (df["high"] >= df["low"]).all()


def test_mock_macro_schema():
    df = mock_data.generate_mock_macro(lookback_days=100)
    expected_cols = {"series_id", "obs_date", "value"}
    assert expected_cols.issubset(df.columns)
    assert df["series_id"].nunique() == 4


def test_mock_data_is_deterministic():
    df1 = mock_data.generate_mock_prices(tickers=["AAPL"], lookback_days=30, seed=42)
    df2 = mock_data.generate_mock_prices(tickers=["AAPL"], lookback_days=30, seed=42)
    pd.testing.assert_frame_equal(df1, df2)
