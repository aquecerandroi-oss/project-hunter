-- T3.84 q04 -- funil K1-K6, cobertura, C5 (as duas metades da banda de risco do
-- `paper_v1`) e o PEDAGIO MEDIDO NAS DECISOES, para a coorte de 90 d da
-- `mean_reversion_m5 v1` (EXP-0028) e para o controle pre-declarado
-- (`mean_reversion v1`, coorte `replay:fa005985-...`, EXP-0025/T3.62b).
--
-- Por que o pedagio aparece aqui e nao so no passo 2 desta tarefa: o passo 2
-- mediu a identidade da KB-0076 sobre a DISTRIBUICAO DE BARRAS condicionada ao
-- portao de ATR% (0,2540 R previstos), assumindo independencia entre o portao e
-- as outras tres condicoes de entrada. Aqui o mesmo numero e lido nas decisoes
-- que REALMENTE aconteceram (`supporting_features->atr->>percent`), o que
-- confirma ou derruba aquela assuncao sem um segundo calculo: a formula e a
-- mesma, custo_R = 0,0020 / (stop_atr x ATR%) com stop_atr = 1.
--
-- K1 < 20 decisoes · K2 > 1500 · K3 >= 100 desfechos E >= 30 dias E bruta < 0 ·
-- K4 unavailable > 40 % das barras (lido do recibo do replay em `system_events`,
-- nao de um segundo contador) · K5 cobertura de R_net < 70 % · K6 >= 60 % das
-- decisoes num unico mercado (`docs/plans/SHADOW-LAB.md` 145-162).
-- C5: banda `paper_v1` [0,003; 0,03] sobre initial_risk / entry.
--
-- A CTE `decisao` e repetida em cada consulta DE PROPOSITO: uma view temporaria
-- seria uma escrita no catalogo e a transacao e `read only` por contrato -- o
-- Postgres recusa `create temporary view` aqui, e essa recusa e a prova de que o
-- contrato esta valendo. Cada consulta e auditavel sozinha; o texto da CTE e
-- identico caractere por caractere nas seis.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format aligned
\pset tuples_only off

\echo == 1. populacao, K1/K2/K3/K5/K6 e expectativa (eixo r_ex_funding) ==
with decisao as (
  select s.key || ' ' || sv.version as versao, (a.emitted_at at time zone 'UTC')::date as dia,
         mk.symbol as mercado,
         case when a.emitted_at < timestamptz '2026-07-12' then 'J1'
              when a.emitted_at < timestamptz '2026-08-11' then 'J2' else 'J3' end as janela,
         (o.meta->>'r_ex_funding')::numeric as r_exf, o.r_multiple as r_net,
         ((o.meta->'progress'->>'exit_base')::numeric - (o.meta->'progress'->>'entry')::numeric/1.0006)
         / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0) as r_bruto,
         (o.meta->'excursions'->>'initial_risk')::numeric
         / nullif((o.meta->'progress'->>'entry')::numeric,0) as risco_pct,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         o.meta->'progress'->>'result' as saida
    from signal_outcomes o join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id join markets mk on mk.id = a.market_id
   where o.meta->>'cohort' in ('replay:92c8d080-6009-4a59-9868-31282b1bd493',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c')
     and o.tracking_state::text = 'terminal')
select versao, count(*) as desfechos, count(r_exf) as avaliaveis, count(distinct dia) as dias,
       round(avg(r_exf), 4) as exp_exf, round(avg(r_bruto), 4) as exp_bruta,
       round(sum(case when r_exf > 0 then r_exf else 0 end)
             / nullif(-sum(case when r_exf < 0 then r_exf else 0 end), 0), 4) as pf_exf,
       round(100.0 * count(r_net) / count(*), 2) as cobertura_rnet_pct,
       round(100.0 * max(por_mkt) / count(*), 2) as maior_mercado_pct
  from decisao d
  cross join lateral (select count(*) as por_mkt from decisao x
                       where x.versao = d.versao and x.mercado = d.mercado) m
 group by versao order by versao;

\echo == 2. por janela de 30 d (regra de sucesso no 2: PF > 1 em >= 2 de 3) ==
with decisao as (
  select s.key || ' ' || sv.version as versao, (a.emitted_at at time zone 'UTC')::date as dia,
         mk.symbol as mercado,
         case when a.emitted_at < timestamptz '2026-07-12' then 'J1'
              when a.emitted_at < timestamptz '2026-08-11' then 'J2' else 'J3' end as janela,
         (o.meta->>'r_ex_funding')::numeric as r_exf, o.r_multiple as r_net,
         ((o.meta->'progress'->>'exit_base')::numeric - (o.meta->'progress'->>'entry')::numeric/1.0006)
         / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0) as r_bruto,
         (o.meta->'excursions'->>'initial_risk')::numeric
         / nullif((o.meta->'progress'->>'entry')::numeric,0) as risco_pct,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         o.meta->'progress'->>'result' as saida
    from signal_outcomes o join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id join markets mk on mk.id = a.market_id
   where o.meta->>'cohort' in ('replay:92c8d080-6009-4a59-9868-31282b1bd493',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c')
     and o.tracking_state::text = 'terminal')
select versao, janela, count(*) as n, count(distinct dia) as dias,
       round(avg(r_exf), 4) as exp_exf, round(avg(r_bruto), 4) as exp_bruta,
       round(sum(case when r_exf > 0 then r_exf else 0 end)
             / nullif(-sum(case when r_exf < 0 then r_exf else 0 end), 0), 4) as pf_exf
  from decisao group by versao, janela order by versao, janela;

\echo == 3. por mercado (K6 e a decomposicao obrigatoria) ==
with decisao as (
  select s.key || ' ' || sv.version as versao, (a.emitted_at at time zone 'UTC')::date as dia,
         mk.symbol as mercado,
         case when a.emitted_at < timestamptz '2026-07-12' then 'J1'
              when a.emitted_at < timestamptz '2026-08-11' then 'J2' else 'J3' end as janela,
         (o.meta->>'r_ex_funding')::numeric as r_exf, o.r_multiple as r_net,
         ((o.meta->'progress'->>'exit_base')::numeric - (o.meta->'progress'->>'entry')::numeric/1.0006)
         / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0) as r_bruto,
         (o.meta->'excursions'->>'initial_risk')::numeric
         / nullif((o.meta->'progress'->>'entry')::numeric,0) as risco_pct,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         o.meta->'progress'->>'result' as saida
    from signal_outcomes o join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id join markets mk on mk.id = a.market_id
   where o.meta->>'cohort' in ('replay:92c8d080-6009-4a59-9868-31282b1bd493',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c')
     and o.tracking_state::text = 'terminal')
select versao, mercado, count(*) as n, round(avg(r_exf), 4) as exp_exf,
       round(sum(case when r_exf > 0 then r_exf else 0 end)
             / nullif(-sum(case when r_exf < 0 then r_exf else 0 end), 0), 4) as pf_exf,
       round(100.0 * avg(atr_pct), 4) as atr_pct_medio
  from decisao group by versao, mercado order by versao, n desc;

\echo == 4. C5 -- banda de risco do paper_v1 [0,003; 0,03] sobre initial_risk/entry ==
with decisao as (
  select s.key || ' ' || sv.version as versao, (a.emitted_at at time zone 'UTC')::date as dia,
         mk.symbol as mercado,
         case when a.emitted_at < timestamptz '2026-07-12' then 'J1'
              when a.emitted_at < timestamptz '2026-08-11' then 'J2' else 'J3' end as janela,
         (o.meta->>'r_ex_funding')::numeric as r_exf, o.r_multiple as r_net,
         ((o.meta->'progress'->>'exit_base')::numeric - (o.meta->'progress'->>'entry')::numeric/1.0006)
         / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0) as r_bruto,
         (o.meta->'excursions'->>'initial_risk')::numeric
         / nullif((o.meta->'progress'->>'entry')::numeric,0) as risco_pct,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         o.meta->'progress'->>'result' as saida
    from signal_outcomes o join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id join markets mk on mk.id = a.market_id
   where o.meta->>'cohort' in ('replay:92c8d080-6009-4a59-9868-31282b1bd493',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c')
     and o.tracking_state::text = 'terminal')
select versao, janela, count(*) as n,
       round((100.0 * percentile_cont(0.5) within group (order by risco_pct))::numeric, 4) as risco_pct_p50,
       sum(case when risco_pct < 0.003 then 1 else 0 end) as abaixo_do_piso,
       sum(case when risco_pct > 0.03  then 1 else 0 end) as acima_do_teto,
       round(100.0 * sum(case when risco_pct < 0.003 then 1 else 0 end)/count(*), 2) as abaixo_pct,
       round(100.0 * sum(case when risco_pct > 0.03  then 1 else 0 end)/count(*), 2) as acima_pct
  from decisao group by versao, janela
union all
select versao, 'TODAS', count(*),
       round((100.0 * percentile_cont(0.5) within group (order by risco_pct))::numeric, 4),
       sum(case when risco_pct < 0.003 then 1 else 0 end),
       sum(case when risco_pct > 0.03  then 1 else 0 end),
       round(100.0 * sum(case when risco_pct < 0.003 then 1 else 0 end)/count(*), 2),
       round(100.0 * sum(case when risco_pct > 0.03  then 1 else 0 end)/count(*), 2)
  from decisao group by versao order by 1, 2;

\echo == 5. PEDAGIO medido nas decisoes: ATR% realizado e 0,0020/ATR% (stop_atr=1) ==
with decisao as (
  select s.key || ' ' || sv.version as versao, (a.emitted_at at time zone 'UTC')::date as dia,
         mk.symbol as mercado,
         case when a.emitted_at < timestamptz '2026-07-12' then 'J1'
              when a.emitted_at < timestamptz '2026-08-11' then 'J2' else 'J3' end as janela,
         (o.meta->>'r_ex_funding')::numeric as r_exf, o.r_multiple as r_net,
         ((o.meta->'progress'->>'exit_base')::numeric - (o.meta->'progress'->>'entry')::numeric/1.0006)
         / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0) as r_bruto,
         (o.meta->'excursions'->>'initial_risk')::numeric
         / nullif((o.meta->'progress'->>'entry')::numeric,0) as risco_pct,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         o.meta->'progress'->>'result' as saida
    from signal_outcomes o join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id join markets mk on mk.id = a.market_id
   where o.meta->>'cohort' in ('replay:92c8d080-6009-4a59-9868-31282b1bd493',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c')
     and o.tracking_state::text = 'terminal')
select versao, count(atr_pct) as n,
       round((100.0 * percentile_cont(0.5) within group (order by atr_pct))::numeric, 4) as atr_pct_p50,
       round((100.0 * percentile_cont(0.25) within group (order by atr_pct))::numeric, 4) as atr_pct_p25,
       round((100.0 * percentile_cont(0.75) within group (order by atr_pct))::numeric, 4) as atr_pct_p75,
       round((0.0020 / percentile_cont(0.5) within group (order by atr_pct))::numeric, 4) as pedagio_R_p50,
       round(avg(0.0020 / atr_pct), 4) as pedagio_R_medio,
       sum(case when atr_pct < 0.006 then 1 else 0 end) as sob_o_piso_006
  from decisao group by versao order by versao;

\echo == 6. funil de saida ==
with decisao as (
  select s.key || ' ' || sv.version as versao, (a.emitted_at at time zone 'UTC')::date as dia,
         mk.symbol as mercado,
         case when a.emitted_at < timestamptz '2026-07-12' then 'J1'
              when a.emitted_at < timestamptz '2026-08-11' then 'J2' else 'J3' end as janela,
         (o.meta->>'r_ex_funding')::numeric as r_exf, o.r_multiple as r_net,
         ((o.meta->'progress'->>'exit_base')::numeric - (o.meta->'progress'->>'entry')::numeric/1.0006)
         / nullif((o.meta->'excursions'->>'initial_risk')::numeric,0) as r_bruto,
         (o.meta->'excursions'->>'initial_risk')::numeric
         / nullif((o.meta->'progress'->>'entry')::numeric,0) as risco_pct,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         o.meta->'progress'->>'result' as saida
    from signal_outcomes o join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id join markets mk on mk.id = a.market_id
   where o.meta->>'cohort' in ('replay:92c8d080-6009-4a59-9868-31282b1bd493',
                               'replay:fa005985-0b55-4820-904c-8ada589e441c')
     and o.tracking_state::text = 'terminal')
select versao, saida, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (partition by versao), 2) as pct,
       round(avg(r_exf), 4) as exp_exf
  from decisao group by versao, saida order by versao, n desc;

\echo == 7. K4 -- unavailable lido do recibo de cada corrida de replay ==
select data->>'cohort'                                          as coorte,
       count(*)                                                 as corridas,
       sum((data->>'bars_evaluated')::bigint)                   as barras,
       sum(coalesce((data->'evaluations_by_state'->>'unavailable')::bigint, 0)) as unavailable,
       sum(coalesce((data->'evaluations_by_state'->>'triggered')::bigint, 0))   as triggered,
       round(100.0 * sum(coalesce((data->'evaluations_by_state'->>'unavailable')::bigint,0))
             / sum((data->>'bars_evaluated')::bigint), 4)        as unavailable_pct,
       sum((data->>'errors')::bigint)                            as erros,
       min(data->>'window_from')                                 as de,
       max(data->>'window_to')                                   as ate
  from system_events
 where component = 'replay_engine' and event = 'replay_run_finished'
   and data->>'cohort' = 'replay:92c8d080-6009-4a59-9868-31282b1bd493'
 group by 1;

\echo == 8. cobertura de barras por mercado (as 23 fatias cobrem 16 x 90 d?) ==
select mk.symbol, count(*) as fatias,
       sum((se.data->>'bars_evaluated')::bigint / (se.data->>'market_count')::bigint) as barras
  from system_events se
  cross join lateral jsonb_array_elements_text(se.data->'markets') as m(nome)
  join markets mk on ('binance:' || mk.symbol) = m.nome
 where se.component = 'replay_engine' and se.event = 'replay_run_finished'
   and se.data->>'cohort' = 'replay:92c8d080-6009-4a59-9868-31282b1bd493'
   -- mk.market_type = 'perpetual': cada simbolo tem DUAS linhas em `markets`
   -- desde a T3.0c (a perpetua e a SPOT) e sem este filtro o join conta cada
   -- fatia duas vezes -- 51 840 barras por mercado em vez das 25 920 reais.
   and mk.market_type::text = 'perpetual'
 group by 1 order by 1;

commit;
