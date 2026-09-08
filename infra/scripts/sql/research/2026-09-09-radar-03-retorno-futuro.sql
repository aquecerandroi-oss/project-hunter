-- T3.46 Q3 — a anomalia carrega informacao SOZINHA? Retorno futuro do mercado
-- depois de cada anomalia contra uma linha de base pareada, sem estrategia
-- nenhuma no meio.
--
-- SOMENTE LEITURA (repeatable read read only). Executavel sozinho; o bloco de
-- eventos e repetido de proposito.
--
-- DESENHO
--   evento     = (mercado, minuto de `anomalies.detected_at`), so anomalias cujo
--                horizonte inteiro cabe nas velas que existem.
--   retorno    = close(t+H)/close(t) - 1, H em {60, 240, 1440} minutos, sobre
--                velas 1m `is_final` (PIPELINE §2: nada de vela em formacao).
--   base       = TODO minuto do MESMO mercado, dentro da mesma janela do Radar,
--                sem nenhuma anomalia detectada nos 60 minutos anteriores nem no
--                proprio minuto, e com o mesmo horizonte disponivel.
--
-- PAREAMENTO — DESVIO DECLARADO DO BRIEF. O brief pede "barras aleatorias sem
-- anomalia, mesma contagem". Uso **todas** as barras elegiveis do mesmo mercado e
-- pondero a media agregada pela contagem de eventos daquele mercado: e o limite
-- da amostra aleatoria pareada quando a contagem cresce, tem a mesma esperanca,
-- tem variancia menor e nao depende de semente. O pareamento que importa (mesmo
-- mercado, mesma janela) esta preservado; o que NAO esta pareado e a hora do dia
-- — com 2 dias de Radar nao ha celula suficiente por hora, e forcar isso trocaria
-- vies por ruido.
--
-- ANTI-ANTECIPACAO. O evento e datado por `detected_at`, que e imutavel, e o
-- retorno comeca no fechamento do minuto do evento — nunca antes. `severity` nao
-- entra em lugar nenhum (e mutavel; ver o cabecalho da consulta 02).
\pset border 2
\pset numericlocale off

begin transaction isolation level repeatable read read only;

\echo '== 0. corte da leitura =='
select now() as read_at,
       (select max(open_time) from candles where timeframe = '1m' and is_final) as ultima_vela;

\echo ''
\echo '== 1. retorno futuro depois da anomalia x base pareada (pooled, ponderado por mercado) =='
-- Um mercado so entra no peso de um horizonte se tiver evento COM aquele
-- horizonte disponivel (senao a media do numerador e a soma do denominador
-- falariam de populacoes diferentes).
with horizontes(h, mins) as (values ('1h', 60), ('4h', 240), ('24h', 1440)),
ev_long as (
  select a.market_id, h.h, (cf.close / c0.close - 1) as ret
    from anomalies a
    cross join horizontes h
    join candles c0 on c0.market_id = a.market_id and c0.timeframe = '1m'
                   and c0.is_final and c0.open_time = date_trunc('minute', a.detected_at)
    join candles cf on cf.market_id = a.market_id and cf.timeframe = '1m'
                   and cf.is_final
                   and cf.open_time = date_trunc('minute', a.detected_at) + (h.mins || ' minutes')::interval
), base_long as (
  select c.market_id, h.h, (cf.close / c.close - 1) as ret
    from candles c
    join (select distinct market_id from anomalies) mk on mk.market_id = c.market_id
    cross join horizontes h
    join candles cf on cf.market_id = c.market_id and cf.timeframe = '1m'
                   and cf.is_final
                   and cf.open_time = c.open_time + (h.mins || ' minutes')::interval
   where c.timeframe = '1m' and c.is_final
     and c.open_time >= (select date_trunc('minute', min(detected_at)) from anomalies)
     and c.open_time <= (select date_trunc('minute', max(detected_at)) from anomalies)
     and not exists (select 1 from anomalies an
                      where an.market_id = c.market_id
                        and an.detected_at <= c.open_time + interval '1 minute'
                        and an.detected_at >  c.open_time - interval '60 minutes')
), ev_m as (
  select market_id, h, count(*) n_ev, avg(ret) r, avg(abs(ret)) a from ev_long group by 1, 2
), base_m as (
  select market_id, h, count(*) n_base, avg(ret) r, avg(abs(ret)) a from base_long group by 1, 2
)
select 'H = ' || e.h as horizonte,
       sum(e.n_ev) as eventos,
       sum(b.n_base) as barras_base,
       count(*) as mercados,
       round(100 * sum(e.n_ev * e.r) / sum(e.n_ev), 4) as ret_anomalia_pct,
       round(100 * sum(e.n_ev * b.r) / sum(e.n_ev), 4) as ret_base_pct,
       round(100 * sum(e.n_ev * e.a) / sum(e.n_ev), 4) as mov_abs_anomalia_pct,
       round(100 * sum(e.n_ev * b.a) / sum(e.n_ev), 4) as mov_abs_base_pct
  from ev_m e join base_m b on b.market_id = e.market_id and b.h = e.h
 group by e.h
 order by case e.h when '1h' then 1 when '4h' then 2 else 3 end;

\echo ''
\echo '== 2. o mesmo por TIPO de anomalia (movimento absoluto, 1h e 4h) =='
with ev as (
  select a.id, a.market_id, a.type::text as tipo,
         date_trunc('minute', a.detected_at) as t0
    from anomalies a
), ev_px as (
  select ev.*, c0.close as px0, c1.close as px60, c4.close as px240
    from ev
    join candles c0 on c0.market_id = ev.market_id and c0.timeframe = '1m'
                   and c0.is_final and c0.open_time = ev.t0
    left join candles c1 on c1.market_id = ev.market_id and c1.timeframe = '1m'
                   and c1.is_final and c1.open_time = ev.t0 + interval '60 minutes'
    left join candles c4 on c4.market_id = ev.market_id and c4.timeframe = '1m'
                   and c4.is_final and c4.open_time = ev.t0 + interval '240 minutes'
)
select tipo,
       count(*) filter (where px60 is not null) as n_1h,
       round(100 * avg(px60 / px0 - 1) filter (where px60 is not null), 4) as ret_1h_pct,
       round(100 * avg(abs(px60 / px0 - 1)) filter (where px60 is not null), 4) as mov_abs_1h_pct,
       count(*) filter (where px240 is not null) as n_4h,
       round(100 * avg(px240 / px0 - 1) filter (where px240 is not null), 4) as ret_4h_pct,
       round(100 * avg(abs(px240 / px0 - 1)) filter (where px240 is not null), 4) as mov_abs_4h_pct
  from ev_px group by 1 order by 2 desc;

\echo ''
\echo '== 3. a direcao declarada pelo detector acerta o sinal do retorno? =='
with ev as (
  select a.market_id, a.type::text as tipo,
         a.metadata->'state'->>'direction' as direcao,
         date_trunc('minute', a.detected_at) as t0
    from anomalies a
), ev_px as (
  select ev.*, c0.close as px0, c1.close as px60, c4.close as px240
    from ev
    join candles c0 on c0.market_id = ev.market_id and c0.timeframe = '1m'
                   and c0.is_final and c0.open_time = ev.t0
    left join candles c1 on c1.market_id = ev.market_id and c1.timeframe = '1m'
                   and c1.is_final and c1.open_time = ev.t0 + interval '60 minutes'
    left join candles c4 on c4.market_id = ev.market_id and c4.timeframe = '1m'
                   and c4.is_final and c4.open_time = ev.t0 + interval '240 minutes'
)
select direcao,
       count(*) filter (where px60 is not null) as n_1h,
       round(100.0 * count(*) filter (where px60 is not null
              and sign(px60 / px0 - 1) = case when direcao = 'up' then 1 when direcao = 'down' then -1 else 0 end)
             / nullif(count(*) filter (where px60 is not null), 0), 1) as acerto_sinal_1h_pct,
       round(100 * avg(px60 / px0 - 1) filter (where px60 is not null), 4) as ret_1h_pct,
       round(100 * avg(px240 / px0 - 1) filter (where px240 is not null), 4) as ret_4h_pct
  from ev_px group by 1 order by 2 desc;

\echo ''
\echo '== 4. quantos eventos perdem horizonte por falta de vela (honestidade da amostra) =='
with ev as (select a.id, a.market_id, date_trunc('minute', a.detected_at) as t0 from anomalies a)
select count(*) as anomalias,
       count(c0.close) as com_vela_no_minuto,
       count(c1.close) as com_1h,
       count(c4.close) as com_4h,
       count(c24.close) as com_24h
  from ev
  left join candles c0  on c0.market_id  = ev.market_id and c0.timeframe  = '1m'
                   and c0.is_final and c0.open_time  = ev.t0
  left join candles c1  on c1.market_id  = ev.market_id and c1.timeframe  = '1m'
                   and c1.is_final and c1.open_time  = ev.t0 + interval '60 minutes'
  left join candles c4  on c4.market_id  = ev.market_id and c4.timeframe  = '1m'
                   and c4.is_final and c4.open_time  = ev.t0 + interval '240 minutes'
  left join candles c24 on c24.market_id = ev.market_id and c24.timeframe = '1m'
                   and c24.is_final and c24.open_time = ev.t0 + interval '1440 minutes';

commit;
