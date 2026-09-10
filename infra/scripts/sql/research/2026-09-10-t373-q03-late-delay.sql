-- T3.73 q03 -- O QUE `late:delay` MEDE DE VERDADE: O ATRASO ENTRE O FECHAMENTO
-- DA BARRA DE REFERENCIA E A DECISAO (nao o preco fugindo da zona).
-- `plan_entry` (plan.py): entry_bar_open = proximo minuto apos decision_at;
-- delay_s = entry_bar_open - source_bar_close; late:delay se delay_s > max_entry_delay_s.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. a forma do meta (uma linha de exemplo, so as chaves)
select jsonb_object_keys(o.meta) as chave, count(*) as n
  from signal_outcomes o
 where o.tracking_state = 'no_entry'
 group by 1 order by 2 desc limit 20;

-- 2. distribuicao do atraso decisao-menos-fechamento por dia UTC
select date_trunc('day', a.emitted_at)::date as dia,
       count(*) as sinais,
       round(avg(extract(epoch from (a.emitted_at - (a.supporting_features->>'observation_ts')::timestamptz)))::numeric, 1) as atraso_medio_s,
       round((percentile_cont(0.5) within group (order by extract(epoch from (a.emitted_at - (a.supporting_features->>'observation_ts')::timestamptz))))::numeric, 1) as mediana_s,
       round((percentile_cont(0.95) within group (order by extract(epoch from (a.emitted_at - (a.supporting_features->>'observation_ts')::timestamptz))))::numeric, 1) as p95_s,
       round(max(extract(epoch from (a.emitted_at - (a.supporting_features->>'observation_ts')::timestamptz)))::numeric, 1) as max_s
  from agent_signals a
 where a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1 order by 1;

-- 3. quantas VERSOES ativas o roster tinha em cada dia (o custo por barra)
select date_trunc('day', a.emitted_at)::date as dia,
       count(distinct a.strategy_version_id) as versoes_que_decidiram,
       count(distinct a.market_id) as mercados
  from agent_signals a
 where a.emitted_at >= '2026-09-01 00:00:00+00'
 group by 1 order by 1;

-- 4. delay_s gravado no proprio plano de entrada, por dia e por motivo
select date_trunc('day', a.emitted_at)::date as dia,
       coalesce(o.no_entry_reason, 'entrou') as motivo,
       count(*) as n,
       round(avg((o.meta->'entry_plan'->>'delay_s')::numeric), 1) as delay_medio_s,
       max((o.meta->'entry_plan'->>'delay_s')::numeric) as delay_max_s
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
 where o.meta->>'cohort' = 'prospective'
   and a.emitted_at >= '2026-09-06 00:00:00+00'
   and o.meta ? 'entry_plan'
 group by 1, 2 order by 1, 3 desc;

commit;
