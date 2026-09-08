-- T3.47 q11 — avaliacao pareada por (mercado, barra) das seis variantes contra o pai.
-- Metodo T3.26/T3.40/T3.42: quatro grupos + o delta pareado sinal a sinal.
-- Sem tabela temporaria: a transacao e READ ONLY e o Postgres recusa CREATE TABLE nela.
\set pop 'select s.key||\' \'||sv.version as versao, left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, a.market_id, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.result::text as motivo, o.tracking_state::text as estado, o.r_multiple as r_net, (o.meta->>\'r_ex_funding\')::numeric as r_exf, (o.meta->\'progress\'->>\'entry\')::numeric as p_entry, (o.meta->\'progress\'->>\'exit_base\')::numeric as exit_base, (o.meta->\'excursions\'->>\'initial_risk\')::numeric as risk, (a.supporting_features->\'atr\'->>\'percent\')::numeric as atr_pct from signal_outcomes o join agent_signals a on a.id=o.signal_id join strategy_versions sv on sv.id=a.strategy_version_id join strategies s on s.id=sv.strategy_id where o.meta->>\'cohort\' in (\'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a\',\'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4\',\'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2\',\'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28\',\'replay:66fa85cb-1d51-4330-a00b-00964b430ab4\',\'replay:9d99748b-21b9-44a7-8980-32c37b931e6e\',\'replay:264b227f-5bc0-4930-8c5b-2e883c0a858e\',\'replay:293d98b7-90e1-4dfe-a604-60556f3b175e\',\'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd\')'
\set par 'select * from (values (\'A1 mr v3 -> v4 (stop x1,5)\',\'f4af4ffe\',\'af24ee08\'),(\'A2 mr v3 -> v5 (stop x2)\',\'f4af4ffe\',\'66fa85cb\'),(\'B1 mr v2 -> v6 (stop x1,5)\',\'d570b19a\',\'9d99748b\'),(\'B2 mr v2 -> v7 (stop x2)\',\'d570b19a\',\'264b227f\'),(\'C1 mom v6 -> v7 (stop x1,5)\',\'9a08835a\',\'293d98b7\'),(\'C2 mom v6 -> v8 (stop x2)\',\'9a08835a\',\'ee11d60b\')) as t(rotulo,pai,var)'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

with pop as (:pop), par as (:par),
 g as (
  select k.rotulo, 'pai pareado com a variante' as grupo, p.*
    from par k join pop p on p.coorte=k.pai
   where exists (select 1 from pop v where v.coorte=k.var and v.market_id=p.market_id and v.bar=p.bar)
  union all
  select k.rotulo, 'pai SEM par na variante', p.*
    from par k join pop p on p.coorte=k.pai
   where not exists (select 1 from pop v where v.coorte=k.var and v.market_id=p.market_id and v.bar=p.bar)
  union all
  select k.rotulo, 'variante pareada com o pai', v.*
    from par k join pop v on v.coorte=k.var
   where exists (select 1 from pop p where p.coorte=k.pai and p.market_id=v.market_id and p.bar=v.bar)
  union all
  select k.rotulo, 'variante SEM par no pai', v.*
    from par k join pop v on v.coorte=k.var
   where not exists (select 1 from pop p where p.coorte=k.pai and p.market_id=v.market_id and p.bar=v.bar)
 )
select rotulo, grupo, count(*) as n,
       count(*) filter (where r_net is not null) as avaliaveis,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as exp_bruta_r,
       round(avg((exit_base - p_entry/1.0006)/risk - r_exf), 4) as custo_r,
       round(avg(r_net), 4) as exp_liquida_r, round(sum(r_net), 2) as soma_r,
       round(100.0*count(*) filter (where motivo='target')/nullif(count(*) filter (where estado='terminal'),0),1) as acerto_pct,
       count(distinct bar::date) as dias
  from g group by 1,2 order by 1,2;

with pop as (:pop), par as (:par)
select k.rotulo, count(*) as pares,
       round(avg(v.r_net - p.r_net), 4) as delta_liq_medio_r,
       round(sum(v.r_net - p.r_net), 2) as delta_liq_soma_r,
       round(avg((v.exit_base - v.p_entry/1.0006)/v.risk - (p.exit_base - p.p_entry/1.0006)/p.risk), 4) as delta_bruto_medio_r,
       round(avg(((v.exit_base - v.p_entry/1.0006)/v.risk - v.r_exf) - ((p.exit_base - p.p_entry/1.0006)/p.risk - p.r_exf)), 4) as delta_custo_medio_r,
       round(avg(v.risk/p.risk), 4) as razao_risco_medio,
       count(*) filter (where v.motivo = p.motivo) as mesmo_motivo,
       count(distinct p.bar::date) as dias
  from par k
  join pop p on p.coorte=k.pai
  join pop v on v.coorte=k.var and v.market_id=p.market_id and v.bar=p.bar
 where p.r_net is not null and v.r_net is not null
 group by 1 order by 1;
commit;
