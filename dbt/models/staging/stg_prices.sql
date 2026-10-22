-- Cleans and standardizes raw OHLCV data: dedupes, casts types, drops
-- clearly bad rows (non-positive prices, high < low) before anything
-- downstream builds on top of it.

with source as (
    select * from {{ source('raw', 'stock_prices') }}
),

deduped as (
    select
        ticker,
        trade_date,
        open::numeric(14, 4)   as open_price,
        high::numeric(14, 4)   as high_price,
        low::numeric(14, 4)    as low_price,
        close::numeric(14, 4)  as close_price,
        volume::bigint         as volume,
        loaded_at,
        row_number() over (
            partition by ticker, trade_date
            order by loaded_at desc
        ) as rn
    from source
)

select
    ticker,
    trade_date,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    loaded_at
from deduped
where rn = 1
  and close_price > 0
  and high_price >= low_price
