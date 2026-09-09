-- T3.57b q24 — as barras em que AS DUAS decidiram (pareamento por (mercado, barra)).
-- Formato: dia,symbol,bar,r_v1,r_v2,motivo_v1,r_bruto_v1,r_bruto_v2. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
with pop as (
  select case when o.meta->>'cohort' like 'replay:7e498c13%' then 'v2' else 'v1' end as lado,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date::text as dia,
         m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.result::text as motivo, o.r_multiple as r_net,
         round(((o.meta->'progress'->>'exit_base')::numeric
                - (o.meta->'progress'->>'entry')::numeric/1.0006)
               / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0), 6) as r_bruto
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
   where o.meta->>'cohort' in ('replay:7e498c13-d79b-4466-8ff8-30550d75c21e',
                               'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
), a as (select * from pop where lado='v2'), b as (select * from pop where lado='v1')
select b.dia, b.symbol, b.bar, b.r_net as r_v1, a.r_net as r_v2,
       b.motivo as motivo_v1,
       b.r_bruto as r_bruto_v1, a.r_bruto as r_bruto_v2
  from a join b on a.symbol=b.symbol and a.bar=b.bar
 order by b.bar, b.symbol
\g (format=csv)
commit;
