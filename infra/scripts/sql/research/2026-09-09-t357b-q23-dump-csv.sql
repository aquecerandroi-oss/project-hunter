-- T3.57b q23 — dois dumps CSV para os estimadores de bloco de dia.
-- (1) populacoes inteiras: versao,dia,symbol,r_net,r_bruto  (formato de t352d/duas_populacoes.py)
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
with pop as (
  select case when o.meta->>'cohort' like 'replay:7e498c13%'
              then 'trendline_bounce v1' else 'trendline_breakout v1' end as versao,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date::text as dia,
         m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.r_multiple as r_net,
         round(((o.meta->'progress'->>'exit_base')::numeric
                - (o.meta->'progress'->>'entry')::numeric/1.0006)
               / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0), 6) as r_bruto
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
   where o.meta->>'cohort' in ('replay:7e498c13-d79b-4466-8ff8-30550d75c21e',
                               'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
)
select versao, dia, symbol, r_net, r_bruto from pop order by versao, bar, symbol
\g (format=csv)
commit;
