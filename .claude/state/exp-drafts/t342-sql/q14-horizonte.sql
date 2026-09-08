-- T3.42 q14 — as 6 saidas por horizonte do pai, uma a uma, com o ATR% da decisao.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
select m.symbol,
       (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as barra,
       round((a.supporting_features->'atr'->>'percent')::numeric,5) as atr_pct,
       round(o.r_multiple,4) as r_liq,
       case when (a.supporting_features->'atr'->>'percent')::numeric >= 0.010 then 'sobrevive aos dois pisos'
            when (a.supporting_features->'atr'->>'percent')::numeric >= 0.008 then 'sobrevive so ao piso 0,008'
            else 'cortada pelos dois pisos' end as destino
  from signal_outcomes o join agent_signals a on a.id=o.signal_id
  join markets m on m.id=a.market_id
 where o.meta->>'cohort' = 'replay:d0f77894-1e04-454e-a49f-d9a98d894968'
   and o.result::text = 'expired'
 order by barra;
commit;
