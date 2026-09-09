-- T3.54 q11 — dump por decisao (versao, coorte, dia UTC, mercado, hora UTC,
-- r liquido, r bruto, custo em R, risco%) das quatro coortes do contraste de
-- timeframe. Entrada do bootstrap de blocos por dia e da lente de sessao.
-- Saida CSV para o stdout. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset format csv
\pset tuples_only off
with pop as (
  select s.key||' '||sv.version as versao,
         'replay:'||left(split_part(o.meta->>'cohort', ':', 2), 8) as coorte,
         m.symbol as mercado,
         (a.emitted_at at time zone 'UTC')::date as dia_utc,
         extract(hour from a.emitted_at at time zone 'UTC')::int as hora_utc,
         extract(hour from a.emitted_at at time zone 'America/Sao_Paulo')::int as hora_brt,
         o.result::text as motivo,
         o.r_multiple as r_net,
         (o.meta->>'r_ex_funding')::numeric as r_exf,
         (o.meta->'progress'->>'entry')::numeric as p_entry,
         (o.meta->'progress'->>'exit_base')::numeric as exit_base,
         (o.meta->'excursions'->>'initial_risk')::numeric as risk,
         (a.supporting_features->'atr'->>'percent')::numeric as atr_pct
    from signal_outcomes o
    join agent_signals a on a.id = o.signal_id
    join strategy_versions sv on sv.id = a.strategy_version_id
    join strategies s on s.id = sv.strategy_id
    join markets m on m.id = a.market_id
   where s.key in ('mean_reversion', 'momentum', 'session_orb')
     and o.meta->>'cohort' like 'replay:%'
     and o.tracking_state::text = 'terminal'
     and o.r_multiple is not null
)
select versao, coorte, dia_utc, hora_utc, hora_brt, mercado, motivo,
       r_net, atr_pct,
       risk / nullif(p_entry, 0) as risco_pct,
       (exit_base - p_entry / 1.0006) / nullif(risk, 0) as r_bruto,
       (exit_base - p_entry / 1.0006) / nullif(risk, 0) - r_exf as custo_r
  from pop
 order by versao, coorte, dia_utc, hora_utc, mercado;
commit;
