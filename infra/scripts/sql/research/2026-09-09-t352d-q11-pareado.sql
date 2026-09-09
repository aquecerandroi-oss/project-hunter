-- T3.52d q11 — pareamento por (mercado, barra de origem) entre o pai e a filha com portao.
-- Responde: quantas decisoes o portao removeu, quantas sobreviveram identicas e se a
-- filha e mesmo um SUBCONJUNTO do pai (decisao da filha sem contraparte no pai = a
-- maquina de estados do slot divergiu, porque INELIGIBLE nao re-arma nem gasta barreira).
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with d as (
  select s.key as familia, sv.version as versao,
         left(split_part(o.meta->>'cohort', ':', 2), 8) as coorte,
         m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         a.direction::text as lado,
         o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.meta->>'cohort' in (
           'replay:9d99748b-21b9-44a7-8980-32c37b931e6e',
           'replay:5bcfbda1-9365-467e-ad14-583fcfa9ae4b',
           'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd',
           'replay:4a60a3dc-334c-4faa-9790-c321063ff23e')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
), pai as (select * from d where versao in ('v6','v8')),
   filha as (select * from d where versao = 'v11')
select coalesce(p.familia, f.familia) as familia,
       case when p.bar is not null and f.bar is not null then '1 nos dois'
            when p.bar is not null then '2 so no pai (removida pelo portao)'
            else '3 so na filha (o slot divergiu)' end as classe,
       count(*) as n,
       round(avg(p.r_net), 4) as exp_pai_r,
       round(avg(f.r_net), 4) as exp_filha_r,
       count(*) filter (where p.r_net is not null and f.r_net is not null
                          and abs(p.r_net - f.r_net) > 1e-9) as divergem_no_r
  from pai p
  full outer join filha f
    on f.familia = p.familia and f.symbol = p.symbol and f.bar = p.bar and f.lado = p.lado
 group by 1, 2
 order by 1, 2;

-- as decisoes que o portao removeu, com o R que elas teriam dado (o que o portao evitou)
with d as (
  select s.key as familia, sv.version as versao, m.symbol,
         (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
         a.direction::text as lado, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join markets m on m.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.meta->>'cohort' in (
           'replay:9d99748b-21b9-44a7-8980-32c37b931e6e',
           'replay:5bcfbda1-9365-467e-ad14-583fcfa9ae4b',
           'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd',
           'replay:4a60a3dc-334c-4faa-9790-c321063ff23e')
     and o.tracking_state::text = 'terminal' and o.r_multiple is not null
), pai as (select * from d where versao in ('v6','v8')),
   filha as (select * from d where versao = 'v11'),
   rem as (
     select p.* from pai p
      where not exists (select 1 from filha f
                         where f.familia = p.familia and f.symbol = p.symbol
                           and f.bar = p.bar and f.lado = p.lado))
select familia, count(*) as removidas,
       round(avg(r_net), 4) as exp_removidas_r,
       round(sum(r_net), 2) as soma_removidas_r,
       round(avg((exit_base - p_entry/1.0006)/nullif(risk,0)), 4) as exp_bruta_removidas_r,
       round(avg((exit_base - p_entry/1.0006)/nullif(risk,0) - r_exf), 4) as custo_r_removidas,
       round(100.0 * count(*) filter (where r_net > 0) / count(*), 1) as acerto_pct
  from rem group by 1 order by 1;

commit;
