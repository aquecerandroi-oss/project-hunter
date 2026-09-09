-- T3.47b q15 — o teto de pedagio prometido pelo brief (0,0020/(1,5*0,006) = 0,222 R)
-- contra o pedagio medido decisao a decisao na v8; e a banda de stop do paper_v1
-- separada por faixa de ATR%. Somente leitura.
\set pop 'select left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, (o.meta->>\'r_ex_funding\')::numeric as r_exf, (o.meta->\'progress\'->>\'entry\')::numeric as p_entry, (o.meta->\'progress\'->>\'exit_base\')::numeric as exit_base, (o.meta->\'excursions\'->>\'initial_risk\')::numeric as risk, (a.supporting_features->\'atr\'->>\'percent\')::numeric as atr_pct, o.r_multiple as r_net from signal_outcomes o join agent_signals a on a.id=o.signal_id where o.meta->>\'cohort\' in (\'replay:8ac79cca-916b-4f7f-bd83-01b068b9f811\',\'replay:d0f77894-1e04-454e-a49f-d9a98d894968\')'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. o teto declarado contra o medido
with pop as (:pop), c as (
  select coorte, (exit_base - p_entry/1.0006)/risk - r_exf as custo, risk/p_entry as risco_pct,
         risk/(atr_pct*p_entry) as stop_atr_efetivo, atr_pct
    from pop where risk > 0
)
select coorte,
       case when coorte='8ac79cca' then 0.2222 else 0.3333 end as teto_declarado_r,
       count(*) as n,
       round(max(custo),4) as pedagio_max_medido,
       count(*) filter (where custo > case when coorte='8ac79cca' then 0.2222 else 0.3333 end) as acima_do_teto,
       round(min(stop_atr_efetivo),4) as stop_atr_ef_min,
       round(min(atr_pct),5) as atr_pct_min_observado,
       round(min(risco_pct),5) as risco_pct_min
  from c group by 1 order by 1;

-- 2. banda de stop do paper_v1 por faixa de ATR%
with pop as (:pop)
select coorte,
       case when atr_pct >= 0.008 then 'ja existia (>= 0,008)' else 'NOVA [0,006; 0,008)' end as faixa,
       count(*) as n,
       count(*) filter (where risk/p_entry > 0.03) as acima_do_teto_paper,
       count(*) filter (where risk/p_entry < 0.003) as abaixo_do_piso_paper,
       round((percentile_cont(0.5) within group (order by risk/p_entry))::numeric,5) as risco_pct_p50
  from pop where p_entry > 0 group by 1,2 order by 1,2 desc;
commit;
