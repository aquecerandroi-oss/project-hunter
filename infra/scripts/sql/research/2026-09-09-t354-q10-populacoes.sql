-- T3.54 q10 — populacoes, pedagio e expectativa das variantes de 1 h contra os
-- pais de 15 m, por versao e coorte de replay. Metodo identico ao da T3.47 q01
-- (KB-0076 com a correcao aritmetica da notes-T3.40 8b): risco% e a distancia
-- ate o stop sobre o preco de entrada, custo_R e o bruto menos o liquido.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;
with pop as (
  select s.key||' '||sv.version as versao,
         'replay:'||left(split_part(o.meta->>'cohort', ':', 2), 8) as coorte,
         sv.default_parameters->>'atr_timeframe' as atr_tf,
         sv.default_parameters->>'atr_bars' as atr_bars,
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
   where s.key in ('mean_reversion', 'momentum')
     and sv.version in ('v6', 'v8', 'v9', 'v10')
     and o.meta->>'cohort' like 'replay:%'
     and o.tracking_state::text = 'terminal'
     and o.r_multiple is not null
), c as (
  select *, (exit_base - p_entry/1.0006)/nullif(risk, 0) as r_bruto,
            (exit_base - p_entry/1.0006)/nullif(risk, 0) - r_exf as custo_r,
            risk/nullif(p_entry, 0) as risco_pct
    from pop
)
select versao, coorte, atr_tf, atr_bars, count(*) as n,
       count(distinct dia) as dias,
       round((percentile_cont(0.5) within group (order by atr_pct))::numeric, 5) as atr_pct_p50,
       round((percentile_cont(0.5) within group (order by risco_pct))::numeric, 5) as risco_pct_p50,
       round(avg(custo_r), 4) as custo_r_medio,
       round((percentile_cont(0.5) within group (order by custo_r))::numeric, 4) as custo_r_p50,
       round(avg(r_bruto), 4) as exp_bruta_r,
       round(avg(r_net), 4) as exp_liquida_r,
       round(sum(r_net), 2) as soma_r,
       round(sum(r_net) filter (where r_net > 0)
             / nullif(-sum(r_net) filter (where r_net < 0), 0), 4) as pf_liquido,
       round(100.0 * count(*) filter (where r_net > 0) / count(*), 1) as acerto_pct,
       count(*) filter (where risco_pct < 0.003) as fora_piso_c5,
       count(*) filter (where risco_pct > 0.03) as fora_teto_c5,
       round(100.0 * count(*) filter (where risco_pct > 0.03) / count(*), 1) as pct_acima_3pct
  from c
 group by 1, 2, 3, 4
 order by 1, 2;
commit;
