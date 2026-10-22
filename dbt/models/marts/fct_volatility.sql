-- Rolling 30-trading-day annualized volatility per ticker, with a simple
-- risk-tier bucket. Feeds the dashboard's risk view today, and is the same
-- table the planned portfolio/market-risk-analytics project (VaR, exposure)
-- will extend rather than duplicate.

with returns as (
    select ticker, trade_date, daily_return_pct
    from {{ ref('fct_daily_returns') }}
    where daily_return_pct is not null
),

rolling as (
    select
        ticker,
        trade_date,
        daily_return_pct,
        stddev_samp(daily_return_pct / 100.0) over (
            partition by ticker order by trade_date
            rows between 29 preceding and current row
        ) as rolling_30d_stddev,
        count(*) over (
            partition by ticker order by trade_date
            rows between 29 preceding and current row
        ) as window_size
    from returns
)

select
    ticker,
    trade_date,
    -- annualize a daily-return stdev by sqrt(252 trading days/year); this is
    -- the standard convention for quoting equity volatility.
    round((rolling_30d_stddev * sqrt(252) * 100)::numeric, 4) as rolling_30d_annualized_volatility_pct,
    case
        when window_size < 30 then null  -- not enough history yet for a stable estimate
        when rolling_30d_stddev * sqrt(252) * 100 < 20 then 'LOW'
        when rolling_30d_stddev * sqrt(252) * 100 < 40 then 'MEDIUM'
        else 'HIGH'
    end as risk_tier
from rolling
