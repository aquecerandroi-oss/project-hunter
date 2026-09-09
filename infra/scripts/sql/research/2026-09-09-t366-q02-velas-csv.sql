-- T3.66 q02 — velas de 1 min `is_final` dos mercados da população, CSV no stdout.
-- SOMENTE LEITURA. Nada é escrito na VPS.
--
-- Por que a série inteira e não só as janelas de acompanhamento: o controle C2 sorteia
-- barras pareadas por (mercado, hora UTC) em TODA a janela da população, então o pool de
-- candidatas precisa da série. Transferir 1,2 M linhas comprimidas é mais barato — e muito
-- mais auditável — do que reimplementar as regras de saída em SQL.
--
-- Janela: [2026-08-09T00:00Z, 2026-09-09T08:00Z) — cobre a primeira barra de origem
-- (2026-08-09T16:45Z) menos o balde de 15 min anterior, e a última (2026-09-09T01:30Z)
-- mais o horizonte de 4 h.
--
-- Só `is_final`: PIPELINE §2 "Anti-look-ahead". Uma vela em formação nunca entra.
begin transaction isolation level repeatable read read only;
copy (
  with mercados as (
    select distinct a.market_id
      from signal_outcomes o
      join agent_signals a      on a.id  = o.signal_id
      join strategy_versions sv on sv.id = a.strategy_version_id
      join strategies s         on s.id  = sv.strategy_id
     where s.key = 'mean_reversion'
       and sv.version in ('v1','v2','v6','v10')
       and a.emitted_at < timestamptz '2026-09-09 02:30:00+00'
       and o.tracking_state = 'terminal'
       and o.r_multiple is not null
  )
  select c.market_id,
         to_char(c.open_time at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as t,
         c.open, c.high, c.low, c.close
    from candles c
    join mercados k on k.market_id = c.market_id
   where c.timeframe = '1m'
     and c.is_final
     and c.open_time >= timestamptz '2026-08-09 00:00:00+00'
     and c.open_time <  timestamptz '2026-09-09 08:00:00+00'
   order by c.market_id, c.open_time
) to stdout with (format csv, header true);
commit;
