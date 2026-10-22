"""
Extracts macro-economic indicators from FRED (Federal Reserve Economic Data).
Free API, requires a free API key (https://fred.stlouisfed.org/docs/api/api_key.html).

Falls back to synthetic data when USE_MOCK_DATA=true (see mock_data.py).
"""
import logging
import sys

import pandas as pd

from extraction.config import settings, MACRO_SERIES
from extraction import mock_data

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def extract_macro() -> pd.DataFrame:
    if settings.use_mock_data:
        logger.info("USE_MOCK_DATA=true -> generating synthetic macro data")
        return mock_data.generate_mock_macro()

    from fredapi import Fred  # imported lazily so mock mode never needs it installed

    if not settings.fred_api_key:
        raise RuntimeError(
            "FRED_API_KEY is not set. Get a free key at "
            "https://fred.stlouisfed.org/docs/api/api_key.html or set USE_MOCK_DATA=true."
        )

    fred = Fred(api_key=settings.fred_api_key)
    frames = []
    for internal_name, series_id in MACRO_SERIES.items():
        logger.info("Pulling FRED series %s (%s)", series_id, internal_name)
        series = fred.get_series(series_id)
        df = series.reset_index()
        df.columns = ["obs_date", "value"]
        df["series_id"] = internal_name
        frames.append(df[["series_id", "obs_date", "value"]].dropna())

    result = pd.concat(frames, ignore_index=True)
    logger.info("Extracted %d macro observation rows across %d series", len(result), result["series_id"].nunique())
    return result


if __name__ == "__main__":
    df = extract_macro()
    print(df.tail())
    sys.exit(0)
