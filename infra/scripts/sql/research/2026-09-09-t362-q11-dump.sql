-- T3.62 q11 — dump por decisao das quatro coortes de 16 mercados (CSV para o
-- bootstrap por blocos de dia, as metades, o contraste 4-originais vs 12-novos e
-- a decomposicao por mercado). Uma linha por desfecho terminal com R conhecido.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format csv
select s.key||' '||sv.version as versao,
       m.symbol as mercado,
       (a.emitted_at)::date as dia,
       extract(hour from a.emitted_at)::int as hora_utc,
       a.emitted_at,
       o.result::text as resultado,
       o.r_multiple as r_net,
       (o.meta->>'r_ex_funding')::numeric as r_exf,
       (o.meta->'progress'->>'entry')::numeric as p_entry,
       (o.meta->'progress'->>'exit_base')::numeric as exit_base,
       (o.meta->'excursions'->>'initial_risk')::numeric as risk,
       (a.supporting_features->'atr'->>'percent')::numeric as atr_pct
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where o.meta->>'cohort' in (
         'replay:85418f7a-bc4f-4417-ae84-4311ec1d1375',
         'replay:d82356d9-65dd-4d6d-ab7a-5ed3ce28b755',
         'replay:3684ac55-49a8-4ffb-a670-d4c7419d9870',
         'replay:99fdba70-d6a9-452f-950e-324ea35828b0')
   and o.tracking_state::text = 'terminal'
   and o.r_multiple is not null
 order by 1, 5;
commit;
