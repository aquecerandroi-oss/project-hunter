-- T3.60 q01 — a população da família mean_reversion, uma linha por desfecho, em
-- CSV no stdout do psql. SOMENTE LEITURA; nada é escrito na VPS.
--
-- Uma linha = um sinal com desfecho terminal e `r_multiple`, com TUDO o que o
-- simulador de carteira precisa para chamar `hunter_risk.evaluate` de verdade:
--
--   geometria      : p_entry (preço executado, já com os 6 bps de entrada do Lab),
--                    entry_base = p_entry/1.0006, risk = |entrada − stop| em preço,
--                    risco_pct = risk/entry_base  → é exatamente o que o check 8
--                    (`stop_distance`) mede contra [0,003; 0,03]
--   relógio        : bar (source_bar_close, a vela que a estratégia leu),
--                    entry_ts (a barra seguinte, onde a ordem entraria),
--                    exit_ts  (quando a posição libera a vaga)
--   resultado      : r_net (com custo e funding), r_exf, motivo
--   mercado        : symbol, base_asset, min_notional, step_size
--   liquidez REAL do instante da entrada, das velas de 1 min:
--                    vol_min_anterior  = quote_volume de [t−1m, t)
--                    vol_mediana_30    = mediana de quote_volume em [t−30m, t)
--                    barras_30         = quantas dessas 30 barras existem (o motor
--                                        exige a janela COMPLETA: barra ausente é
--                                        indisponibilidade, nunca zero — §4)
--                    vol_24h           = soma de quote_volume em [t−24h, t)
--                                        → é o insumo do check 9 (`liquidity_24h`,
--                                        piso de 50 M USD)
--   custos         : os `assumed_costs` que o próprio Lab usou (fee/spread/slippage
--                    em bps), para o simulador não inventar hipótese de custo.
--
-- t = date_trunc('minute', entry_ts). A referência de participação do motor é
-- min(último minuto completo, mediana de 30 barras completas) — a fórmula está no
-- simulador, não aqui: esta consulta entrega os dois insumos crus.
begin transaction isolation level repeatable read read only;

copy (
  with pop as (
    select o.signal_id,
           s.key || ' ' || sv.version as versao,
           sv.version as versao_num,
           case when coalesce(a.supporting_features->>'cohort', o.meta->>'cohort', '') like 'replay:%'
                then 'replay' else 'prospective' end as coorte,
           a.market_id, m.symbol, ba.symbol as base_asset,
           coalesce(m.min_notional, 5)          as min_notional,
           coalesce(m.step_size, 0.00000001)    as step_size,
           (o.meta->'entry_plan'->>'source_bar_close')::timestamptz as bar,
           o.entry_ts, o.exit_ts,
           date_trunc('minute', o.entry_ts) as t,
           o.result::text as motivo,
           o.r_multiple as r_net,
           (o.meta->>'r_ex_funding')::numeric                as r_exf,
           (o.meta->'progress'->>'entry')::numeric           as p_entry,
           (o.meta->'progress'->>'exit_base')::numeric       as exit_base,
           (o.meta->'excursions'->>'initial_risk')::numeric  as risk,
           (o.meta->'excursions'->>'mae')::numeric           as mae,
           (o.meta->'excursions'->>'mae_bar')::timestamptz   as mae_bar,
           (o.meta->'assumed_costs'->>'fee_bps')::numeric      as fee_bps,
           (o.meta->'assumed_costs'->>'spread_bps')::numeric   as spread_bps,
           (o.meta->'assumed_costs'->>'slippage_bps')::numeric as slippage_bps
      from signal_outcomes o
      join agent_signals a      on a.id  = o.signal_id
      join markets m            on m.id  = a.market_id
      join assets ba            on ba.id = m.base_asset_id
      join strategy_versions sv on sv.id = a.strategy_version_id
      join strategies s         on s.id  = sv.strategy_id
     where s.key = 'mean_reversion'
       and o.tracking_state = 'terminal'
       and o.r_multiple is not null
       and o.entry_ts is not null and o.exit_ts is not null
       and (o.meta->'excursions'->>'initial_risk')::numeric > 0
  )
  select p.signal_id, p.versao, p.versao_num, p.coorte, p.symbol, p.base_asset,
         to_char(p.bar      at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as bar_utc,
         to_char(p.entry_ts at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as entry_utc,
         to_char(p.exit_ts  at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as exit_utc,
         to_char(p.entry_ts at time zone 'America/Sao_Paulo', 'YYYY-MM-DD')   as dia_br,
         extract(hour from (p.entry_ts at time zone 'America/Sao_Paulo'))::int as hora_br,
         p.motivo, p.r_net, p.r_exf,
         p.p_entry,
         round(p.p_entry / 1.0006, 12)                             as entry_base,
         p.risk,
         round(p.risk / (p.p_entry / 1.0006), 8)                   as risco_pct,
         p.mae,
         to_char(p.mae_bar at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')  as mae_bar_utc,
         p.min_notional, p.step_size,
         p.fee_bps, p.spread_bps, p.slippage_bps,
         v.vol_min_anterior, v.vol_mediana_30, v.barras_30, v.vol_24h, v.barras_24h
    from pop p
    left join lateral (
      select
        (select c.quote_volume from candles c
          where c.market_id = p.market_id and c.timeframe = '1m' and c.is_final
            and c.open_time = p.t - interval '1 minute')                      as vol_min_anterior,
        (select percentile_cont(0.5) within group (order by c.quote_volume)
           from candles c
          where c.market_id = p.market_id and c.timeframe = '1m' and c.is_final
            and c.open_time >= p.t - interval '30 minutes' and c.open_time < p.t) as vol_mediana_30,
        (select count(*) from candles c
          where c.market_id = p.market_id and c.timeframe = '1m' and c.is_final
            and c.open_time >= p.t - interval '30 minutes' and c.open_time < p.t) as barras_30,
        (select sum(c.quote_volume) from candles c
          where c.market_id = p.market_id and c.timeframe = '1m' and c.is_final
            and c.open_time >= p.t - interval '24 hours' and c.open_time < p.t)   as vol_24h,
        (select count(*) from candles c
          where c.market_id = p.market_id and c.timeframe = '1m' and c.is_final
            and c.open_time >= p.t - interval '24 hours' and c.open_time < p.t)   as barras_24h
    ) v on true
   order by p.entry_ts, p.versao
) to stdout with (format csv, header true);

commit;
