-- T3.42 q11 — os quatro grupos pareados por (mercado, barra), metodo T3.26/T3.40.
\set pop 'select s.key||\' \'||sv.version as versao, left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, a.market_id, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.result::text as motivo, o.tracking_state::text as estado, o.r_multiple as r_net, (o.meta->>\'r_ex_funding\')::numeric as r_exf, (o.meta->\'progress\'->>\'entry\')::numeric as p_entry, (o.meta->\'progress\'->>\'exit_base\')::numeric as exit_base, (o.meta->\'excursions\'->>\'initial_risk\')::numeric as risk, (a.supporting_features->\'atr\'->>\'percent\')::numeric as atr_pct from signal_outcomes o join agent_signals a on a.id=o.signal_id join strategy_versions sv on sv.id=a.strategy_version_id join strategies s on s.id=sv.strategy_id where o.meta->>\'cohort\' in (\'replay:d0f77894-1e04-454e-a49f-d9a98d894968\',\'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a\',\'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4\')'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- a populacao do pai partida pelos dois pisos
with pop as (:pop)
select case when atr_pct >= 0.010 then 'pai ACIMA de 0,010'
            when atr_pct >= 0.008 then 'pai em [0,008; 0,010)'
            else 'pai ABAIXO de 0,008' end as faixa,
       count(*) as n,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as exp_bruta_r,
       round(avg((exit_base - p_entry/1.0006)/risk - r_exf), 4) as custo_r,
       round(avg(r_net), 4) as exp_liquida_r, round(sum(r_net), 2) as soma_r,
       count(*) filter (where motivo='expired') as saidas_horizonte,
       round(sum(r_net) filter (where motivo='expired'), 2) as soma_r_horizonte
  from pop where coorte='d0f77894' group by 1 order by 1;

-- V1: os quatro grupos pareados
with pop as (:pop),
     pai as (select * from pop where coorte='d0f77894'),
     var as (select * from pop where coorte='d570b19a'),
     g as (
       select 'pai pareado com a variante' as grupo, p.* from pai p
        where exists (select 1 from var v where v.market_id=p.market_id and v.bar=p.bar)
       union all
       select 'pai SEM par na variante', p.* from pai p
        where not exists (select 1 from var v where v.market_id=p.market_id and v.bar=p.bar)
       union all
       select 'variante pareada com o pai', v.* from var v
        where exists (select 1 from pai p where p.market_id=v.market_id and p.bar=v.bar)
       union all
       select 'variante SEM par no pai', v.* from var v
        where not exists (select 1 from pai p where p.market_id=v.market_id and p.bar=v.bar)
     )
select 'V1 (v2, piso 0,008)' as variante, grupo, count(*) as n,
       count(*) filter (where r_net is not null) as avaliaveis,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as exp_bruta_r,
       round(avg((exit_base - p_entry/1.0006)/risk - r_exf), 4) as custo_r,
       round(avg(r_net), 4) as exp_liquida_r, round(sum(r_net), 2) as soma_r,
       round(100.0*count(*) filter (where motivo='target')/nullif(count(*) filter (where estado='terminal'),0),1) as acerto_pct,
       round(sum(r_net) filter (where r_net>0)/nullif(-sum(r_net) filter (where r_net<0),0),4) as pf_liquido,
       count(distinct bar::date) as dias
  from g group by 1,2 order by 2;

-- V1: o delta pareado, sinal a sinal
with pop as (:pop)
select 'V1 (v2, piso 0,008)' as variante, count(*) as pares,
       round(avg(v.r_net - p.r_net), 4) as delta_liq_medio_r,
       round(sum(v.r_net - p.r_net), 2) as delta_liq_soma_r,
       round(avg((v.exit_base - v.p_entry/1.0006)/v.risk - (p.exit_base - p.p_entry/1.0006)/p.risk), 4) as delta_bruto_medio_r,
       count(*) filter (where v.risk = p.risk) as mesmo_risco_inicial,
       count(*) filter (where v.motivo = p.motivo) as mesmo_motivo,
       count(distinct p.bar::date) as dias
  from pop p join pop v on v.market_id=p.market_id and v.bar=p.bar
 where p.coorte='d0f77894' and v.coorte='d570b19a' and p.r_net is not null and v.r_net is not null;
commit;
