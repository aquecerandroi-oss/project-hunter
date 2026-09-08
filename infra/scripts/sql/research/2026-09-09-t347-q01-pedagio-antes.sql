-- T3.47 q01 — a tabela de pedagio ANTES (metodo T3.40/KB-0076): por versao e coorte,
-- ATR% mediana na decisao, risco% (distancia ate o stop / preco de entrada),
-- distribuicao do custo em R (p25/p50/p75) e bruto x liquido. Somente leitura.
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select s.key||' '||sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%'
              then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else o.meta->>'cohort' end as coorte,
         o.tracking_state::text as estado,
         o.result::text as motivo,
         o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         (a.emitted_at)::date as dia
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where s.key in ('mean_reversion','momentum','session_orb')
     and sv.version in ('v1','v2','v3','v6')
     and o.tracking_state::text = 'terminal'
     and o.r_multiple is not null
), c as (
  select *, (exit_base - p_entry/1.0006)/nullif(risk,0) as r_bruto,
            (exit_base - p_entry/1.0006)/nullif(risk,0) - r_exf as custo_r,
            risk/nullif(p_entry,0) as risco_pct
    from pop
)
select versao, coorte, count(*) as n,
       round((percentile_cont(0.5) within group (order by atr_pct))::numeric, 5) as atr_pct_p50,
       round((percentile_cont(0.5) within group (order by risco_pct))::numeric, 5) as risco_pct_p50,
       round((percentile_cont(0.25) within group (order by custo_r))::numeric, 4) as custo_p25,
       round((percentile_cont(0.5) within group (order by custo_r))::numeric, 4) as custo_p50,
       round((percentile_cont(0.75) within group (order by custo_r))::numeric, 4) as custo_p75,
       round(avg(custo_r), 4) as custo_medio,
       round(avg(r_bruto), 4) as exp_bruta_r,
       round(avg(r_net), 4) as exp_liquida_r,
       round(sum(r_net), 2) as soma_r,
       round(sum(r_net) filter (where r_net>0)/nullif(-sum(r_net) filter (where r_net<0),0), 4) as pf_liquido,
       round(sum(r_bruto) filter (where r_bruto>0)/nullif(-sum(r_bruto) filter (where r_bruto<0),0), 4) as pf_bruto,
       count(distinct dia) as dias,
       round(avg(custo_r) - avg(r_bruto), 4) as perda_por_op_r,
       round(100.0*avg(custo_r)/nullif(abs(avg(r_bruto)),0), 1) as pedagio_sobre_bruto_pct
  from c
 group by 1,2
having count(*) >= 5
 order by 1,2;
commit;
