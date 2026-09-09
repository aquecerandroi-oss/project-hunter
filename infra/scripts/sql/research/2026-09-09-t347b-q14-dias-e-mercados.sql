-- T3.47b q14 — onde as decisoes novas caem: R por dia e concentracao por mercado (K6)
-- no fatorial 2x2 do piso x stop. Somente leitura.
\set pop 'select s.key||\' \'||sv.version as versao, left(split_part(o.meta->>\'cohort\',\':\',2),8) as coorte, m.symbol, (o.meta->\'entry_plan\'->>\'source_bar_close\')::timestamptz as bar, o.r_multiple as r_net, (a.supporting_features->\'atr\'->>\'percent\')::numeric as atr_pct from signal_outcomes o join agent_signals a on a.id=o.signal_id join markets m on m.id=a.market_id join strategy_versions sv on sv.id=a.strategy_version_id join strategies s on s.id=sv.strategy_id where o.meta->>\'cohort\' in (\'replay:d0f77894-1e04-454e-a49f-d9a98d894968\',\'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a\',\'replay:9d99748b-21b9-44a7-8980-32c37b931e6e\',\'replay:8ac79cca-916b-4f7f-bd83-01b068b9f811\')'
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. R por dia nas quatro coortes
with pop as (:pop)
select bar::date as dia,
       count(*) filter (where coorte='d570b19a') as n_v2,
       round(sum(r_net) filter (where coorte='d570b19a'),2) as r_v2,
       count(*) filter (where coorte='d0f77894') as n_v1,
       round(sum(r_net) filter (where coorte='d0f77894'),2) as r_v1,
       count(*) filter (where coorte='9d99748b') as n_v6,
       round(sum(r_net) filter (where coorte='9d99748b'),2) as r_v6,
       count(*) filter (where coorte='8ac79cca') as n_v8,
       round(sum(r_net) filter (where coorte='8ac79cca'),2) as r_v8
  from pop group by 1 order by 1;

-- 2. concentracao por mercado (K6: >= 60 % num unico mercado)
with pop as (:pop)
select versao, coorte, symbol, count(*) as n,
       round(100.0*count(*)/sum(count(*)) over (partition by coorte),1) as pct,
       round(sum(r_net),2) as soma_r
  from pop group by 1,2,3 order by 1, n desc;
commit;
