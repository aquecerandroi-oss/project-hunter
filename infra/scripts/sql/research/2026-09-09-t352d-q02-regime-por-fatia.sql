-- T3.52d q02 — rótulo horário do BTC por metade da janela de replay. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

select case when start_time < timestamptz '2026-08-23 00:00:00+00' then 'A 08-08..08-23'
            else 'B 08-23..09-08' end as fatia,
       regime::text as rotulo, count(*) as horas
  from market_regimes
 where scope = 'btc' and classifier_version = 'regime_hourly_v1'
   and start_time >= timestamptz '2026-08-08 00:00:00+00'
   and start_time <  timestamptz '2026-09-08 00:00:00+00'
 group by 1,2 order by 1, 3 desc;

commit;
