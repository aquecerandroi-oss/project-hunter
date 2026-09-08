-- T3.47 q12 — dump dos deltas pareados (rotulo, dia, delta_liq_r) para o bootstrap de blocos.
\set pop 'select left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, a.market_id, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.r_multiple as r_net from signal_outcomes o join agent_signals a on a.id=o.signal_id where o.meta->>\'cohort\' in (\'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a\',\'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4\',\'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2\',\'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28\',\'replay:66fa85cb-1d51-4330-a00b-00964b430ab4\',\'replay:9d99748b-21b9-44a7-8980-32c37b931e6e\',\'replay:264b227f-5bc0-4930-8c5b-2e883c0a858e\',\'replay:293d98b7-90e1-4dfe-a604-60556f3b175e\',\'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd\') and o.r_multiple is not null'
\set par 'select * from (values (\'A1\',\'f4af4ffe\',\'af24ee08\'),(\'A2\',\'f4af4ffe\',\'66fa85cb\'),(\'B1\',\'d570b19a\',\'9d99748b\'),(\'B2\',\'d570b19a\',\'264b227f\'),(\'C1\',\'9a08835a\',\'293d98b7\'),(\'C2\',\'9a08835a\',\'ee11d60b\')) as t(rotulo,pai,var)'
begin transaction isolation level repeatable read read only;
\pset format csv
select k.rotulo, p.bar::date as dia, (v.r_net - p.r_net) as delta_r, p.r_net as r_pai, v.r_net as r_var
  from (:par) k
  join (:pop) p on p.coorte=k.pai
  join (:pop) v on v.coorte=k.var and v.market_id=p.market_id and v.bar=p.bar
 order by 1,2,3;
commit;
