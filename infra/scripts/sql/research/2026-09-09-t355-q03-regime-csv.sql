-- T3.55b q03 — o regime horario do BTC como o sistema o gravou (market_regimes,
-- PIPELINE 4b), em CSV, para o recorte condicional. Uma linha por hora fechada.
-- O consumidor usa a hora ANTERIOR ao fechamento da barra (start_time + 1 h <= close),
-- que e o unico corte que nao le o futuro. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';
\pset format csv
\pset tuples_only off
select scope::text as scope, start_time, end_time, regime::text as regime, confidence, classifier_version
  from market_regimes
 where start_time >= timestamptz '2026-08-07 00:00:00+00'
   and start_time <  timestamptz '2026-09-09 00:00:00+00'
 order by start_time;
commit;
