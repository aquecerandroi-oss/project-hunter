-- T3.47b q10 — o fatorial 2x2 do piso de ATR% x largura do stop, mesma janela
-- (2026-08-08..2026-09-08), mesmos quatro mercados, mesmo lag, mesmos workers.
--   piso 0,006 stop 1,0 = mean_reversion v1 (a "v9" do brief, por identidade)
--   piso 0,008 stop 1,0 = mean_reversion v2 (o pai)
--   piso 0,006 stop 1,5 = mean_reversion v8 (derivada nesta tarefa)
--   piso 0,008 stop 1,5 = mean_reversion v6 (T3.47 B1)
-- Contexto: v3 (0,010/1,0), v4 (0,010/1,5), v5 (0,010/2,0), v7 (0,008/2,0).
-- Somente leitura.
\set pop 'select s.key||\' \'||sv.version as versao, sv.default_parameters->>\'atr_pct_min\' as piso, sv.default_parameters->>\'stop_atr\' as stop_atr, left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, a.market_id, m.symbol, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.result::text as motivo, o.tracking_state::text as estado, o.r_multiple as r_net, (o.meta->>\'r_ex_funding\')::numeric as r_exf, (o.meta->\'progress\'->>\'entry\')::numeric as p_entry, (o.meta->\'progress\'->>\'exit_base\')::numeric as exit_base, (o.meta->\'excursions\'->>\'initial_risk\')::numeric as risk, (a.supporting_features->\'atr\'->>\'percent\')::numeric as atr_pct from signal_outcomes o join agent_signals a on a.id=o.signal_id join markets m on m.id=a.market_id join strategy_versions sv on sv.id=a.strategy_version_id join strategies s on s.id=sv.strategy_id where o.meta->>\'cohort\' in (\'replay:d0f77894-1e04-454e-a49f-d9a98d894968\',\'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a\',\'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4\',\'replay:9d99748b-21b9-44a7-8980-32c37b931e6e\',\'replay:264b227f-5bc0-4930-8c5b-2e883c0a858e\',\'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28\',\'replay:66fa85cb-1d51-4330-a00b-00964b430ab4\',\'replay:8ac79cca-916b-4f7f-bd83-01b068b9f811\')'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. populacoes
with pop as (:pop)
select versao, piso, stop_atr, coorte,
       count(*) as decisoes,
       count(*) filter (where estado='terminal' and r_net is not null) as avaliaveis,
       round(avg((exit_base - p_entry/1.0006)/risk) filter (where risk>0), 4) as exp_bruta_r,
       round(avg((exit_base - p_entry/1.0006)/risk - r_exf) filter (where risk>0), 4) as custo_medio_r,
       round((percentile_cont(0.5) within group (order by (exit_base - p_entry/1.0006)/risk - r_exf))::numeric,4) as custo_p50_r,
       round(avg(r_net) filter (where r_net is not null), 4) as exp_liquida_r,
       round(sum(r_net) filter (where r_net is not null), 2) as soma_r,
       round(100.0*count(*) filter (where motivo='target')/nullif(count(*) filter (where estado='terminal'),0), 1) as acerto_pct,
       round(sum(r_net) filter (where r_net>0) / nullif(-sum(r_net) filter (where r_net<0),0), 4) as pf_liquido,
       round(sum((exit_base - p_entry/1.0006)/risk) filter (where risk>0 and (exit_base - p_entry/1.0006)/risk>0)
             / nullif(-sum((exit_base - p_entry/1.0006)/risk) filter (where risk>0 and (exit_base - p_entry/1.0006)/risk<0),0), 4) as pf_bruto,
       count(distinct bar::date) as dias,
       round((percentile_cont(0.5) within group (order by atr_pct))::numeric,5) as atr_pct_p50,
       round((percentile_cont(0.5) within group (order by risk/nullif(p_entry,0)))::numeric,5) as risco_pct_p50
  from pop group by 1,2,3,4 order by 2,3;

-- 2. cobertura
with pop as (:pop)
select versao, coorte, count(*) as emitidos,
       count(*) filter (where estado='pending_entry') as pendentes,
       count(*) filter (where p_entry is not null) as entradas,
       count(*) filter (where estado='active') as ativos,
       count(*) filter (where motivo='target') as alvo,
       count(*) filter (where motivo='stop') as stop,
       count(*) filter (where motivo='expired') as expirado,
       count(*) filter (where motivo='invalidated') as invalidado,
       count(*) filter (where r_net is null) as sem_r,
       count(*) filter (where estado='terminal' and r_net is not null) as avaliaveis,
       count(distinct bar::date) as dias
  from pop group by 1,2 order by 1;

-- 3. identidade do pedagio: custo_R previsto = 0,0020 / risco%
with pop as (:pop), c as (
  select versao, coorte, (exit_base - p_entry/1.0006)/risk - r_exf as custo_medido,
         0.0020/(risk/p_entry) as custo_previsto,
         risk/(atr_pct*p_entry) as stop_atr_efetivo
    from pop where risk > 0
)
select versao, coorte, count(*) as n,
       round(avg(custo_medido),4) as custo_medio_medido,
       round(max(custo_medido),4) as custo_max_medido,
       round(avg(custo_previsto),4) as custo_medio_previsto,
       round(max(abs(custo_medido-custo_previsto)),5) as maior_erro_absoluto,
       round(min(stop_atr_efetivo),4) as stop_atr_ef_min,
       round(avg(stop_atr_efetivo),4) as stop_atr_ef_medio,
       round(max(stop_atr_efetivo),4) as stop_atr_ef_max
  from c group by 1,2 order by 1;

-- 4. C5: banda de stop do paper_v1 [0,003; 0,03] do preco
with pop as (:pop)
select versao, coorte, count(*) as n,
       count(*) filter (where risk/p_entry > 0.03) as acima_do_teto_paper,
       count(*) filter (where risk/p_entry < 0.003) as abaixo_do_piso_paper,
       round(100.0*count(*) filter (where risk/p_entry > 0.03 or risk/p_entry < 0.003)/count(*),1) as pct_recusado,
       round(sum(r_net) filter (where risk/p_entry > 0.03),2) as soma_r_acima_do_teto
  from pop where p_entry > 0 group by 1,2 order by 1;

-- 5. motivos de saida
with pop as (:pop)
select versao, coorte, motivo, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (partition by coorte),1) as pct,
       round(avg(r_net),4) as r_liq_medio, round(sum(r_net),2) as r_liq_soma
  from pop where estado='terminal' group by 1,2,3 order by 1, n desc;
commit;
