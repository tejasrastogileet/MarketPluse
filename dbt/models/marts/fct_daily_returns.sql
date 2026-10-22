-- Daily and cumulative returns, plus simple moving averages, per ticker.
-- This is the core analytical table the Streamlit dashboard's price charts
-- read from, and the table the future portfolio-risk project (VaR, exposure)
-- will build on top of.

with prices as (
    select * from {{ ref('stg_prices') }}
),

with_prev as (
    select
        ticker,
        trade_date,
        close_price,
        volume,
        lag(close_price) over (partition by ticker order by trade_date) as prev_close,
        first_value(close_price) over (partition by ticker order by trade_date) as first_close
    from prices
)

select
    ticker,
    trade_date,
    close_price,
    volume,
    prev_close,
    case
        when prev_close is null or prev_close = 0 then null
        else round((close_price / prev_close - 1) * 100, 4)
    end as daily_return_pct,
    case
        when first_close is null or first_close = 0 then null
        else round((close_price / first_close - 1) * 100, 4)
    end as cumulative_return_pct,
    round(avg(close_price) over (
        partition by ticker order by trade_date
        rows between 19 preceding and current row
    ), 4) as sma_20,
    round(avg(close_price) over (
        partition by ticker order by trade_date
        rows between 49 preceding and current row
    ), 4) as sma_50,
    round(avg(close_price) over (
        partition by ticker order by trade_date
        rows between 199 preceding and current row
    ), 4) as sma_200
from with_prev
