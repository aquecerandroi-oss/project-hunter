-- T3.76 q05 -- FUNIL K1-K5 DOS BRACOS E DO PAI, E A COBERTURA DE `R_net`.
-- K1 (< 20 decisoes), K2 (> 1500), K3 (>= 100 avaliaveis E >= 30 dias E
-- expectancy bruta `r_ex_funding` < 0), K4 (`unavailable` > 40 % das barras) e
-- K5 (cobertura de `R_net` < 70 %) estao congelados em `docs/plans/SHADOW-LAB.md`.
-- **K4 nao e mensuravel numa versao com portao** (§4b item 12): a barra que
-- seria `unavailable` e recusada como `ineligible` antes, entao a filha mede 0 %
-- como falso verde. Por isso esta consulta le K4 no **pai** e reporta a fracao
-- `ineligible` da filha como numero proprio, ao lado, nunca no lugar.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

\echo ''
\echo '== 1. barras avaliadas por estado (K4 e a fracao ineligible) =='
select s.key || ' ' || v.version as versao,
       r.cohort,
       sum(r.bars_evaluated)                                            as barras,
       sum((r.evaluations_by_state->>'unavailable')::int)               as unavailable,
       round(100.0 * sum(coalesce((r.evaluations_by_state->>'unavailable')::int,0))
             / sum(r.bars_evaluated), 2)                                as k4_pct,
       sum(coalesce((r.evaluations_by_state->>'ineligible')::int,0))    as ineligible,
       round(100.0 * sum(coalesce((r.evaluations_by_state->>'ineligible')::int,0))
             / sum(r.bars_evaluated), 2)                                as ineligible_pct,
       sum(coalesce((r.evaluations_by_state->>'triggered')::int,0))     as triggered,
       sum(r.errors)                                                    as erros
  from replay_runs r
  join strategy_versions v on v.id = r.strategy_version_id
  join strategies s on s.id = v.strategy_id
 where r.cohort in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                    'replay:3271f431-10f3-4fad-81f5-8fb96fa6bfac',
                    'replay:309144d2-c89b-4f1a-b417-c04f1c49df3c',
                    'replay:095d4772-d133-47de-82cb-189dc78bbade',
                    'replay:70f55430-2752-48d8-93db-3941d3b31bf8')
 group by 1, 2 order by 1;

\echo ''
\echo '== 2. K1/K2/K3/K5: populacao, dias, eixos e cobertura de R_net =='
select s.key || ' ' || v.version as versao,
       count(*)                                                as decisoes,
       count(*) filter (where o.tracking_state::text='terminal') as terminais,
       count(distinct (a.emitted_at at time zone 'UTC')::date) as dias,
       count(o.r_multiple)                                      as com_r_net,
       round(100.0 * count(o.r_multiple) / nullif(count(*),0), 1) as cobertura_rnet_pct,
       round(avg((o.meta->>'r_ex_funding')::numeric), 4)        as media_r_exf,
       round(avg(o.r_multiple), 4)                              as media_r_net
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join strategy_versions v  on v.id = a.strategy_version_id
  join strategies s         on s.id = v.strategy_id
 where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                             'replay:3271f431-10f3-4fad-81f5-8fb96fa6bfac',
                             'replay:309144d2-c89b-4f1a-b417-c04f1c49df3c',
                             'replay:095d4772-d133-47de-82cb-189dc78bbade',
                             'replay:70f55430-2752-48d8-93db-3941d3b31bf8')
 group by 1 order by 1;

\echo ''
\echo '== 3. desfechos por resultado (o funil de saida) =='
select s.key || ' ' || v.version as versao, o.result::text, count(*)
  from signal_outcomes o
  join agent_signals a      on a.id = o.signal_id
  join strategy_versions v  on v.id = a.strategy_version_id
  join strategies s         on s.id = v.strategy_id
 where o.meta->>'cohort' in ('replay:c7d138eb-a633-4457-a4fa-aa82a5df95e3',
                             'replay:3271f431-10f3-4fad-81f5-8fb96fa6bfac',
                             'replay:309144d2-c89b-4f1a-b417-c04f1c49df3c',
                             'replay:095d4772-d133-47de-82cb-189dc78bbade',
                             'replay:70f55430-2752-48d8-93db-3941d3b31bf8')
 group by 1, 2 order by 1, 2;

commit;
