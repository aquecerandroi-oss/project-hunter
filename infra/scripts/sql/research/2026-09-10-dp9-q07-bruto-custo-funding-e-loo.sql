-- D-P9 q07 -- BRUTO x CUSTO x FUNDING, HORA DA ENTRADA x HORA DA DECISAO, E A
-- SENSIBILIDADE DEIXANDO UM MERCADO DE FORA (leave-one-out), pedidos na linha
-- D-P9 da fila de hipoteses.
-- Identidades usadas (SHADOW-LAB.md 3, funding.py):
--   r_bruto  = (progress.exit_base - progress.entry) / (virtual_entry - virtual_stop)
--   custo_R  = r_bruto - r_ex_funding      (taxas/spread/slippage: 4+2+5 bps por perna)
--   funding_R= r_ex_funding - r_multiple   (positivo = o comprado PAGOU funding)
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off

-- 1. bruto x custo x funding. ATENCAO ao recorte: a hora 21Z de 09/09 sai numa
--    linha propria, entao a linha "09/09" e o dia SEM aquela hora.
with pop as (
  select mk.symbol, s.key || ' ' || sv.version as versao, a.emitted_at,
         o.r_multiple as r_net, (o.meta->>'r_ex_funding')::numeric as r_ex,
         case when (o.virtual_entry - o.virtual_stop) <> 0
              then ((o.meta->'progress'->>'exit_base')::numeric - (o.meta->'progress'->>'entry')::numeric)
                   / (o.virtual_entry - o.virtual_stop) end as r_bruto,
         (a.emitted_at >= '2026-09-09 21:00:00+00' and a.emitted_at < '2026-09-09 22:00:00+00') as hora21z
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date in (date '2026-09-08', date '2026-09-09')
)
select case when hora21z then '09/09 hora 21Z (18 BRT)'
            else to_char(emitted_at at time zone 'America/Sao_Paulo','DD/MM') || ' dia BRT SEM a hora 21Z de 09/09' end as recorte,
       count(*) n,
       round(sum(r_bruto),3) soma_bruto,
       round(sum(r_ex),3)    soma_ex_funding,
       round(sum(r_net),3)   soma_liquido,
       round(sum(r_bruto - r_ex),3) as custo_total_R,
       round(sum(r_ex - r_net),3)   as funding_total_R,
       round(avg(r_bruto - r_ex),4) as custo_medio_R,
       round(avg(r_ex - r_net),4)   as funding_medio_R
  from pop
 group by 1 order by 1;

-- 2. hora da DECISAO x hora da ENTRADA (as duas so diferem quando a decisao cai
--    perto do fim da hora; o atraso de entrada e de ~1-2 min por construcao)
with pop as (
  select extract(hour from a.emitted_at at time zone 'UTC')::int h_dec,
         extract(hour from o.entry_ts  at time zone 'UTC')::int h_ent,
         extract(hour from o.exit_ts   at time zone 'UTC')::int h_sai,
         o.r_multiple as r_net,
         extract(epoch from (o.entry_ts - a.emitted_at)) as atraso_s
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-09'
)
select h_dec as hora_decisao_utc, count(*) n,
       count(*) filter (where h_ent = h_dec) entrou_na_mesma_hora,
       count(*) filter (where h_sai = h_dec) saiu_na_mesma_hora,
       round(avg(atraso_s)::numeric,1) atraso_medio_s,
       round(max(atraso_s)::numeric,1) atraso_max_s,
       round(sum(r_net),3) soma_r
  from pop group by 1 order by 1;

-- 3. leave-one-out: o dia 09/09 BRT sem cada mercado (os 12 de maior impacto)
with pop as (
  select mk.symbol, o.r_multiple as r_net
    from signal_outcomes o
    join agent_signals a      on a.id = o.signal_id
    join markets mk           on mk.id = a.market_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s         on s.id = sv.strategy_id
   where o.meta->>'cohort' = 'prospective'
     and ( (s.key = 'mean_reversion' and sv.version in ('v1','v2','v3','v6','v7','v8','v10','v14'))
        or (s.key = 'mean_reversion_h1' and sv.version = 'v1') )
     and o.tracking_state = 'terminal'
     and (a.emitted_at at time zone 'America/Sao_Paulo')::date = date '2026-09-09'
), total as (select sum(r_net) t, count(r_net) n from pop)
select p.symbol, count(*) n_do_mercado, round(sum(p.r_net),3) r_do_mercado,
       round((select t from total),3) r_do_dia,
       round((select t from total) - coalesce(sum(p.r_net),0),3) r_sem_o_mercado,
       round(((select t from total) - coalesce(sum(p.r_net),0)) / ((select n from total) - count(p.r_net)),4) media_sem_o_mercado
  from pop p group by 1
 order by abs(coalesce(sum(p.r_net),0)) desc limit 12;

commit;
