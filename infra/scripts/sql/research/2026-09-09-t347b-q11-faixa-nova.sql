-- T3.47b q11 — o que o piso mais baixo comprou: as decisoes NOVAS (ATR% na faixa
-- [0,006; 0,008)) contra as que ja existiam (ATR% >= 0,008), nas duas colunas de stop;
-- e o pareamento (mercado, barra) entre v8 e v6 e entre v1 e v2.
-- Somente leitura.
\set pop 'select s.key||\' \'||sv.version as versao, left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, m.symbol, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.result::text as motivo, o.tracking_state::text as estado, o.r_multiple as r_net, (o.meta->>\'r_ex_funding\')::numeric as r_exf, (o.meta->\'progress\'->>\'entry\')::numeric as p_entry, (o.meta->\'progress\'->>\'exit_base\')::numeric as exit_base, (o.meta->\'excursions\'->>\'initial_risk\')::numeric as risk, (a.supporting_features->\'atr\'->>\'percent\')::numeric as atr_pct from signal_outcomes o join agent_signals a on a.id=o.signal_id join markets m on m.id=a.market_id join strategy_versions sv on sv.id=a.strategy_version_id join strategies s on s.id=sv.strategy_id where o.meta->>\'cohort\' in (\'replay:d0f77894-1e04-454e-a49f-d9a98d894968\',\'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a\',\'replay:9d99748b-21b9-44a7-8980-32c37b931e6e\',\'replay:8ac79cca-916b-4f7f-bd83-01b068b9f811\')'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. dentro de cada coorte de piso 0,006: a faixa nova contra a faixa que ja existia
with pop as (:pop)
select versao, coorte,
       case when atr_pct >= 0.008 then 'ja existia (ATR% >= 0,008)' else 'NOVA (ATR% em [0,006; 0,008))' end as faixa,
       count(*) as n,
       round(avg((exit_base - p_entry/1.0006)/risk) filter (where risk>0),4) as exp_bruta_r,
       round(avg((exit_base - p_entry/1.0006)/risk - r_exf) filter (where risk>0),4) as custo_medio_r,
       round(avg(r_net),4) as exp_liquida_r,
       round(sum(r_net),2) as soma_r,
       round(100.0*count(*) filter (where motivo='target')/count(*),1) as acerto_pct,
       round(sum(r_net) filter (where r_net>0)/nullif(-sum(r_net) filter (where r_net<0),0),4) as pf_liquido,
       count(distinct bar::date) as dias,
       round((percentile_cont(0.5) within group (order by atr_pct))::numeric,5) as atr_pct_p50
  from pop where coorte in ('8ac79cca','d0f77894') group by 1,2,3 order by 1,3 desc;

-- 2. pareamento por (mercado, barra) entre v8 (0,006/1,5) e v6 (0,008/1,5)
with pop as (:pop), v8 as (select * from pop where coorte='8ac79cca'),
     v6 as (select * from pop where coorte='9d99748b')
select case when v8.bar is not null and v6.bar is not null then 'nas duas'
            when v8.bar is not null then 'so na v8 (piso 0,006)'
            else 'so na v6 (piso 0,008)' end as grupo,
       count(*) as n,
       round(avg(coalesce(v8.r_net, v6.r_net)),4) as exp_liquida_r,
       round(sum(coalesce(v8.r_net, v6.r_net)),2) as soma_r,
       round(min(coalesce(v8.atr_pct, v6.atr_pct)),5) as atr_min,
       round(max(coalesce(v8.atr_pct, v6.atr_pct)),5) as atr_max
  from v8 full outer join v6 on v6.symbol=v8.symbol and v6.bar=v8.bar
 group by 1 order by 1;

-- 3. as decisoes da v6 que sumiram na v8, uma a uma (ocupacao de slot?)
with pop as (:pop), v8 as (select * from pop where coorte='8ac79cca'),
     v6 as (select * from pop where coorte='9d99748b')
select v6.symbol, to_char(v6.bar,'YYYY-MM-DD HH24:MI') as barra, round(v6.atr_pct,5) as atr_pct,
       v6.motivo, round(v6.r_net,4) as r_net,
       (select count(*) from v8 x where x.symbol=v6.symbol
          and x.bar < v6.bar and x.bar > v6.bar - interval '4 hours') as v8_abertas_antes_4h
  from v6 left join v8 on v8.symbol=v6.symbol and v8.bar=v6.bar
 where v8.bar is null order by v6.symbol, v6.bar;

-- 4. o mesmo pareamento entre v1 (0,006/1,0) e v2 (0,008/1,0)
with pop as (:pop), v1 as (select * from pop where coorte='d0f77894'),
     v2 as (select * from pop where coorte='d570b19a')
select case when v1.bar is not null and v2.bar is not null then 'nas duas'
            when v1.bar is not null then 'so na v1 (piso 0,006)'
            else 'so na v2 (piso 0,008)' end as grupo,
       count(*) as n,
       round(avg(coalesce(v1.r_net, v2.r_net)),4) as exp_liquida_r,
       round(sum(coalesce(v1.r_net, v2.r_net)),2) as soma_r,
       round(min(coalesce(v1.atr_pct, v2.atr_pct)),5) as atr_min,
       round(max(coalesce(v1.atr_pct, v2.atr_pct)),5) as atr_max
  from v1 full outer join v2 on v2.symbol=v1.symbol and v2.bar=v1.bar
 group by 1 order by 1;
commit;
