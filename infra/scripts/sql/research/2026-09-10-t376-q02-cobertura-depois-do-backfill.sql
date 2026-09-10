-- T3.76 q02 -- A SERIE DE REGIME DEPOIS DO REPARO PROFUNDO DE 90 DIAS.
-- Espelho do q00, rodado depois de
--   `compose.sh ops python -m hunter_scanner_worker.regime_hourly --once --repair-days 90`
-- (tres passadas: 35 d, 90 d e 90 d de novo -- a terceira e a prova de
-- idempotencia, `written: 0`). Responde:
--   1. cobertura das 2161 horas da janela de 90 d (tem de ser 100 %);
--   2. horas por rotulo por mes;
--   3. horas por rotulo nas TRES janelas de 30 dias da T3.62b
--      (J1 06-12->07-12, J2 07-12->08-11, J3 08-11->09-10) -- e por elas que a
--      regra de sucesso da EXP-0026 pede "positivo em 2 das 3";
--   4. quantas horas cada BRACO da EXP-0026 deixaria elegiveis, por janela:
--      v15 = SIDEWAYS + LOW_VOLATILITY, v16 = SIDEWAYS, v17 = HIGH_VOLATILITY,
--      momentum v11 = BTC_BULL + HIGH_VOLATILITY. E o teto de barras da filha;
--   5. onde ficou o aquecimento (UNKNOWN) depois do reparo -- a vela de 1 min do
--      BTC comeca em 2026-06-11 19:00Z e a tendencia precisa de 224 horas
--      contiguas atras, entao as primeiras ~224 horas da janela NAO tem como
--      sair classificadas, e isso e propriedade do dado, nao do produtor.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at, date_trunc('hour', now()) as corte;

-- 1. cobertura
with grade as (
  select generate_series(date_trunc('hour', now()) - interval '90 days',
                         date_trunc('hour', now()), interval '1 hour') as h
), tem as (
  select distinct start_time as h
    from market_regimes
   where scope = 'btc' and classifier_version = 'regime_hourly_v1'
)
select count(*) as horas_da_janela, count(tem.h) as com_linha,
       count(*) - count(tem.h) as sem_linha,
       round(100.0 * count(tem.h) / count(*), 1) as pct_coberto
  from grade left join tem on tem.h = grade.h;

-- 1b. nenhuma hora duplicada (nao ha indice unico em (scope, start_time))
select count(*) as horas_duplicadas
  from (select start_time from market_regimes
         where scope = 'btc' and classifier_version = 'regime_hourly_v1'
         group by 1 having count(*) > 1) d;

-- 2. horas por rotulo por mes
select to_char(date_trunc('month', start_time), 'YYYY-MM') as mes,
       regime::text as rotulo, count(*) as horas
  from market_regimes
 where scope = 'btc' and classifier_version = 'regime_hourly_v1'
   and start_time >= date_trunc('hour', now()) - interval '90 days'
 group by 1, 2 order by 1, 2;

-- 3. horas por rotulo nas tres janelas de 30 dias
with janela as (
  select 'J1 06-12->07-12' as j, timestamptz '2026-06-12 00:00+00' as ini,
         timestamptz '2026-07-12 00:00+00' as fim
  union all select 'J2 07-12->08-11', '2026-07-12 00:00+00', '2026-08-11 00:00+00'
  union all select 'J3 08-11->09-10', '2026-08-11 00:00+00', '2026-09-10 00:00+00'
)
select janela.j, r.regime::text as rotulo, count(*) as horas
  from janela join market_regimes r
    on r.scope = 'btc' and r.classifier_version = 'regime_hourly_v1'
   and r.start_time >= janela.ini and r.start_time < janela.fim
 group by 1, 2 order by 1, 2;

-- 4. horas elegiveis por braco e por janela
with janela as (
  select 'J1 06-12->07-12' as j, timestamptz '2026-06-12 00:00+00' as ini,
         timestamptz '2026-07-12 00:00+00' as fim
  union all select 'J2 07-12->08-11', '2026-07-12 00:00+00', '2026-08-11 00:00+00'
  union all select 'J3 08-11->09-10', '2026-08-11 00:00+00', '2026-09-10 00:00+00'
  union all select 'TOTAL 06-12->09-10', '2026-06-12 00:00+00', '2026-09-10 00:00+00'
)
select janela.j,
       count(*)                                                          as horas,
       count(*) filter (where r.regime::text in ('SIDEWAYS','LOW_VOLATILITY'))     as v15_sw_lowvol,
       count(*) filter (where r.regime::text = 'SIDEWAYS')                         as v16_sw,
       count(*) filter (where r.regime::text = 'HIGH_VOLATILITY')                  as v17_highvol,
       count(*) filter (where r.regime::text in ('BTC_BULL','HIGH_VOLATILITY'))    as mom_v11,
       count(*) filter (where r.regime::text = 'UNKNOWN')                          as unknown
  from janela join market_regimes r
    on r.scope = 'btc' and r.classifier_version = 'regime_hourly_v1'
   and r.start_time >= janela.ini and r.start_time < janela.fim
 group by 1 order by 1;

-- 5. onde ficou o aquecimento
select min(start_time) filter (where regime::text <> 'UNKNOWN') as primeira_hora_classificada,
       max(start_time) filter (where regime::text = 'UNKNOWN')  as ultima_hora_unknown,
       count(*) filter (where regime::text = 'UNKNOWN')         as horas_unknown,
       count(*)                                                 as horas_totais
  from market_regimes
 where scope = 'btc' and classifier_version = 'regime_hourly_v1'
   and start_time >= date_trunc('hour', now()) - interval '90 days';

-- 5b. o motivo declarado do aquecimento, contado (`reasons` e uma lista)
select coalesce(motivo, '(sem motivo)') as motivo, count(*) as horas
  from market_regimes r
  left join lateral jsonb_array_elements_text(r.supporting_features -> 'reasons')
       as t(motivo) on true
 where r.scope = 'btc' and r.classifier_version = 'regime_hourly_v1'
   and r.regime::text = 'UNKNOWN'
   and r.start_time >= date_trunc('hour', now()) - interval '90 days'
 group by 1 order by 2 desc;

commit;
