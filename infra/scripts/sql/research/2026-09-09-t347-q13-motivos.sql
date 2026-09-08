-- T3.47 q13 — motivos de saida por coorte e a matriz de transicao pai -> variante.
\set pop 'select left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, a.market_id, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.result::text as motivo, o.tracking_state::text as estado, o.r_multiple as r_net, (o.meta->>\'r_ex_funding\')::numeric as r_exf, (o.meta->\'progress\'->>\'entry\')::numeric as p_entry, (o.meta->\'progress\'->>\'exit_base\')::numeric as exit_base, (o.meta->\'excursions\'->>\'initial_risk\')::numeric as risk from signal_outcomes o join agent_signals a on a.id=o.signal_id where o.meta->>\'cohort\' in (\'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a\',\'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4\',\'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2\',\'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28\',\'replay:66fa85cb-1d51-4330-a00b-00964b430ab4\',\'replay:9d99748b-21b9-44a7-8980-32c37b931e6e\',\'replay:264b227f-5bc0-4930-8c5b-2e883c0a858e\',\'replay:293d98b7-90e1-4dfe-a604-60556f3b175e\',\'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd\')'
\set par 'select * from (values (\'A1 mr v3->v4 x1,5\',\'f4af4ffe\',\'af24ee08\'),(\'A2 mr v3->v5 x2\',\'f4af4ffe\',\'66fa85cb\'),(\'B1 mr v2->v6 x1,5\',\'d570b19a\',\'9d99748b\'),(\'B2 mr v2->v7 x2\',\'d570b19a\',\'264b227f\'),(\'C1 mom v6->v7 x1,5\',\'9a08835a\',\'293d98b7\'),(\'C2 mom v6->v8 x2\',\'9a08835a\',\'ee11d60b\')) as t(rotulo,pai,var)'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- motivos de saida, populacao inteira de cada coorte
with pop as (:pop)
select coorte, motivo, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (partition by coorte), 1) as pct,
       round(avg(r_net), 4) as r_liq_medio, round(sum(r_net), 2) as r_liq_soma,
       round(avg((exit_base - p_entry/1.0006)/risk), 4) as r_bruto_medio
  from pop group by 1,2 order by 1, 3 desc;

-- a matriz de transicao: para onde foi cada saida do pai
with pop as (:pop), par as (:par)
select k.rotulo, p.motivo as motivo_pai, v.motivo as motivo_var, count(*) as n,
       round(avg(v.r_net - p.r_net), 4) as delta_liq_medio_r,
       round(sum(v.r_net - p.r_net), 2) as delta_soma_r
  from par k
  join pop p on p.coorte=k.pai
  join pop v on v.coorte=k.var and v.market_id=p.market_id and v.bar=p.bar
 where p.r_net is not null and v.r_net is not null
 group by 1,2,3 order by 1, 6 desc;
commit;
