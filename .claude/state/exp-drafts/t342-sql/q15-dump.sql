begin transaction isolation level repeatable read read only;
\pset format csv
\pset tuples_only off
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date as dia,
       (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
       o.r_multiple as r_net,
       (o.meta->>'r_ex_funding')::numeric as r_exf,
       o.result::text as motivo
  from signal_outcomes o join agent_signals a on a.id=o.signal_id
  join markets m on m.id=a.market_id
 where o.meta->>'cohort' = 'replay:d0f77894-1e04-454e-a49f-d9a98d894968'
 order by dia, m.symbol;
commit;
