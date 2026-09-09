-- T3.62 q10 — populacao, pedagio e expectativa das quatro versoes da familia
-- mean_reversion nas coortes de 16 mercados (31 d). Metodo identico ao da
-- T3.54 q10 / T3.47 q01 (KB-0076 com a correcao aritmetica da notes-T3.40 8b):
-- r_bruto usa o preco de entrada desfeito do slippage (p_entry/1.0006) contra o
-- exit_base, custo_R e o bruto menos o liquido ex-funding, risco% e a distancia
-- ate o stop sobre a entrada. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

with pop as (
  select s.key||' '||sv.version as versao,
         left(split_part(o.meta->>'cohort', ':', 2), 8) as coorte,
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
   where o.meta->>'cohort' in (
           'replay:85418f7a-bc4f-4417-ae84-4311ec1d1375',
           'replay:d82356d9-65dd-4d6d-ab7a-5ed3ce28b755',
           'replay:3684ac55-49a8-4ffb-a670-d4c7419d9870',
           'replay:99fdba70-d6a9-452f-950e-324ea35828b0')
     and o.tracking_state::text = 'terminal'
     and o.r_multiple is not null
), c as (
  select *, (exit_base - p_entry/1.0006)/nullif(risk, 0) as r_bruto,
            (exit_base - p_entry/1.0006)/nullif(risk, 0) - r_exf as custo_r,
            risk/nullif(p_entry, 0) as risco_pct
    from pop
)
select versao, coorte, count(*) as n, count(distinct dia) as dias,
       round((percentile_cont(0.5) within group (order by atr_pct))::numeric, 5) as atr_pct_p50,
       round((percentile_cont(0.5) within group (order by risco_pct))::numeric, 5) as risco_pct_p50,
       round(avg(custo_r), 4) as pedagio_medio_r,
       round((percentile_cont(0.5) within group (order by custo_r))::numeric, 4) as pedagio_p50_r,
       round(avg(r_bruto), 4) as exp_bruta_r,
       round(avg(r_net), 4) as exp_liquida_r,
       round(stddev_samp(r_net), 4) as dp_r,
       round(sum(r_net), 2) as soma_r,
       round(sum(r_net) filter (where r_net > 0)
             / nullif(-sum(r_net) filter (where r_net < 0), 0), 4) as pf_liquido,
       round(100.0 * count(*) filter (where r_net > 0) / count(*), 1) as acerto_pct,
       count(*) filter (where risco_pct < 0.003) as fora_piso_c5,
       count(*) filter (where risco_pct > 0.03) as fora_teto_c5
  from c
 group by 1, 2
 order by 1;
commit;
