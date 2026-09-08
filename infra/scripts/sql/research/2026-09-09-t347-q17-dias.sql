-- T3.47 q17 — R por dia nas coortes de cada familia (o teste visual de concentracao).
\set pop 'select left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz::date as dia, o.r_multiple as r_net from signal_outcomes o join agent_signals a on a.id=o.signal_id where o.r_multiple is not null and o.meta->>\'cohort\' in (\'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a\',\'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4\',\'replay:9a08835a-ae13-4c23-b521-734b2f60a3a2\',\'replay:af24ee08-01cf-41ba-9b7a-1b43172bea28\',\'replay:66fa85cb-1d51-4330-a00b-00964b430ab4\',\'replay:9d99748b-21b9-44a7-8980-32c37b931e6e\',\'replay:264b227f-5bc0-4930-8c5b-2e883c0a858e\',\'replay:293d98b7-90e1-4dfe-a604-60556f3b175e\',\'replay:ee11d60b-3a4e-48be-94a3-1aecb8cf16fd\')'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- familia mean_reversion: pai v2 e v3 e as quatro variantes
with pop as (:pop)
select dia,
       count(*) filter (where coorte='d570b19a') as n_v2, round(sum(r_net) filter (where coorte='d570b19a'),2) as r_v2,
       count(*) filter (where coorte='9d99748b') as n_v6, round(sum(r_net) filter (where coorte='9d99748b'),2) as r_v6,
       count(*) filter (where coorte='264b227f') as n_v7, round(sum(r_net) filter (where coorte='264b227f'),2) as r_v7,
       count(*) filter (where coorte='f4af4ffe') as n_v3, round(sum(r_net) filter (where coorte='f4af4ffe'),2) as r_v3,
       count(*) filter (where coorte='af24ee08') as n_v4, round(sum(r_net) filter (where coorte='af24ee08'),2) as r_v4,
       count(*) filter (where coorte='66fa85cb') as n_v5, round(sum(r_net) filter (where coorte='66fa85cb'),2) as r_v5
  from pop where coorte in ('d570b19a','9d99748b','264b227f','f4af4ffe','af24ee08','66fa85cb')
 group by 1 order by 1;

-- familia momentum: pai v6 e as duas variantes, por dia
with pop as (:pop)
select dia,
       count(*) filter (where coorte='9a08835a') as n_v6, round(sum(r_net) filter (where coorte='9a08835a'),2) as r_v6,
       count(*) filter (where coorte='293d98b7') as n_v7, round(sum(r_net) filter (where coorte='293d98b7'),2) as r_v7,
       count(*) filter (where coorte='ee11d60b') as n_v8, round(sum(r_net) filter (where coorte='ee11d60b'),2) as r_v8
  from pop where coorte in ('9a08835a','293d98b7','ee11d60b')
 group by 1 order by 1;
commit;
