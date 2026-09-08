-- T3.32 item 6 (suporte) — contrafactual DENTRO DA AMOSTRA (gera hipótese, não confirma):
-- se a versão só tivesse decidido quando o risco inicial fosse >= X% do preço,
-- qual seria a expectancy? Não é backtest de variante: a seleção é aplicada às
-- MESMAS entradas congeladas, então o efeito de re-arme e de seleção de entradas
-- não está aqui (é exatamente o que a T3.26 mediu misturar). [[KB-0010]].
\pset border 2
\pset numericlocale off
with pop as (
  select s.key||' '||sv.version as version,
         case when o.meta->>'cohort' like 'replay:%' then 'replay:'||left(split_part(o.meta->>'cohort',':',2),8)
              else 'prospective' end as coorte,
         o.result, o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (a.supporting_features->'atr'->>'value')::numeric as atr0,
         (o.meta->>'reference_price')::numeric as ref_px
  from signal_outcomes o
  join agent_signals a on a.id=o.signal_id
  join strategy_versions sv on sv.id=a.strategy_version_id
  join strategies s on s.id=sv.strategy_id
  where a.emitted_at < timestamptz '2026-09-08 15:00:00+00'  -- corte declarado da leitura
    and o.tracking_state='terminal' and o.r_multiple is not null
), d as (
  select *, risk/(p_entry/1.0006) as risco_pct, atr0/ref_px as atr_pct,
            (exit_base-p_entry/1.0006)/risk as r_gross,
            (exit_base-p_entry/1.0006)/risk - r_exf as custo_r
  from pop where risk>0 and ref_px>0
), t(piso) as (values (0.000),(0.004),(0.006),(0.008),(0.010),(0.012),(0.015),(0.020))
select d.version, d.coorte, t.piso as piso_atr_pct,
       count(*) n, round(100.0*count(*)/max(tot.total),1) as pct_da_populacao,
       round(avg(d.r_gross),4) bruto_r, round(avg(d.custo_r),4) custo_r,
       round(avg(d.r_net),4) liquido_r, round(sum(d.r_net),2) soma_r,
       round(100.0*count(*) filter (where d.result='target')/count(*),1) acerto
from d cross join t
join lateral (select count(*) total from d d2 where d2.version=d.version and d2.coorte=d.coorte) tot on true
where d.atr_pct >= t.piso
  and (d.version,d.coorte) in (('momentum v2','prospective'),('momentum v2','replay:f8d8279c'),
                               ('volume_anomaly v2','prospective'),('volume_anomaly v2','replay:bac27c12'))
group by 1,2,3 having count(*) >= 15 order by 1,2,3;
