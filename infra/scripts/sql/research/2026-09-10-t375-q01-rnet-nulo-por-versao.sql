-- T3.75 q01 -- `r_multiple` NULO POR VERSAO NAS TRES COORTES DA T3.62b, DEPOIS DO BACKFILL.
-- O ponto desta consulta e provar duas coisas ao mesmo tempo:
--   1. os desfechos JA PERSISTIDOS **nao** se recalculam sozinhos -- a contagem
--      de nulos por versao continua identica a da T3.62b SS3 (v10 498, v1 288+1,
--      v2 126+1) mesmo com `funding_rates` agora cobrindo 2026-06-12 -> hoje;
--   2. quantos deles PASSARIAM a resolver se alguem rodasse a recomputacao
--      (`infra/scripts/recompute_funding.py`), medido pelo mesmo criterio que
--      `resolve_funding` usa para dizer `funding_schedule_unknown`: a cadencia
--      so e legivel com >= 2 instantes distintos de assentamento na janela que
--      `settle()` carrega, que e [entry_ts - 3 dias, exit_ts + 2 s]
--      (`settle._CADENCE_LOOKBACK`, `funding.MATCH_TOLERANCE`).
-- Isto e uma PREVISAO por contagem, nao a recomputacao: um desfecho com cadencia
-- legivel ainda pode cair em `funding_missing` / `funding_ambiguous_exit`.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. cobertura de R_net por versao (o numero do K5), nas tres coortes
with coorte(rotulo, cohort) as (
  values ('v10', 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'),
         ('v1',  'replay:fa005985-0b55-4820-904c-8ada589e441c'),
         ('v2',  'replay:da706026-319a-451e-950e-7728ca9ae563')
), pop as (
  select c.rotulo,
         o.r_multiple,
         o.meta->>'r_net_reason' as motivo
    from agent_signals a
    join coorte c on c.cohort = a.supporting_features->>'cohort'
    join signal_outcomes o on o.signal_id = a.id
   where o.tracking_state = 'terminal'
)
select rotulo,
       count(*)                                        as terminais,
       count(r_multiple)                               as com_r_net,
       round(100.0 * count(r_multiple) / count(*), 2)  as cobertura_pct,
       count(*) filter (where r_multiple is null)      as nulos
  from pop
 group by 1
 order by 1;

-- 2. o motivo dos nulos, por versao
with coorte(rotulo, cohort) as (
  values ('v10', 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'),
         ('v1',  'replay:fa005985-0b55-4820-904c-8ada589e441c'),
         ('v2',  'replay:da706026-319a-451e-950e-7728ca9ae563')
)
select c.rotulo,
       split_part(o.meta->>'r_net_reason', ':', 1) as motivo,
       count(*)                                    as n
  from agent_signals a
  join coorte c on c.cohort = a.supporting_features->>'cohort'
  join signal_outcomes o on o.signal_id = a.id
 where o.tracking_state = 'terminal' and o.r_multiple is null
 group by 1, 2
 order by 1, 3 desc;

-- 3. quantos nulos ja teriam cadencia legivel se a recomputacao rodasse
with coorte(rotulo, cohort) as (
  values ('v10', 'replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3'),
         ('v1',  'replay:fa005985-0b55-4820-904c-8ada589e441c'),
         ('v2',  'replay:da706026-319a-451e-950e-7728ca9ae563')
), nulos as (
  select c.rotulo,
         o.signal_id,
         a.market_id,
         o.entry_ts,
         o.exit_ts,
         split_part(o.meta->>'r_net_reason', ':', 1) as motivo
    from agent_signals a
    join coorte c on c.cohort = a.supporting_features->>'cohort'
    join signal_outcomes o on o.signal_id = a.id
   where o.tracking_state = 'terminal' and o.r_multiple is null
     and o.entry_ts is not null and o.exit_ts is not null
)
select n.rotulo,
       n.motivo,
       count(*)                                  as nulos,
       count(*) filter (where s.instantes >= 2)  as cadencia_legivel,
       count(*) filter (where s.instantes < 2)   as ainda_cega
  from nulos n
  cross join lateral (
    select count(distinct date_trunc('second', f.funding_time)) as instantes
      from funding_rates f
     where f.market_id = n.market_id
       and f.funding_time >= n.entry_ts - interval '3 days'
       and f.funding_time <= n.exit_ts + interval '2 seconds'
  ) s
 group by 1, 2
 order by 1, 3 desc;

commit;
