-- T3.65b q02 -- QUANDO cada coorte rodou, e o motivo por coorte nos tres mercados.
-- A q01 achou DOIS desfechos com a MESMA janela (PROMUSDT, 2026-08-14 15:46 ->
-- 19:42) e vereditos diferentes: `c7d138eb` (v10) resolveu, `d82356d9` deu
-- `funding_missing:2026-08-14T17:00:00.002`. Se as coortes rodaram em datas
-- diferentes, a diferenca e a VERSAO DO CODIGO (a T3.65 trocou a moda da janela
-- inteira pela moda dos 3 ultimos gaps), nao o dado.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. as coortes que tocam os tres mercados, com a data de criacao dos desfechos
select a.supporting_features->>'cohort'            as cohort,
       min(o.updated_at)                           as primeiro_gravado,
       max(o.updated_at)                           as ultimo_gravado,
       count(*)                                    as desfechos,
       count(*) filter (where o.r_multiple is null) as nulos
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
 where o.tracking_state = 'terminal'
   and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT')
 group by 1
 order by 2;

-- 2. os dois desfechos gemeos, com created_at
select a.supporting_features->>'cohort' as cohort, o.updated_at,
       o.entry_ts, o.exit_ts, o.meta->>'r_net_reason' as motivo,
       o.meta->'funding'->>'interval_s' as interval_s,
       o.meta->'funding'->>'settlements' as settlements
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
 where o.tracking_state = 'terminal' and m.symbol = 'PROMUSDT'
   and o.entry_ts = timestamptz '2026-08-14 15:46+00'
 order by o.updated_at;

-- 3. TODOS os desfechos dos tres mercados com motivo de funding, com created_at,
--    interval_s lido e a janela -- e a materia-prima do script de pesquisa
select m.symbol, a.supporting_features->>'cohort' as cohort, o.updated_at,
       o.entry_ts, o.exit_ts,
       o.meta->>'r_net_reason' as motivo,
       o.meta->'funding'->>'interval_s' as interval_s
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
 where o.tracking_state = 'terminal'
   and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT')
   and o.meta->>'r_net_reason' is not null
   and split_part(o.meta->>'r_net_reason', ':', 1) in
       ('funding_missing','funding_ambiguous_exit','funding_schedule_unknown')
   and o.entry_ts >= timestamptz '2026-08-08 16:00+00'
 order by m.symbol, o.entry_ts;

-- 4. o interval_s efetivamente lido, por mercado e por semana (so os resolvidos)
select m.symbol,
       date_trunc('week', o.entry_ts)::date        as semana,
       o.meta->'funding'->>'interval_s'            as interval_s,
       count(*)                                    as n
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join markets m on m.id = a.market_id
 where o.tracking_state = 'terminal'
   and m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT')
   and o.entry_ts >= timestamptz '2026-08-08 16:00+00'
 group by 1, 2, 3
 order by 1, 2, 3;

commit;
