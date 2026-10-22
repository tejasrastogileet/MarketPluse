"""
Shared configuration for the extraction/load pipeline.

All settings are read from environment variables so the exact same code runs
against local Docker Postgres (dev), a live free-tier Postgres like Neon or
Supabase (the public demo), or whatever a CI runner injects as secrets.
"""
import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _tickers_from_env() -> List[str]:
    raw = os.getenv(
        "TICKERS",
        "AAPL,MSFT,GOOGL,AMZN,META,NVDA,TSLA,JPM,GS,V,MA,WMT,COST,XOM,CVX,UNH,JNJ,PFE,BA,DIS",
    )
    return [t.strip().upper() for t in raw.split(",") if t.strip()]


# Macro series pulled from FRED. Keys are the internal column name we use,
# values are FRED's official series IDs.
MACRO_SERIES = {
    "treasury_10y": "DGS10",       # 10-Year Treasury Constant Maturity Rate
    "unemployment_rate": "UNRATE",  # Civilian Unemployment Rate
    "cpi_all_items": "CPIAUCSL",    # Consumer Price Index, All Urban Consumers
    "fed_funds_rate": "FEDFUNDS",   # Effective Federal Funds Rate
}


@dataclass
class Settings:
    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: str = os.getenv("POSTGRES_PORT", "5432")
    postgres_db: str = os.getenv("POSTGRES_DB", "market_data")
    postgres_user: str = os.getenv("POSTGRES_USER", "market_user")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "market_pass")
    fred_api_key: str = os.getenv("FRED_API_KEY", "")
    tickers: List[str] = field(default_factory=_tickers_from_env)
    use_mock_data: bool = os.getenv("USE_MOCK_DATA", "false").lower() in ("1", "true", "yes")
    lookback_days: int = int(os.getenv("LOOKBACK_DAYS", "730"))  # ~2 years on first run

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
