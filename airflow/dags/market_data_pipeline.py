"""
Airflow DAG: market_data_pipeline

extract_load_prices ---\
                         >--> dbt_seed --> dbt_run --> dbt_test --> record_pipeline_run
extract_load_macro  ---/

Design notes (things an interviewer is likely to ask about):
  - Extraction and load are split into their own task per source (prices,
    macro) so a Yahoo Finance outage doesn't block the FRED pull, and each
    can retry/alert independently.
  - dbt is run in three discrete tasks (seed/run/test) rather than one
    "dbt build" task, so a failure surfaces exactly which stage broke in the
    Airflow UI instead of a single opaque failure.
  - record_pipeline_run has trigger_rule="all_done" so we log a row (with
    status=failed and the error) even when an upstream task fails, rather
    than silently having no record of the failed run at all.
  - on_failure_callback is wired to alert_on_failure, which in this portfolio
    version just logs - swap the body for a Slack webhook / PagerDuty call in
    a real deployment.
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.utils.log.logging_mixin import LoggingMixin

DBT_PROJECT_DIR = "/opt/airflow/dbt"
DBT_PROFILES_DIR = "/opt/airflow/dbt"


def alert_on_failure(context):
    """Stub alerting hook - replace with a Slack/PagerDuty/email call.
    Kept as a real callback (not just a comment) so the DAG demonstrates the
    pattern even though this portfolio deployment has nowhere to actually
    send the page."""
    task_id = context["task_instance"].task_id
    dag_id = context["dag"].dag_id
    exception = context.get("exception")
    LoggingMixin().log.error("ALERT: %s.%s failed: %s", dag_id, task_id, exception)


default_args = {
    "owner": "karthick",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "on_failure_callback": alert_on_failure,
}


def _extract_load_prices(**context):
    from extraction import load
    from extraction.extract_prices import extract_prices

    engine = load.get_engine()
    load.ensure_schema(engine)
    df = extract_prices()
    rows = load.load_prices(engine, df)
    context["ti"].xcom_push(key="rows_loaded_prices", value=rows)


def _extract_load_macro(**context):
    from extraction import load
    from extraction.extract_macro import extract_macro

    engine = load.get_engine()
    load.ensure_schema(engine)
    df = extract_macro()
    rows = load.load_macro(engine, df)
    context["ti"].xcom_push(key="rows_loaded_macro", value=rows)


def _record_pipeline_run(**context):
    from extraction import load
    from extraction.pipeline import parse_dbt_test_results

    ti = context["ti"]
    dag_run = context["dag_run"]

    rows_prices = ti.xcom_pull(task_ids="extract_load_prices", key="rows_loaded_prices") or 0
    rows_macro = ti.xcom_pull(task_ids="extract_load_macro", key="rows_loaded_macro") or 0

    failed_upstream = any(
        ti.current_state() == "failed"
        for ti in dag_run.get_task_instances()
        if ti.task_id != "record_pipeline_run"
    )
    dbt_passed, dbt_failed = parse_dbt_test_results()

    engine = load.get_engine()
    load.record_pipeline_run(
        engine,
        pipeline_name="market_data_pipeline",
        started_at=dag_run.start_date,
        status="failed" if failed_upstream else "success",
        rows_loaded=rows_prices + rows_macro,
        dbt_tests_passed=dbt_passed,
        dbt_tests_failed=dbt_failed,
        error_message="One or more upstream tasks failed - see Airflow task logs" if failed_upstream else None,
    )


with DAG(
    dag_id="market_data_pipeline",
    description="Extracts daily market prices + macro indicators, loads to Postgres, transforms with dbt",
    schedule_interval="30 21 * * 1-5",  # 21:30 UTC weekdays - after US market close
    start_date=datetime(2026, 7, 1),
    catchup=False,
    default_args=default_args,
    tags=["market-data", "portfolio-project"],
) as dag:

    extract_load_prices = PythonOperator(
        task_id="extract_load_prices",
        python_callable=_extract_load_prices,
    )

    extract_load_macro = PythonOperator(
        task_id="extract_load_macro",
        python_callable=_extract_load_macro,
    )

    dbt_seed = BashOperator(
        task_id="dbt_seed",
        bash_command=f"dbt seed --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROFILES_DIR}",
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f"dbt run --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROFILES_DIR}",
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f"dbt test --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROFILES_DIR}",
    )

    record_pipeline_run = PythonOperator(
        task_id="record_pipeline_run",
        python_callable=_record_pipeline_run,
        trigger_rule="all_done",
    )

    [extract_load_prices, extract_load_macro] >> dbt_seed >> dbt_run >> dbt_test >> record_pipeline_run
