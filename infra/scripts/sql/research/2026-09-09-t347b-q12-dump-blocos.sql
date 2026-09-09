-- T3.47b q12 — dump por decisao (dia, ATR%, R liquido) das duas coortes de piso 0,006,
-- para o bootstrap de blocos de dia da T3.42 (`t342-blocos/blocos.py`, contraste
-- populacao-contra-populacao: a variante e superconjunto exato do pai, provado em q11).
-- Somente leitura. Saida em CSV pelo stdout.
begin transaction isolation level repeatable read read only;
\pset format csv
\pset tuples_only off
select to_char((o.meta->'entry_plan'->>'source_bar_close')::timestamptz, 'YYYY-MM-DD') as dia,
       (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
       o.r_multiple as r_net,
       left(split_part(o.meta->>'cohort',':',2),8) as coorte
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
 where o.meta->>'cohort' = :'coorte'
   and o.r_multiple is not null
 order by dia, atr_pct;
commit;
