-- T3.62b q10 -- POPULACAO, PORTAS K1-K6 e as TRES JANELAS DE ~30 d, para v10, v1 e v2
-- sobre a janela limpa de 90 d (2026-06-12 -> 2026-09-10, 16 mercados, 100 % de vela).
--
-- A decisao de metodo que manda nesta consulta, e o motivo dela:
--   `funding_rates` so existe a partir de 2026-08-08 16:00 UTC. O backfill de 90 d
--   trouxe VELA, nao FUNDING. Entao `signal_outcomes.r_multiple` (= R liquido COM
--   funding) e NULO em 498 das 798 decisoes da v10 -- `funding_schedule_unknown`.
--   Usar so o subconjunto com r_multiple seria medir agosto/setembro de novo e
--   chamar isso de 90 dias -- exatamente o erro que o brief manda evitar.
--   Por isso o eixo principal aqui e `r_ex_funding` (bruto menos spread e taxa,
--   SEM funding), que existe em 100 % dos desfechos terminais, e o funding entra
--   como arrasto MEDIDO na janela onde ele e conhecido (secao 6). O r liquido COM
--   funding continua reportado, com a cobertura dele declarada (K5).
--
-- Aritmetica identica a T3.62 q10 / T3.54 q10 / T3.47 q01 (KB-0076 + notas T3.40 8b):
--   r_bruto = (exit_base - p_entry/1.0006)/initial_risk   (toda a populacao e `long`,
--             conferido: 1 644 de 1 644 -- o 1.0006 e o slippage de entrada, desfeito)
--   pedagio = r_bruto - r_ex_funding ; risco% = initial_risk/p_entry
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- ============ 0. catalogo das tres versoes (o contraste tem de ser de parametro)
select sv.version, sv.status::text as estado, sv.purpose::text as proposito,
       sv.default_parameters->>'atr_pct_min'   as atr_pct_min,
       sv.default_parameters->>'stop_atr'      as stop_atr,
       sv.default_parameters->>'target_atr'    as alvo1,
       sv.default_parameters->>'target2_atr'   as alvo2,
       sv.default_parameters->>'atr_timeframe' as atr_tf,
       sv.default_parameters->>'atr_bars'      as atr_bars,
       coalesce(sv.eligibility_policy::text,'-') as politica,
       right(sv.code_ref,16) as code_ref_sufixo
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
 where s.key='mean_reversion' and sv.version in ('v1','v2','v10')
 order by (regexp_replace(sv.version,'\D','','g'))::int;

-- ============ 1. K1-K6 (K5 sobre r_net COM funding e sobre r_ex_funding)
with pop as (
  select sv.version, o.tracking_state::text as estado,
         o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_exf,
         a.market_id, (a.emitted_at at time zone 'UTC')::date as dia
    from signal_outcomes o
    join agent_signals a on a.id=o.signal_id
    join strategy_versions sv on sv.id=a.strategy_version_id
   where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c',
                               'replay:da706026-319a-451e-950e-7728ca9ae563')
), mx as (
  -- o maior mercado de cada versao, como ESCALAR. Um join por versao aqui
  -- multiplicaria cada decisao por 16 (medido na primeira passada: 798 -> 12 768)
  -- e TODO contador inteiro sairia 16x; so as razoes sobreviveriam. E esse e
  -- exatamente o tipo de erro de denominador que passa despercebido.
  select version, max(n) as maior
    from (select version, market_id, count(*) n from pop group by 1,2) t
   group by 1
)
select p.version,
       count(*) as decisoes,
       count(*) filter (where estado='terminal') as terminais,
       count(r_exf) as com_r_exfunding,
       count(r_net) as com_r_net,
       round(100.0*count(r_exf)/count(*),2) as k5_cobertura_exf_pct,
       round(100.0*count(r_net)/count(*),2) as k5_cobertura_net_pct,
       count(distinct dia) as k3_dias_distintos,
       count(distinct p.market_id) as mercados,
       round(100.0*(select maior from mx where mx.version=p.version)/count(*),1)
         as k6_maior_mercado_pct
  from pop p
 group by 1 order by 1;

-- ============ 2. POOLED, eixo r_ex_funding (100 % da populacao) e r_net (subconjunto)
with c as (
  select sv.version,
         o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         (a.emitted_at at time zone 'UTC')::date as dia
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
    join strategy_versions sv on sv.id=a.strategy_version_id
   where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c',
                               'replay:da706026-319a-451e-950e-7728ca9ae563')
     and o.tracking_state::text='terminal'
), d as (
  select *, (exit_base - p_entry/1.0006)/nullif(risk,0) as r_bruto,
            (exit_base - p_entry/1.0006)/nullif(risk,0) - r_exf as custo_r,
            risk/nullif(p_entry,0) as risco_pct from c
)
select version, count(*) as n, count(distinct dia) as dias,
       round((percentile_cont(0.5) within group (order by atr_pct))::numeric,5) as atr_pct_p50,
       round((percentile_cont(0.5) within group (order by risco_pct))::numeric,5) as risco_pct_p50,
       round(avg(custo_r),4) as pedagio_medio_r,
       round((percentile_cont(0.5) within group (order by custo_r))::numeric,4) as pedagio_p50_r,
       round(avg(r_bruto),4)  as exp_bruta_r,
       round(avg(r_exf),4)    as exp_exfunding_r,
       round(stddev_samp(r_exf),4) as dp_exf,
       round(sum(r_exf) filter (where r_exf>0)/nullif(-sum(r_exf) filter (where r_exf<0),0),4) as pf_exfunding,
       round(100.0*count(*) filter (where r_exf>0)/count(*),1) as acerto_pct,
       count(r_net) as n_com_net,
       round(avg(r_net),4) as exp_liquida_r,
       round(sum(r_net) filter (where r_net>0)/nullif(-sum(r_net) filter (where r_net<0),0),4) as pf_liquido,
       count(*) filter (where risco_pct < 0.003) as c5_abaixo_piso,
       count(*) filter (where risco_pct > 0.03)  as c5_acima_teto,
       round(100.0*count(*) filter (where risco_pct > 0.03)/count(*),1) as c5_acima_teto_pct
  from d group by 1 order by 1;

-- ============ 3. AS TRES JANELAS DE 30 d, separadas (a pergunta central do brief)
with c as (
  select sv.version,
         o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (a.emitted_at at time zone 'UTC')::date as dia,
         case when a.emitted_at <  timestamptz '2026-07-12' then 'J1 jun12-jul12'
              when a.emitted_at <  timestamptz '2026-08-11' then 'J2 jul12-ago11'
              else 'J3 ago11-set10' end as janela
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
    join strategy_versions sv on sv.id=a.strategy_version_id
   where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c',
                               'replay:da706026-319a-451e-950e-7728ca9ae563')
     and o.tracking_state::text='terminal'
), d as (
  select *, (exit_base - p_entry/1.0006)/nullif(risk,0) as r_bruto,
            (exit_base - p_entry/1.0006)/nullif(risk,0) - r_exf as custo_r from c
)
select version, janela, count(*) as n, count(distinct dia) as dias,
       round(avg(r_bruto),4) as exp_bruta_r,
       round((percentile_cont(0.5) within group (order by custo_r))::numeric,4) as pedagio_p50_r,
       round(avg(r_exf),4)   as exp_exfunding_r,
       round(sum(r_exf) filter (where r_exf>0)/nullif(-sum(r_exf) filter (where r_exf<0),0),4) as pf_exfunding,
       round(100.0*count(*) filter (where r_exf>0)/count(*),1) as acerto_pct,
       count(r_net) as n_com_net,
       round(avg(r_net),4) as exp_liquida_r
  from d group by 1,2 order by 1,2;

-- ============ 4. DECOMPOSICAO POR MERCADO (K6 e a assinatura de selecao)
with c as (
  select sv.version, mk.symbol,
         (mk.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT')) as original,
         (o.meta->>'r_ex_funding')::numeric as r_exf, o.r_multiple as r_net
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
    join strategy_versions sv on sv.id=a.strategy_version_id
    join markets mk on mk.id=a.market_id
   where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c',
                               'replay:da706026-319a-451e-950e-7728ca9ae563')
     and o.tracking_state::text='terminal'
)
select version, symbol, original, count(*) as n,
       round(avg(r_exf),4) as exp_exfunding_r,
       round(sum(r_exf),2) as soma_exf,
       round(sum(r_exf) filter (where r_exf>0)/nullif(-sum(r_exf) filter (where r_exf<0),0),3) as pf
  from c group by 1,2,3 order by 1, 5 desc;

-- ============ 5. 4 ORIGINAIS vs 12 NOVOS (replicacao)
with c as (
  select sv.version,
         (mk.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT')) as original,
         (o.meta->>'r_ex_funding')::numeric as r_exf
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
    join strategy_versions sv on sv.id=a.strategy_version_id
    join markets mk on mk.id=a.market_id
   where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c',
                               'replay:da706026-319a-451e-950e-7728ca9ae563')
     and o.tracking_state::text='terminal'
)
select version, case when original then '4 originais' else '12 novos' end as grupo,
       count(*) as n, round(avg(r_exf),4) as exp_exfunding_r,
       round(sum(r_exf) filter (where r_exf>0)/nullif(-sum(r_exf) filter (where r_exf<0),0),3) as pf
  from c group by 1,2 order by 1,2;

-- ============ 6. O ARRASTO DE FUNDING, onde ele e CONHECIDO (>= 2026-08-08 16:00)
with c as (
  select sv.version, o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_exf
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
    join strategy_versions sv on sv.id=a.strategy_version_id
   where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c',
                               'replay:da706026-319a-451e-950e-7728ca9ae563')
     and o.tracking_state::text='terminal' and o.r_multiple is not null
)
select version, count(*) as n_com_funding_conhecido,
       round(avg(r_exf),4) as exp_exfunding_r,
       round(avg(r_net),4) as exp_liquida_r,
       round(avg(r_net - r_exf),4) as arrasto_funding_medio_r,
       round((percentile_cont(0.5) within group (order by (r_net-r_exf)))::numeric,4) as arrasto_p50_r
  from c group by 1 order by 1;

commit;
