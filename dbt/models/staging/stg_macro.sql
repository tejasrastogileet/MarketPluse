-- Cleans raw macro indicator observations and forward-fills onto a daily
-- grid isn't done here (that's a mart concern) - staging just standardizes
-- types and dedupes.

with source as (
    select * from {{ source('raw', 'macro_indicators') }}
),

deduped as (
    select
        series_id,
        obs_date,
        value::numeric(14, 4) as value,
        loaded_at,
        row_number() over (
            partition by series_id, obs_date
            order by loaded_at desc
        ) as rn
    from source
)

select
    series_id,
    obs_date,
    value,
    loaded_at
from deduped
where rn = 1
