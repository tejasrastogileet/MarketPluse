"""
Streamlit dashboard - the live, public-facing piece of the platform.

Two views:
  1. Pipeline Health  - is the data fresh, did the last run succeed, dbt test
     pass rate over time. This is what an interviewer clicking the live link
     sees first, and it's the part that makes the DE/AE/BIE story concrete:
     "here's the pipeline actually running, not just a diagram of it."
  2. Market Analytics  - the business-facing payoff on top of the same marts:
     price trends, cross-ticker return comparison, sector performance, and
     risk-tier / volatility views.

Run locally with:  streamlit run dashboard/app.py
Deploy on Streamlit Community Cloud pointed at your live Postgres (see
README.md's "Deploying the live dashboard" section) - no code changes needed,
only the POSTGRES_* secrets differ between local and deployed.
"""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import text

sys.path.append(str(Path(__file__).resolve().parent.parent))

from dashboard.theme import (
    apply_theme,
    CATEGORICAL,
    SECTOR_COLOR,
    RISK_TIER_COLOR,
    SEQUENTIAL_BLUE,
    TEXT_MUTED,
)
from extraction.load import get_engine

st.set_page_config(page_title="MarketPulse", layout="wide")
apply_theme()


@st.cache_resource
def _engine():
    return get_engine()


@st.cache_data(ttl=300)
def load_df(query: str, **params) -> pd.DataFrame:
    with _engine().connect() as conn:
        return pd.read_sql(text(query), conn, params=params)


def pipeline_health_view():
    st.header("Pipeline Health")

    runs = load_df(
        """
        select run_id, pipeline_name, started_at, finished_at, status,
               rows_loaded, dbt_tests_passed, dbt_tests_failed, error_message
        from raw.pipeline_runs
        order by started_at desc
        limit 30
        """
    )

    if runs.empty:
        st.warning("No pipeline runs recorded yet. Run `python -m extraction.pipeline` at least once.")
        return

    latest = runs.iloc[0]
    freshness = load_df("select max(trade_date) as latest_trade_date from marts.fct_daily_returns")
    latest_trade_date = freshness["latest_trade_date"].iloc[0] if not freshness.empty else None

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Last run status", "✅ Success" if latest["status"] == "success" else "❌ Failed")
    col2.metric("Rows loaded (last run)", f"{int(latest['rows_loaded'] or 0):,}")
    col3.metric(
        "dbt tests (last run)",
        f"{int(latest['dbt_tests_passed'] or 0)} passed",
        delta=f"-{int(latest['dbt_tests_failed'] or 0)} failed" if latest["dbt_tests_failed"] else None,
        delta_color="inverse",
    )
    col4.metric("Latest data as of", str(latest_trade_date) if latest_trade_date is not None else "—")

    if latest["status"] != "success" and latest["error_message"]:
        st.error(f"Last run error: {latest['error_message']}")

    st.subheader("Run history")
    runs_display = runs.copy()
    runs_display["status_icon"] = runs_display["status"].map({"success": "✅", "failed": "❌"}).fillna("—")
    st.dataframe(
        runs_display[
            ["status_icon", "started_at", "finished_at", "rows_loaded", "dbt_tests_passed", "dbt_tests_failed"]
        ].rename(
            columns={
                "status_icon": "Status",
                "started_at": "Started",
                "finished_at": "Finished",
                "rows_loaded": "Rows Loaded",
                "dbt_tests_passed": "Tests Passed",
                "dbt_tests_failed": "Tests Failed",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("dbt test pass rate over time")
    trend = runs.sort_values("started_at").copy()
    trend["pass_rate_pct"] = 100 * trend["dbt_tests_passed"] / (
        trend["dbt_tests_passed"] + trend["dbt_tests_failed"]
    ).replace(0, pd.NA)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=trend["started_at"],
            y=trend["pass_rate_pct"],
            mode="lines+markers",
            line=dict(width=2, color=CATEGORICAL[0]),
            marker=dict(size=8),
            name="Pass rate",
        )
    )
    fig.update_layout(yaxis=dict(title="dbt test pass rate (%)", range=[0, 105]), height=320, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)


def market_analytics_view():
    st.header("Market Analytics")

    tickers_df = load_df("select ticker, company_name, sector from marts.dim_tickers order by ticker")
    if tickers_df.empty:
        st.warning("No tickers found. Run `dbt seed` and `dbt run` at least once.")
        return

    all_sectors = sorted(tickers_df["sector"].dropna().unique().tolist())
    with st.sidebar:
        st.subheader("Filters")
        sector_filter = st.multiselect("Sector", all_sectors, default=all_sectors)
        eligible = tickers_df[tickers_df["sector"].isin(sector_filter)]["ticker"].tolist()
        default_selection = eligible[:5]  # keep the comparison chart within the safe 8-series categorical range
        selected_tickers = st.multiselect(
            "Tickers to compare (max 8)",
            eligible,
            default=default_selection,
            max_selections=8,
        )

    if not selected_tickers:
        st.info("Select at least one ticker from the sidebar.")
        return

    returns = load_df(
        """
        select ticker, trade_date, close_price, daily_return_pct, cumulative_return_pct, sma_20, sma_50
        from marts.fct_daily_returns
        where ticker = any(:tickers)
        order by trade_date
        """,
        tickers=selected_tickers,
    )

    st.subheader("Cumulative return comparison")
    fig = go.Figure()
    for i, ticker in enumerate(selected_tickers):
        series = returns[returns["ticker"] == ticker]
        fig.add_trace(
            go.Scatter(
                x=series["trade_date"],
                y=series["cumulative_return_pct"],
                mode="lines",
                name=ticker,
                line=dict(width=2, color=CATEGORICAL[i % len(CATEGORICAL)]),
            )
        )
    fig.update_layout(yaxis=dict(title="Cumulative return (%)"), height=420)
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Price with 20/50-day moving averages")
    focus_ticker = st.selectbox("Ticker detail", selected_tickers)
    detail = returns[returns["ticker"] == focus_ticker]
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=detail["trade_date"], y=detail["close_price"], name="Close",
                               line=dict(width=2, color=CATEGORICAL[0])))
    fig2.add_trace(go.Scatter(x=detail["trade_date"], y=detail["sma_20"], name="SMA 20",
                               line=dict(width=2, color=CATEGORICAL[2], dash="dot")))
    fig2.add_trace(go.Scatter(x=detail["trade_date"], y=detail["sma_50"], name="SMA 50",
                               line=dict(width=2, color=CATEGORICAL[5], dash="dot")))
    fig2.update_layout(yaxis=dict(title="Price ($)"), height=420)
    st.plotly_chart(fig2, use_container_width=True)

    col_a, col_b = st.columns(2)

    with col_a:
        st.subheader("Avg. cumulative return by sector")
        sector_perf = load_df(
            """
            select t.sector, avg(r.cumulative_return_pct) as avg_cumulative_return_pct
            from marts.fct_daily_returns r
            join marts.dim_tickers t on r.ticker = t.ticker
            where r.trade_date = (select max(trade_date) from marts.fct_daily_returns)
            group by t.sector
            order by avg_cumulative_return_pct desc
            """
        )
        fig3 = go.Figure(
            go.Bar(
                x=sector_perf["avg_cumulative_return_pct"],
                y=sector_perf["sector"],
                orientation="h",
                marker_color=[SECTOR_COLOR.get(s, TEXT_MUTED) for s in sector_perf["sector"]],
            )
        )
        fig3.update_layout(xaxis=dict(title="Avg. cumulative return (%)"), height=380)
        st.plotly_chart(fig3, use_container_width=True)

    with col_b:
        st.subheader("Risk tier distribution (latest day)")
        risk_dist = load_df(
            """
            select risk_tier, count(*) as n
            from marts.fct_volatility
            where trade_date = (select max(trade_date) from marts.fct_volatility)
              and risk_tier is not null
            group by risk_tier
            """
        )
        order = ["LOW", "MEDIUM", "HIGH"]
        risk_dist["risk_tier"] = pd.Categorical(risk_dist["risk_tier"], categories=order, ordered=True)
        risk_dist = risk_dist.sort_values("risk_tier")
        fig4 = go.Figure(
            go.Bar(
                x=risk_dist["risk_tier"],
                y=risk_dist["n"],
                marker_color=[RISK_TIER_COLOR[t] for t in risk_dist["risk_tier"]],
            )
        )
        fig4.update_layout(yaxis=dict(title="Number of tickers"), height=380)
        st.plotly_chart(fig4, use_container_width=True)

    st.subheader("Rolling 30-day annualized volatility (selected tickers)")
    vol = load_df(
        """
        select ticker, trade_date, rolling_30d_annualized_volatility_pct
        from marts.fct_volatility
        where ticker = any(:tickers) and rolling_30d_annualized_volatility_pct is not null
        order by trade_date
        """,
        tickers=selected_tickers,
    )
    pivot = vol.pivot(index="ticker", columns="trade_date", values="rolling_30d_annualized_volatility_pct")
    fig5 = go.Figure(
        go.Heatmap(
            z=pivot.values,
            x=pivot.columns,
            y=pivot.index,
            colorscale=SEQUENTIAL_BLUE,
            colorbar=dict(title="Ann. vol (%)"),
        )
    )
    fig5.update_layout(height=max(300, 40 * len(pivot)))
    st.plotly_chart(fig5, use_container_width=True)


def main():
    st.title("MarketPulse")
    st.caption(
        "A market data engineering platform — Airflow-orchestrated ETL + dbt transformations over "
        "daily stock prices and macro indicators. See the GitHub repo for the DAG, dbt models, and architecture."
    )
    view = st.radio("View", ["Pipeline Health", "Market Analytics"], horizontal=True, label_visibility="collapsed")
    st.divider()
    if view == "Pipeline Health":
        pipeline_health_view()
    else:
        market_analytics_view()


if __name__ == "__main__":
    main()
