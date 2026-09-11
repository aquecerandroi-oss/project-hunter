-- D-P19 q05 — dump CSV: apostas únicas por hora de Brasília (a hora da DECISÃO/entrada)
-- Somente leitura. Uma linha por (hora_brt, escopo), escopo em {'todos', 'os_16'}.
-- Colunas: escopo, hora_brt, apostas_unicas, dias, r_soma, r_medio, acertos, com_r, mercados
-- Dedupe = (market_id, meta.entry_plan.source_bar_close), vence activated_at mais antigo (T3.78).
-- Uso:
--   ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -q -f -" \
--     < este arquivo > .claude/state/exp-drafts/dp19/apostas_por_hora.csv
begin transaction isolation level repeatable read read only;

copy (
  with desfechos as (
    select so.signal_id,
           sig.market_id,
           m.symbol,
           m.symbol in ('ARBUSDT','BNBUSDT','BTCUSDT','DASHUSDT','DOGEUSDT','ETHUSDT','LINKUSDT',
                        'NEARUSDT','PROMUSDT','SAHARAUSDT','SOLUSDT','SUIUSDT','TAOUSDT','UNIUSDT',
                        'XRPUSDT','ZECUSDT') as nos_16,
           sv.activated_at,
           sv.id as strategy_version_id,
           (so.meta->'entry_plan'->>'source_bar_close')::timestamptz as source_bar_close,
           (so.entry_ts at time zone 'America/Sao_Paulo')::date as dia_brt,
           extract(hour from (so.entry_ts at time zone 'America/Sao_Paulo'))::int as hora_brt,
           so.r_multiple
      from signal_outcomes so
      join agent_signals sig on sig.id = so.signal_id
      join strategy_versions sv on sv.id = sig.strategy_version_id
      join strategies s on s.id = sv.strategy_id
      join markets m on m.id = sig.market_id
     where so.meta->>'cohort' = 'prospective'
       and so.tracking_state = 'terminal'
       and so.entry_ts >= now() - interval '30 days'
       and s.key like 'mean_reversion%'
  ), unicas as (
    select distinct on (market_id, source_bar_close) *
      from desfechos
     order by market_id, source_bar_close, activated_at asc, strategy_version_id, signal_id
  )
  select 'todos' as escopo, hora_brt, count(*) as apostas_unicas,
         count(distinct dia_brt) as dias, round(sum(r_multiple), 6) as r_soma,
         round(avg(r_multiple), 6) as r_medio,
         count(*) filter (where r_multiple > 0) as acertos,
         count(*) filter (where r_multiple is not null) as com_r,
         count(distinct symbol) as mercados
    from unicas group by 1, 2
  union all
  select 'os_16', hora_brt, count(*), count(distinct dia_brt), round(sum(r_multiple), 6),
         round(avg(r_multiple), 6), count(*) filter (where r_multiple > 0),
         count(*) filter (where r_multiple is not null), count(distinct symbol)
    from unicas where nos_16 group by 1, 2
  order by 1, 2
) to stdout with (format csv, header true);

commit;
