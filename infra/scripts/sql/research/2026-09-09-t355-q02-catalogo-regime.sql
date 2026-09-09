-- T3.55b q02 — catalogo: existe regime horario (market_regimes, PIPELINE 4b) cobrindo
-- os 31 d da janela? Se nao cobrir, o recorte "por regime do BTC" desta task e derivado
-- das proprias velas de 1 h do BTC, e isso fica declarado na nota. SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '120s';
\pset border 2
\pset numericlocale off
select now() as read_at;

select count(*) as linhas,
       min(start_time) as primeiro,
       max(start_time) as ultimo,
       count(distinct date_trunc('day', start_time)) as dias
  from market_regimes;

select regime::text, count(*) as n
  from market_regimes
 group by 1 order by 2 desc;
commit;
