-- T3.48 — insumos do documento "o que muda se o risco por operação subir de 0,25 %".
--
-- SOMENTE LEITURA (repeatable read read only). Executável sozinho. Nenhum bloco
-- cria tabela temporária (proibido em transação read only), por isso o CTE `pop`
-- é repetido de propósito em cada consulta — convenção de
-- `infra/scripts/sql/research/2026-09-08-00-base.sql`.
--
-- DECOMPOSIÇÃO DO R (contrato de `hunter_strategy_worker/pricing.py`, colado em
-- `2026-09-08-00-base.sql`):
--   risco        = P_entry − stop = meta.excursions.initial_risk
--   risco_pct    = risco / (P_entry/1.0006)      -> a DISTÂNCIA DO STOP em fração do preço,
--                  que é exatamente o que o check 8 (`stop_distance`) do Risk Engine mede
--                  contra a banda [min_stop_distance_pct, max_stop_distance_pct] = [0,003; 0,03]
--   r_gross      = (exit_base − P_entry/1.0006) / risco          (sem custo nenhum)
--   r_exf        = meta.r_ex_funding                              (com spread+slippage+fee)
--   r_net        = signal_outcomes.r_multiple                     (custo + funding)
--   custo_R      = r_gross − r_exf   ->  identidade  custo_R × risco_pct ≈ 0,0020
--
-- DINHEIRO. O R do Lab tem denominador `risco` = distância do stop SEM custo; o
-- orçamento do Risk Engine (§4) é `equity × risk_per_trade_pct` sobre a distância
-- EFETIVA (stop + custo). Logo:
--   R$ por 1 R do Lab = equity × risk_per_trade_pct / (1 + custo_R)
-- Esta consulta publica `custo_R` medido para que a conversão do documento não
-- seja uma suposição.
--
-- DIA DE NEGOCIAÇÃO = `America/Sao_Paulo` (RISK_ENGINE §5), não UTC: o "pior dia"
-- desta consulta é o mesmo dia que o kill switch mede.
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as read_at, current_database() as db,
       now() at time zone 'America/Sao_Paulo' as read_at_brasilia;

\echo ''
\echo '== 1. catálogo: versões, propósito, status, parâmetros de geometria =='
select s.key || ' ' || sv.version as versao, sv.purpose, sv.status,
       sv.activated_at,
       sv.default_parameters->>'timeframe'   as tf,
       sv.default_parameters->>'atr_pct_min' as atr_pct_min,
       sv.default_parameters->>'atr_pct_max' as atr_pct_max,
       sv.default_parameters->>'stop_atr'    as stop_atr,
       sv.default_parameters->>'target_atr'  as target_atr,
       left(sv.code_ref, 60) as code_ref
  from strategy_versions sv
  join strategies s on s.id = sv.strategy_id
 order by s.key, sv.version;

\echo ''
\echo '== 2. carteira paper: patrimônio, caixa, perfil de risco em vigor =='
select p.name, p.type, p.status, p.kill_switch_state, p.base_currency,
       p.initial_capital,
       (select e.equity from portfolio_equity_snapshots e
         where e.portfolio_id = p.id order by e.ts desc limit 1) as equity_ultima,
       (select e.cash from portfolio_equity_snapshots e
         where e.portfolio_id = p.id order by e.ts desc limit 1) as cash_ultimo,
       (select e.ts from portfolio_equity_snapshots e
         where e.portfolio_id = p.id order by e.ts desc limit 1) as equity_ts,
       rp.preset,
       rp.limits->>'risk_per_trade_pct'             as risk_per_trade_pct,
       rp.limits->>'max_aggregate_planned_risk_pct' as max_agg_risk_pct,
       rp.limits->>'max_concurrent_positions'       as max_pos,
       rp.limits->>'max_stop_distance_pct'          as max_stop_dist,
       rp.limits->>'kill_switch_warning'            as ks_warning,
       rp.limits->>'kill_switch_blocked'            as ks_blocked
  from portfolios p
  left join risk_profiles rp on rp.id = p.risk_profile_id
 where p.deleted_at is null
 order by p.type, p.name;

\echo ''
\echo '== 3. desfechos fechados por versão × coorte: n, dias, expectância, PF, custo =='
with pop as (
  select s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         coalesce((a.supporting_features->>'decision_at')::timestamptz, a.emitted_at) as decision_at,
         o.result::text as resultado, o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risco
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
), d as (
  select *, risco / (p_entry / 1.0006) as risco_pct,
            (exit_base - p_entry / 1.0006) / risco as r_gross,
            (exit_base - p_entry / 1.0006) / risco - r_exf as custo_r
    from pop where risco > 0
)
select versao, coorte, count(*) n,
       count(distinct (decision_at at time zone 'America/Sao_Paulo')::date) dias,
       min(decision_at) as de, max(decision_at) as ate,
       round(avg(r_gross), 4) exp_bruto_r,
       round(avg(r_net), 4)   exp_liquido_r,
       round(sum(r_net), 2)   soma_r,
       round(100.0 * count(*) filter (where resultado = 'target') / count(*), 1) acerto_pct,
       round(coalesce(sum(r_net) filter (where r_net > 0), 0)
             / nullif(abs(sum(r_net) filter (where r_net < 0)), 0), 3) pf,
       round(percentile_cont(0.25) within group (order by custo_r)::numeric, 4) custo_r_p25,
       round(percentile_cont(0.50) within group (order by custo_r)::numeric, 4) custo_r_p50,
       round(percentile_cont(0.75) within group (order by custo_r)::numeric, 4) custo_r_p75,
       round(percentile_cont(0.50) within group (order by risco_pct)::numeric, 5) risco_pct_p50
  from d group by 1, 2 order by 1, 2;

\echo ''
\echo '== 4. pior dia e melhor dia em R (dia de São Paulo), por versão × coorte =='
with pop as (
  select s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         coalesce((a.supporting_features->>'decision_at')::timestamptz, a.emitted_at) as decision_at,
         o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
), dia as (
  select versao, coorte, (decision_at at time zone 'America/Sao_Paulo')::date as d,
         count(*) n_dia, sum(r_net) r_dia
    from pop group by 1, 2, 3
)
select versao, coorte, count(*) dias,
       round(min(r_dia), 3) pior_dia_r,
       (array_agg(d order by r_dia asc))[1] pior_dia,
       (array_agg(n_dia order by r_dia asc))[1] ops_no_pior_dia,
       round(max(r_dia), 3) melhor_dia_r,
       round(avg(r_dia), 3) media_dia_r,
       round(avg(n_dia), 2) ops_por_dia
  from dia group by 1, 2 order by 1, 2;

\echo ''
\echo '== 5. maior sequência de perdas consecutivas (ordem de decisão), por versão × coorte =='
with pop as (
  select s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         coalesce((a.supporting_features->>'decision_at')::timestamptz, a.emitted_at) as decision_at,
         o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
), marc as (
  select versao, coorte, decision_at, r_net, (r_net < 0) as perda,
         row_number() over (partition by versao, coorte order by decision_at, r_net)
       - row_number() over (partition by versao, coorte, (r_net < 0) order by decision_at, r_net) as grp
    from pop
), runs as (
  select versao, coorte, perda, count(*) tam, sum(r_net) soma_r_da_sequencia
    from marc where perda group by versao, coorte, perda, grp
)
select versao, coorte, max(tam) max_perdas_seguidas,
       round(min(soma_r_da_sequencia), 3) pior_sequencia_r
  from runs group by 1, 2 order by 1, 2;

\echo ''
\echo '== 6. distância de stop medida vs o teto max_stop_distance_pct = 0,03 =='
\echo '==    (hoje, e o que aconteceria com stop x1,5 e x2 — a alavanca da T3.47) =='
with pop as (
  select s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'excursions'->>'initial_risk')::numeric as risco
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
), d as (
  select versao, coorte, risco / (p_entry / 1.0006) as risco_pct
    from pop where risco > 0 and p_entry > 0
)
select versao, coorte, count(*) n,
       round(percentile_cont(0.50) within group (order by risco_pct)::numeric, 5) p50,
       round(percentile_cont(0.90) within group (order by risco_pct)::numeric, 5) p90,
       round(max(risco_pct), 5) maximo,
       round(100.0 * count(*) filter (where risco_pct < 0.003) / count(*), 1) pct_abaixo_do_piso,
       round(100.0 * count(*) filter (where risco_pct > 0.03)  / count(*), 1) pct_acima_do_teto,
       round(100.0 * count(*) filter (where risco_pct * 1.5 > 0.03) / count(*), 1) pct_acima_com_stop_x15,
       round(100.0 * count(*) filter (where risco_pct * 2.0 > 0.03) / count(*), 1) pct_acima_com_stop_x2,
       round(100.0 * count(*) filter (where risco_pct * 1.5 < 0.003) / count(*), 1) pct_abaixo_com_stop_x15
  from d group by 1, 2 order by 1, 2;

\echo ''
\echo '== 7. o que a carteira paper de fato executou (propostas, ordens, posições) =='
select (select count(*) from trade_proposals) as propostas,
       (select count(*) from trade_proposals where (risk_decision->>'approved')::boolean) as aprovadas,
       (select count(*) from orders) as ordens,
       (select count(*) from positions) as posicoes,
       (select count(*) from positions where closed_at is null) as posicoes_abertas,
       (select count(*) from risk_events) as risk_events,
       (select count(*) from kill_switch_transitions) as transicoes_ks;

\echo ''
\echo '== 7b. motivos de recusa/indisponibilidade já registrados (se houver) =='
select type::text as tipo, severity::text as severidade, count(*) n,
       min(created_at) as de, max(created_at) as ate
  from risk_events group by 1, 2 order by 3 desc limit 20;

\echo ''
\echo '== 8. concorrência observada: decisões simultâneas por dia (quantos slots o Lab pediria) =='
with pop as (
  select s.key || ' ' || sv.version as versao,
         case when o.meta->>'cohort' like 'replay:%' then 'replay' else 'prospective' end as coorte,
         coalesce((a.supporting_features->>'decision_at')::timestamptz, a.emitted_at) as decision_at,
         o.entry_ts, o.exit_ts
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
   where o.tracking_state = 'terminal' and o.r_multiple is not null
     and o.entry_ts is not null and o.exit_ts is not null
)
select coorte, count(*) n_com_janela,
       round(avg(extract(epoch from (exit_ts - entry_ts)) / 3600.0)::numeric, 2) horas_medias_na_posicao,
       round(percentile_cont(0.50) within group
             (order by extract(epoch from (exit_ts - entry_ts)) / 3600.0)::numeric, 2) horas_p50,
       min(entry_ts) as de, max(exit_ts) as ate
  from pop group by 1 order by 1;

commit;
