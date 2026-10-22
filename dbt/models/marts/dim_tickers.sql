-- One row per ticker: static reference data (company name, sector) joined
-- with derived stats about the price history we actually have on file.

with prices as (
    select * from {{ ref('stg_prices') }}
),

reference as (
    select * from {{ ref('ticker_reference') }}
),

price_stats as (
    select
        ticker,
        min(trade_date) as first_trade_date,
        count(*) as total_trading_days
    from prices
    group by ticker
),

latest_price as (
    select distinct on (ticker)
        ticker,
        trade_date as last_trade_date,
        close_price as latest_close
    from prices
    order by ticker, trade_date desc
)

select
    r.ticker,
    r.company_name,
    r.sector,
    ps.first_trade_date,
    lp.last_trade_date,
    ps.total_trading_days,
    lp.latest_close
from reference r
left join price_stats ps on r.ticker = ps.ticker
left join latest_price lp on r.ticker = lp.ticker
