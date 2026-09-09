-- T3.65 q01 — varredura geral: algum mercado MONITORADO teve o gap dominante
-- entre settlements de funding mudando desde 2026-09-01 (não só os nove TradFi
-- do anúncio, que a q00 já mostrou ausentes do nosso `markets`)? SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;

select now() as read_at;

with gaps as (
  select m.symbol,
         fr.funding_time,
         extract(epoch from (
           fr.funding_time - lag(fr.funding_time) over (partition by m.id order by fr.funding_time)
         ))::bigint as gap_s
    from funding_rates fr
    join markets m on m.id = fr.market_id
   where m.is_monitored
     and m.market_type = 'perpetual'
     and fr.funding_time >= timestamptz '2026-08-25 00:00:00+00'
),
rounded as (
  select symbol, funding_time,
         -- collapse jitter: round to the nearest 5 minutes
         round(gap_s / 300.0) * 300 as gap_r
    from gaps
   where gap_s is not null and gap_s > 0
),
by_half as (
  -- before/after 2026-09-01 12:00Z as a coarse split; the real T3.65 window is
  -- 2026-09-04 08:15Z, this just buckets enough history to see a shift
  select symbol,
         mode() within group (order by gap_r) filter (
           where funding_time <  timestamptz '2026-09-04 08:15:00+00') as moda_antes,
         mode() within group (order by gap_r) filter (
           where funding_time >= timestamptz '2026-09-04 08:15:00+00') as moda_depois,
         count(*) filter (where funding_time <  timestamptz '2026-09-04 08:15:00+00') as n_antes,
         count(*) filter (where funding_time >= timestamptz '2026-09-04 08:15:00+00') as n_depois
    from rounded
   group by symbol
)
select *
  from by_half
 where moda_antes is distinct from moda_depois
   and n_antes >= 2 and n_depois >= 2
 order by symbol;

commit;
