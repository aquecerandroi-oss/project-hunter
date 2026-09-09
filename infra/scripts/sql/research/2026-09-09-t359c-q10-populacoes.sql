-- T3.59c/T3.57b q10 — populacoes dos quatro bracos da EXP-0023 + trendline_bounce v1,
-- contra os pais, mesma janela (31 d) e mesmos 4 mercados.
-- Metodo identico ao da T3.52d q10 / T3.54 q10. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select s.key||' '||sv.version as versao,
         left(split_part(o.meta->>'cohort', ':', 2), 8) as coorte,
         m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         o.result::text as motivo,
         o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz::date as dia
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.meta->>'cohort' in (
           'replay:4ed2ec88-c4cd-4fa2-aeb9-eb432fd271dd',
           'replay:29bc81bf-26ea-4255-a9cb-46bab6d7c99f',
           'replay:fbb65b47-d8dc-4abb-b64f-0ef1f24faf3e',
           'replay:9a48a940-5957-4b07-a9c4-4d4521adc907',
           'replay:7e498c13-d79b-4466-8ff8-30550d75c21e',
           'replay:71c76d86-ceb0-4d48-b3be-88c3c055061e',
           'replay:4a60a3dc-334c-4faa-9790-c321063ff23e',
           'replay:d78c14d1-b4c5-424a-8f31-a43100744bb4')
     and o.tracking_state::text = 'terminal'
     and o.r_multiple is not null
), c as (
  select *, (exit_base - p_entry/1.0006)/nullif(risk, 0) as r_bruto,
            (exit_base - p_entry/1.0006)/nullif(risk, 0) - r_exf as custo_r,
            risk/nullif(p_entry, 0) as risco_pct
    from pop
)
select versao, coorte, count(*) as n, count(distinct dia) as dias,
       count(distinct symbol) as mercados,
       min(bar)::date as primeira, max(bar)::date as ultima,
       round(avg(custo_r), 4) as pedagio_r,
       round(avg(r_bruto), 4) as exp_bruta_r,
       round(avg(r_net), 4) as exp_liquida_r,
       round(sum(r_net), 3) as soma_r,
       round(sum(r_net) filter (where r_net > 0)
             / nullif(-sum(r_net) filter (where r_net < 0), 0), 4) as pf_liquido,
       round(100.0 * count(*) filter (where r_net > 0) / count(*), 1) as acerto_pct
  from c
 group by 1, 2
 order by 1, 2;

-- desfechos por motivo
select s.key||' '||sv.version as versao,
       left(split_part(o.meta->>'cohort', ':', 2), 8) as coorte,
       o.tracking_state::text as estado, coalesce(o.result::text,'-') as motivo, count(*)
  from signal_outcomes o
  join agent_signals a on a.id = o.signal_id
  join strategy_versions sv on sv.id = a.strategy_version_id
  join strategies s on s.id = sv.strategy_id
 where o.meta->>'cohort' in (
         'replay:4ed2ec88-c4cd-4fa2-aeb9-eb432fd271dd',
         'replay:29bc81bf-26ea-4255-a9cb-46bab6d7c99f',
         'replay:fbb65b47-d8dc-4abb-b64f-0ef1f24faf3e',
         'replay:9a48a940-5957-4b07-a9c4-4d4521adc907',
         'replay:7e498c13-d79b-4466-8ff8-30550d75c21e')
 group by 1,2,3,4 order by 1,2,3,4;
commit;
