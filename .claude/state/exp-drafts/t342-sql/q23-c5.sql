-- T3.42 q23 — C5: decisoes cujo stop (1 ATR) sai da banda do preset paper_v1 [0,003; 0,03].
begin transaction isolation level repeatable read read only;
\pset border 2
\pset numericlocale off
with pop as (
  select left(split_part(o.meta->>'cohort',':',2),8) as coorte,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct,
         o.r_multiple as r_net
    from signal_outcomes o join agent_signals a on a.id=o.signal_id
   where o.meta->>'cohort' in ('replay:d0f77894-1e04-454e-a49f-d9a98d894968',
                               'replay:d570b19a-f6e2-4312-86ed-9394b16ac81a',
                               'replay:f4af4ffe-da8b-47e4-9ad2-6af83aca59e4')
)
select coorte, count(*) as n,
       count(*) filter (where atr_pct > 0.03) as acima_do_teto_paper,
       count(*) filter (where atr_pct < 0.003) as abaixo_do_piso_paper,
       round(sum(r_net) filter (where atr_pct > 0.03),2) as soma_r_acima_do_teto
  from pop group by 1 order by 1;
commit;
