"""
Loads extracted DataFrames into the `raw` schema of Postgres.

Uses a batched INSERT ... ON CONFLICT DO UPDATE (upsert) rather than a naive
append, so re-running the pipeline for a date range you already have is
idempotent - no duplicate rows, and revised values (e.g. Yahoo Finance
occasionally restates a recent close) overwrite cleanly instead of piling up.

Also writes a row to `raw.pipeline_runs` on every run, which is what the
Streamlit dashboard's "Pipeline Health" view and the Airflow DAG's alerting
task read from.
"""
import logging
from datetime import datetime, timezone

import pandas as pd
from psycopg2.extras import execute_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from extraction.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DDL = """
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.stock_prices (
    ticker      VARCHAR(10)   NOT NULL,
    trade_date  DATE          NOT NULL,
    open        NUMERIC(14,4),
    high        NUMERIC(14,4),
    low         NUMERIC(14,4),
    close       NUMERIC(14,4),
    volume      BIGINT,
    loaded_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (ticker, trade_date)
);

CREATE TABLE IF NOT EXISTS raw.macro_indicators (
    series_id   VARCHAR(50)   NOT NULL,
    obs_date    DATE          NOT NULL,
    value       NUMERIC(14,4),
    loaded_at   TIMESTAMPTZ   NOT NULL DEFAULT now(),
    PRIMARY KEY (series_id, obs_date)
);

CREATE TABLE IF NOT EXISTS raw.pipeline_runs (
    run_id        SERIAL PRIMARY KEY,
    pipeline_name VARCHAR(100) NOT NULL,
    started_at    TIMESTAMPTZ  NOT NULL,
    finished_at   TIMESTAMPTZ,
    status        VARCHAR(20)  NOT NULL,       -- 'success' | 'failed'
    rows_loaded   INTEGER,
    dbt_tests_passed INTEGER,
    dbt_tests_failed INTEGER,
    error_message TEXT
);
"""

UPSERT_PRICES = """
INSERT INTO raw.stock_prices (ticker, trade_date, open, high, low, close, volume)
VALUES %s
ON CONFLICT (ticker, trade_date)
DO UPDATE SET
    open = EXCLUDED.open,
    high = EXCLUDED.high,
    low = EXCLUDED.low,
    close = EXCLUDED.close,
    volume = EXCLUDED.volume,
    loaded_at = now();
"""

UPSERT_MACRO = """
INSERT INTO raw.macro_indicators (series_id, obs_date, value)
VALUES %s
ON CONFLICT (series_id, obs_date)
DO UPDATE SET
    value = EXCLUDED.value,
    loaded_at = now();
"""


def _bulk_upsert(engine: Engine, sql: str, columns: list, records: list) -> None:
    """Runs an execute_values upsert in batched multi-row statements instead
    of one round trip per row - the difference between seconds and tens of
    minutes when the target is a remote Postgres (Neon/Supabase) rather than
    a same-host Docker container."""
    if not records:
        return
    rows = [tuple(r[c] for c in columns) for r in records]
    raw_conn = engine.raw_connection()
    try:
        with raw_conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=1000)
        raw_conn.commit()
    finally:
        raw_conn.close()


def get_engine() -> Engine:
    return create_engine(settings.sqlalchemy_url, pool_pre_ping=True)


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text(DDL))
    logger.info("Schema ensured (raw.stock_prices, raw.macro_indicators, raw.pipeline_runs)")


def load_prices(engine: Engine, df: pd.DataFrame) -> int:
    records = df.to_dict(orient="records")
    _bulk_upsert(engine, UPSERT_PRICES, ["ticker", "trade_date", "open", "high", "low", "close", "volume"], records)
    logger.info("Upserted %d price rows", len(records))
    return len(records)


def load_macro(engine: Engine, df: pd.DataFrame) -> int:
    records = df.to_dict(orient="records")
    _bulk_upsert(engine, UPSERT_MACRO, ["series_id", "obs_date", "value"], records)
    logger.info("Upserted %d macro rows", len(records))
    return len(records)


def record_pipeline_run(
    engine: Engine,
    pipeline_name: str,
    started_at: datetime,
    status: str,
    rows_loaded: int = 0,
    dbt_tests_passed: int = 0,
    dbt_tests_failed: int = 0,
    error_message: str = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO raw.pipeline_runs
                    (pipeline_name, started_at, finished_at, status, rows_loaded,
                     dbt_tests_passed, dbt_tests_failed, error_message)
                VALUES
                    (:pipeline_name, :started_at, :finished_at, :status, :rows_loaded,
                     :dbt_tests_passed, :dbt_tests_failed, :error_message)
                """
            ),
            {
                "pipeline_name": pipeline_name,
                "started_at": started_at,
                "finished_at": datetime.now(timezone.utc),
                "status": status,
                "rows_loaded": rows_loaded,
                "dbt_tests_passed": dbt_tests_passed,
                "dbt_tests_failed": dbt_tests_failed,
                "error_message": error_message,
            },
        )
    logger.info("Recorded pipeline run: %s (%s)", pipeline_name, status)
