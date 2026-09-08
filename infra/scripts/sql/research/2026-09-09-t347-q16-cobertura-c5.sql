-- T3.47 q16 — cobertura das seis coortes, identidade do pedagio conferida decisao a decisao,
-- checagem C5 (banda de stop do paper_v1: 0,003..0,03 do preco) e code_ref contra o pai.
\set pop 'select left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, o.result::text as motivo, o.tracking_state::text as estado, o.r_multiple as r_net, (o.meta->>\'r_ex_funding\')::numeric as r_exf, (o.meta->\'progress\'->>\'entry\')::numeric as p_entry, (o.meta->\'progress\'->>\'exit_base\')::numeric as exit_base, (o.meta->\'excursions\'->>\'initial_risk\')::numeric as risk, (a.supporting_features->\'atr\'->>\'percent\')::numeric as atr_pct, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar from signal_outcomes o join agent_signals a on a.id=o.signal_id where o.meta->>\'cohort\' in (\'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a\',\'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4\',\'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2\',\'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28\',\'replay:66fa85cb-1d51-4330-a00b-00964b430ab4\',\'replay:9d99748b-21b9-44a7-8980-32c37b931e6e\',\'replay:264b227f-5bc0-4930-8c5b-2e883c0a858e\',\'replay:293d98b7-90e1-4dfe-a604-60556f3b175e\',\'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd\')'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. cobertura
with pop as (:pop)
select coorte, count(*) as emitidos,
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
  from pop group by 1 order by 1;

-- 2. identidade do pedagio: custo_R previsto = 0,0020 / risco%  (risco% medido, nao suposto)
with pop as (:pop), c as (
  select coorte, (exit_base - p_entry/1.0006)/risk - r_exf as custo_medido,
         0.0020/(risk/p_entry) as custo_previsto,
         risk/(atr_pct*p_entry) as stop_atr_efetivo
    from pop where risk > 0
)
select coorte, count(*) as n,
       round(avg(custo_medido),4) as custo_medio_medido,
       round(max(custo_medido),4) as custo_max_medido,
       round(avg(custo_previsto),4) as custo_medio_previsto,
       round(max(abs(custo_medido-custo_previsto)),5) as maior_erro_absoluto,
       round(min(stop_atr_efetivo),4) as stop_atr_efetivo_min,
       round(avg(stop_atr_efetivo),4) as stop_atr_efetivo_medio,
       round(max(stop_atr_efetivo),4) as stop_atr_efetivo_max
  from c group by 1 order by 1;

-- 3. C5: quantas decisoes uma linha paper recusaria (stop fora de [0,3 %; 3 %] do preco)
with pop as (:pop)
select coorte, count(*) as n,
       count(*) filter (where risk/p_entry > 0.03) as acima_do_teto_paper,
       count(*) filter (where risk/p_entry < 0.003) as abaixo_do_piso_paper,
       round(100.0*count(*) filter (where risk/p_entry > 0.03)/count(*),1) as pct_recusado,
       round(sum(r_net) filter (where risk/p_entry > 0.03),2) as soma_r_acima_do_teto
  from pop where p_entry > 0 group by 1 order by 1;

-- 4. code_ref das variantes contra o pai declarado
select s.key||' '||sv.version as versao, sv.code_ref = pai.code_ref as code_ref_igual_ao_pai,
       right(sv.code_ref, 16) as sufixo
  from strategy_versions sv join strategies s on s.id=sv.strategy_id
  join strategy_versions pai on pai.strategy_id=sv.strategy_id
   and pai.version = substring(sv.changelog from 'derived_from=(v[0-9]+)')
 where (s.key,sv.version) in (('momentum','v7'),('momentum','v8'),('mean_reversion','v4'),
                              ('mean_reversion','v5'),('mean_reversion','v6'),('mean_reversion','v7'))
 order by 1;
commit;
