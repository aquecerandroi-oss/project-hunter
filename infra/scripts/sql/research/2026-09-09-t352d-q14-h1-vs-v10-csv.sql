-- T3.52d/T3.54c q14 — dump por decisao de mean_reversion_h1 v1 e mean_reversion v10
-- para o bootstrap de blocos de dia. O dia e o da BARRA DE ORIGEM (o relogio da T3.53).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
select s.key||' '||sv.version as versao,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date::text as dia,
       m.symbol,
       o.r_multiple as r_net,
       round((o.meta->'progress'->>'exit_base')::numeric
             - (o.meta->'progress'->>'entry')::numeric/1.0006, 10)
         / nullif((o.meta->'excursions'->>'initial_risk')::numeric, 0) as r_bruto
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where o.meta->>'cohort' in ('replay:fc9e2506-b812-4f07-a2fa-89ce4671a8bf',
                             'replay:71c76d86-ceb0-4d48-b3be-88c3c055061e')
   and o.tracking_state::text = 'terminal' and o.r_multiple is not null
 order by versao, dia, m.symbol
\g (format=csv)
commit;
