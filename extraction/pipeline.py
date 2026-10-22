"""
Single entrypoint that runs the full pipeline: extract -> load -> dbt build
-> dbt test -> record run metadata.

This module is intentionally the *only* place that encodes "what the
pipeline does" - both the Airflow DAG (airflow/dags/market_data_pipeline.py)
and the GitHub Actions scheduled workflow (.github/workflows/refresh_data.yml)
call into these same functions rather than duplicating logic, so the two
execution paths can never silently drift apart.

Usage:
    python -m extraction.pipeline                # full run
    python -m extraction.pipeline --skip-dbt      # extract/load only (fast dev loop)
"""
import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from extraction.extract_prices import extract_prices
from extraction.extract_macro import extract_macro
from extraction import load

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
DBT_PROJECT_DIR = REPO_ROOT / "dbt"


def run_dbt(command: list) -> subprocess.CompletedProcess:
    """Runs a dbt CLI command against the dbt/ project directory."""
    full_cmd = ["dbt"] + command + ["--project-dir", str(DBT_PROJECT_DIR)]
    logger.info("Running: %s", " ".join(full_cmd))
    return subprocess.run(full_cmd, capture_output=True, text=True)


def parse_dbt_test_results():
    """Reads dbt's run_results.json after `dbt test` to get pass/fail counts
    for the pipeline_runs table, instead of just a binary success/fail."""
    results_path = DBT_PROJECT_DIR / "target" / "run_results.json"
    if not results_path.exists():
        return 0, 0
    data = json.loads(results_path.read_text())
    passed = sum(1 for r in data.get("results", []) if r.get("status") == "pass")
    failed = sum(1 for r in data.get("results", []) if r.get("status") in ("fail", "error"))
    return passed, failed


def run_pipeline(skip_dbt: bool = False) -> None:
    started_at = datetime.now(timezone.utc)
    engine = load.get_engine()
    load.ensure_schema(engine)

    rows_loaded = 0
    dbt_passed, dbt_failed = 0, 0

    try:
        prices = extract_prices()
        rows_loaded += load.load_prices(engine, prices)

        macro = extract_macro()
        rows_loaded += load.load_macro(engine, macro)

        if not skip_dbt:
            seed_result = run_dbt(["seed"])
            if seed_result.returncode != 0:
                logger.error(seed_result.stdout + seed_result.stderr)
                raise RuntimeError("dbt seed failed")

            run_result = run_dbt(["run"])
            if run_result.returncode != 0:
                logger.error(run_result.stdout + run_result.stderr)
                raise RuntimeError("dbt run failed")

            test_result = run_dbt(["test"])
            dbt_passed, dbt_failed = parse_dbt_test_results()
            logger.info("dbt test: %d passed, %d failed", dbt_passed, dbt_failed)
            if test_result.returncode != 0:
                # We still record the run (with the failure counts) rather than
                # swallowing it, but we DO fail the pipeline - bad data quality
                # should never silently ship to the dashboard.
                raise RuntimeError(f"dbt test failed ({dbt_failed} failing test(s))")

        load.record_pipeline_run(
            engine,
            pipeline_name="market_data_pipeline",
            started_at=started_at,
            status="success",
            rows_loaded=rows_loaded,
            dbt_tests_passed=dbt_passed,
            dbt_tests_failed=dbt_failed,
        )
        logger.info("Pipeline run succeeded (%d rows loaded)", rows_loaded)

    except Exception as exc:
        load.record_pipeline_run(
            engine,
            pipeline_name="market_data_pipeline",
            started_at=started_at,
            status="failed",
            rows_loaded=rows_loaded,
            dbt_tests_passed=dbt_passed,
            dbt_tests_failed=dbt_failed,
            error_message=str(exc),
        )
        logger.exception("Pipeline run failed")
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-dbt", action="store_true", help="Extract/load only, skip dbt seed/run/test")
    args = parser.parse_args()
    try:
        run_pipeline(skip_dbt=args.skip_dbt)
    except Exception:
        sys.exit(1)
