-- D-P19 q01 — dump do volume em quote (USDT) de cada minuto, 30 dias, os 16 mercados e os gêmeos SPOT
-- Somente leitura. Saída CSV no stdout (cabeçalho incluído); o rolling median de 30 barras e os
-- percentis por hora são calculados fora do banco, em Decimal (dp19/meta_em_dinheiro.py).
-- Uso:
--   ssh hunter-vps "docker exec -i hunter-postgres-1 psql -U hunter -d hunter -v ON_ERROR_STOP=1 -q -f - | gzip -c" \
--     < este arquivo > .claude/state/exp-drafts/dp19/volume_1m.csv.gz
begin transaction isolation level repeatable read read only;

copy (
  select m.symbol,
         m.market_type::text as tipo,
         to_char(c.open_time at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS') as open_time_utc,
         c.quote_volume
    from candles_1m c
    join markets m on m.id = c.market_id
    join exchanges e on e.id = m.exchange_id
   where e.code = 'binance'
     and c.open_time >= date_trunc('minute', now()) - interval '30 days'
     and c.open_time <  date_trunc('minute', now())
     and c.is_final
     and m.symbol in ('ARBUSDT','BNBUSDT','BTCUSDT','DASHUSDT','DOGEUSDT','ETHUSDT','LINKUSDT',
                      'NEARUSDT','PROMUSDT','SAHARAUSDT','SOLUSDT','SUIUSDT','TAOUSDT','UNIUSDT',
                      'XRPUSDT','ZECUSDT')
   order by m.symbol, m.market_type::text, c.open_time
) to stdout with (format csv, header true);

commit;
