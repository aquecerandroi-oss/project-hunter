-- =====================================================================================
-- T3.45 — pré-checagem da candidata "varredura de mínima e recuperação" (sweep + reclaim)
-- EXP-0017 · sweep_reclaim_v1 · SOMENTE LEITURA · VPS (hunter-postgres-1)
--
-- MÉTODO: o da T3.33d. A consulta roda ANTES de qualquer linha de módulo, e as regras de
-- morte abaixo foram escritas ANTES de a consulta rodar. Se uma delas disparar, o módulo
-- NÃO é escrito e o EXP-0017 é arquivado `bloqueado-por-precheck`.
--
-- REGRAS DE MORTE (congeladas em 2026-09-08, antes da execução)
--   P1  < 20 eventos sob a regra congelada INTEIRA (pivô + varredura + recuperação + RVOL
--       + piso de risco + teto de risco), em 31 dias × 4 mercados  -> NÃO escrever o módulo.
--       Não é "amostra pequena": é ausência de população, e mais 30 dias não a criam (K1).
--   P2  > 1 500 eventos -> a regra não é condição, é relógio: não escrever COMO ESPECIFICADA
--       (re-especificar é versão nova, não ajuste) (K2).
--   P3  >= 60 % dos eventos num único mercado -> não mata; o módulo pode ser escrito, mas o
--       dia um é obrigado a reportar por mercado, e K6 vale sobre o replay.
--   P4  cobertura de barras de 15 min completas < 90 % da janela -> BUG DE DADO a reportar,
--       não resultado de estratégia (o análogo do `mark_price` nulo da T3.33d).
--
-- PARÂMETROS DA REGRA, EXATAMENTE COMO O EXP-0017 OS CONGELA
--   janela            2026-08-08T00:00Z <= open_time < 2026-09-08T00:00Z (31 dias)
--   mercados          ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (perpetual)
--   barra de decisão  15 min, formada por EXATAMENTE 15 velas de 1 min `is_final`
--   escala            ATR de Wilder(14) sobre 97 barras de 15 min (`rolling_window_v1`),
--                     UMA leitura por barra de decisão, e é ela que escala tudo
--   pivô              k = 3 (low < as 3 lows à esquerda, <= as 3 à direita),
--                     proeminência >= 1 ATR, confirmado em `rn + 3`
--   lookback do pivô  40 barras
--   varredura         low <= pivo_low - 0,25 × ATR
--   recuperação       close > pivo_low
--   RVOL              volume / mediana dos 20 volumes anteriores >= 1,5
--   stop              low_da_barra - 0,10 × ATR
--   piso de custo     risco% = (close - stop)/close >= 0,006  (teto de pedágio 0,3333 R)
--   teto de risco     risco_atr = (close - stop)/ATR <= 3
--
-- O QUE ESTA CONSULTA **NÃO** É
--   * não é o motor: `aggregate()` recusa a janela inteira quando falta UM minuto; aqui a
--     contiguidade é exigida sobre as 97 barras de 15 min completas — é um LIMITE SUPERIOR
--     da população, nunca um limite inferior;
--   * o ATR é calculado em `float8` pela forma fechada equivalente à recursão de Wilder
--     (semente = média dos 14 primeiros TRs da janela de 97, mais 82 passos de suavização);
--     o motor usa `Decimal` com 28 dígitos. Diferença esperada muito abaixo do último dígito
--     reportado; declarada mesmo assim;
--   * `markets.is_monitored` é o de hoje, não o da janela (limitação declarada, PIPELINE §6c).
-- =====================================================================================

\pset border 2
\pset numericlocale off
\timing on

begin transaction isolation level repeatable read read only;

select now() as read_at, current_database() as db;

-- -------------------------------------------------------------------------------------
-- Q1 — cobertura de barras de 15 min e distribuição de ATR% (Wilder 14, janela rolante 97).
--      Q1 fecha o CONCERN 2 da notes-T3.33d, aberto desde 2026-09-08: nunca medimos o ATR de
--      Wilder, só `(high-low)/close`.
-- -------------------------------------------------------------------------------------
with bars as (
  select c.market_id, m.symbol,
         date_bin(interval '15 minutes', c.open_time, timestamptz '2026-01-01 00:00:00+00') as bar_open,
         count(*)                                          as minutes,
         max(c.high)                                       as h,
         min(c.low)                                        as l,
         (array_agg(c.close order by c.open_time desc))[1] as cl,
         sum(c.volume)                                     as v
    from candles c
    join markets m on m.id = c.market_id
   where m.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT')
     and m.market_type = 'perpetual'
     and c.timeframe = '1m'
     and c.is_final
     and c.open_time >= timestamptz '2026-08-08 00:00:00+00'
     and c.open_time <  timestamptz '2026-09-08 00:00:00+00'
   group by 1,2,3
),
full_bars as (select * from bars where minutes = 15),
seq as (
  select f.*,
         row_number()    over w as rn,
         lag(f.cl)       over w as prev_close,
         lag(f.bar_open) over w as prev_open
    from full_bars f
  window w as (partition by f.market_id order by f.bar_open)
),
tr as (
  select s.*,
         case when s.prev_close is null then null
              else greatest(s.h - s.l, abs(s.h - s.prev_close), abs(s.l - s.prev_close)) end as tr,
         case when s.prev_open = s.bar_open - interval '15 minutes' then 1 else 0 end        as contig
    from seq s
),
win as (
  select t.*,
         array_agg(t.tr::float8) over w1 as trs,
         min(t.contig)           over w1 as contiguous_97
    from tr t
  window w1 as (partition by t.market_id order by t.bar_open rows between 95 preceding and current row)
),
atr as (
  select w.market_id, w.symbol, w.bar_open, w.rn, w.h, w.l, w.cl, w.v, w.contiguous_97,
         case when w.rn >= 97 and cardinality(w.trs) = 96 and w.contiguous_97 = 1 then
              (select avg(u.x) from unnest(w.trs) with ordinality u(x, o) where o <= 14)
                * power(13.0::float8/14.0, 82)
              + coalesce((select sum(u.x * power(13.0::float8/14.0, 96 - o) / 14.0)
                            from unnest(w.trs) with ordinality u(x, o) where o >= 15), 0)
         end as atr
    from win w
)
select a.symbol,
       count(*)                                                        as barras_15m,
       round(100.0 * count(*) / 2976.0, 2)                             as pct_da_janela,
       count(*) filter (where a.atr is not null)                       as com_atr,
       round((percentile_cont(0.10) within group (order by a.atr / a.cl::float8))::numeric, 6) as atr_pct_p10,
       round((percentile_cont(0.50) within group (order by a.atr / a.cl::float8))::numeric, 6) as atr_pct_p50,
       round((percentile_cont(0.90) within group (order by a.atr / a.cl::float8))::numeric, 6) as atr_pct_p90,
       round((max(a.atr / a.cl::float8))::numeric, 6)                                          as atr_pct_max,
       round(100.0 * count(*) filter (where a.atr / a.cl::float8 >= 0.006)
             / nullif(count(*) filter (where a.atr is not null), 0), 2) as pct_atr_ge_0006,
       round(100.0 * count(*) filter (where a.atr / a.cl::float8 >= 0.003)
             / nullif(count(*) filter (where a.atr is not null), 0), 2) as pct_atr_ge_0003
  from atr a
 group by 1
 order by 1;

-- -------------------------------------------------------------------------------------
-- Q2 — o funil da regra congelada, porta a porta, por mercado. P1/P2/P3 leem esta tabela.
-- -------------------------------------------------------------------------------------
with bars as (
  select c.market_id, m.symbol,
         date_bin(interval '15 minutes', c.open_time, timestamptz '2026-01-01 00:00:00+00') as bar_open,
         count(*) as minutes, max(c.high) as h, min(c.low) as l,
         (array_agg(c.close order by c.open_time desc))[1] as cl, sum(c.volume) as v
    from candles c join markets m on m.id = c.market_id
   where m.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT')
     and m.market_type = 'perpetual' and c.timeframe = '1m' and c.is_final
     and c.open_time >= timestamptz '2026-08-08 00:00:00+00'
     and c.open_time <  timestamptz '2026-09-08 00:00:00+00'
   group by 1,2,3
),
full_bars as (select * from bars where minutes = 15),
seq as (
  select f.*, row_number() over w as rn, lag(f.cl) over w as prev_close,
         lag(f.bar_open) over w as prev_open
    from full_bars f window w as (partition by f.market_id order by f.bar_open)
),
tr as (
  select s.*,
         case when s.prev_close is null then null
              else greatest(s.h - s.l, abs(s.h - s.prev_close), abs(s.l - s.prev_close)) end as tr,
         case when s.prev_open = s.bar_open - interval '15 minutes' then 1 else 0 end        as contig
    from seq s
),
win as (
  select t.*,
         array_agg(t.tr::float8) over w1 as trs,
         min(t.contig)           over w1 as contiguous_97,
         array_agg(t.v::float8)  over w2 as vols
    from tr t
  window w1 as (partition by t.market_id order by t.bar_open rows between 95 preceding and current row),
         w2 as (partition by t.market_id order by t.bar_open rows between 20 preceding and 1 preceding)
),
atr as (
  select w.market_id, w.symbol, w.bar_open, w.rn, w.h, w.l, w.cl, w.v, w.contiguous_97, w.vols,
         case when w.rn >= 97 and cardinality(w.trs) = 96 and w.contiguous_97 = 1 then
              (select avg(u.x) from unnest(w.trs) with ordinality u(x, o) where o <= 14)
                * power(13.0::float8/14.0, 82)
              + coalesce((select sum(u.x * power(13.0::float8/14.0, 96 - o) / 14.0)
                            from unnest(w.trs) with ordinality u(x, o) where o >= 15), 0)
         end as atr
    from win w
),
neigh as (
  select a.*,
         min(a.l) over (partition by a.market_id order by a.bar_open rows between 3 preceding and 1 preceding) as l_left,
         min(a.l) over (partition by a.market_id order by a.bar_open rows between 1 following and 3 following) as l_right,
         max(a.h) over (partition by a.market_id order by a.bar_open rows between 3 preceding and 1 preceding) as h_left,
         max(a.h) over (partition by a.market_id order by a.bar_open rows between 1 following and 3 following) as h_right,
         count(*) over (partition by a.market_id order by a.bar_open rows between 3 preceding and 3 following) as neigh_n
    from atr a
),
marked as (
  select n.*,
         case when n.atr is not null and n.neigh_n = 7
                   and n.l < n.l_left and n.l <= n.l_right
                   and (least(n.h_left, n.h_right) - n.l)::float8 / n.atr >= 1.0
              then n.rn end as pivot_rn_self,
         case when n.atr is not null and n.neigh_n = 7
                   and n.l < n.l_left and n.l <= n.l_right
                   and (least(n.h_left, n.h_right) - n.l)::float8 / n.atr >= 1.0
              then n.l end  as pivot_low_self
    from neigh n
),
withpiv as (
  select m.*,
         max(m.pivot_rn_self) over (partition by m.market_id order by m.bar_open
                                    rows between 40 preceding and 3 preceding) as piv_rn,
         (select percentile_cont(0.5) within group (order by u.x)
            from unnest(m.vols) u(x)) as vol_median
    from marked m
),
ev as (
  select w.market_id, w.symbol, w.bar_open, w.rn, w.cl, w.l, w.v, w.atr,
         w.atr / w.cl::float8                                            as atr_pct,
         p.pivot_low_self                                                as piv_low,
         case when w.vol_median > 0 then w.v::float8 / w.vol_median end  as rvol,
         (w.l::float8 - 0.10 * w.atr)                                    as stop_price
    from withpiv w
    left join marked p on p.market_id = w.market_id and p.rn = w.piv_rn
   where w.atr is not null and w.contiguous_97 = 1
),
gated as (
  select e.*,
         (e.cl::float8 - e.stop_price) / e.cl::float8 as risk_pct,
         (e.cl::float8 - e.stop_price) / e.atr        as risk_atr,
         (e.piv_low is not null)                      as g1_pivo,
         (e.piv_low is not null and e.l::float8 <= e.piv_low::float8 - 0.25 * e.atr) as g2_varredura,
         (e.piv_low is not null and e.l::float8 <= e.piv_low::float8 - 0.25 * e.atr
            and e.cl > e.piv_low)                     as g3_recuperacao,
         (e.rvol >= 1.5)                              as g4_rvol
    from ev e
),
-- A barreira de re-arme do Shadow Lab: um acompanhamento por slot. Com horizonte de 4 h
-- (16 barras de 15 min), um evento que cai dentro das 16 barras do anterior NÃO vira decisão.
-- `gap is null or gap >= 16` é um LIMITE INFERIOR do que a máquina de estados deixaria passar
-- (a gulosa real re-ancora no evento aceito; esta conta ancora no anterior, aceito ou não).
eventos_seq as (
  select g.*, g.rn - lag(g.rn) over (partition by g.market_id order by g.rn) as gap
    from gated g
   where g.g3_recuperacao and g.g4_rvol and g.risk_pct >= 0.006
     and g.risk_atr <= 3.0 and g.stop_price > 0
)
select symbol,
       count(*)                                                                 as barras_avaliaveis,
       count(*) filter (where g1_pivo)                                          as com_pivo,
       count(*) filter (where g2_varredura)                                     as varreram,
       count(*) filter (where g3_recuperacao)                                   as recuperaram,
       count(*) filter (where g3_recuperacao and g4_rvol)                       as mais_rvol,
       count(*) filter (where g3_recuperacao and g4_rvol and risk_pct >= 0.006) as mais_piso_risco,
       count(*) filter (where g3_recuperacao and g4_rvol and risk_pct >= 0.006
                          and risk_atr <= 3.0 and stop_price > 0)               as eventos,
       count(distinct bar_open::date) filter (where g3_recuperacao and g4_rvol
                          and risk_pct >= 0.006 and risk_atr <= 3.0)            as dias_com_evento,
       (select count(*) from eventos_seq s
         where s.symbol = gated.symbol and (s.gap is null or s.gap >= 16))      as pos_barreira_lb
  from gated
 group by 1
union all
select 'ZTOTAL',
       count(*),
       count(*) filter (where g1_pivo),
       count(*) filter (where g2_varredura),
       count(*) filter (where g3_recuperacao),
       count(*) filter (where g3_recuperacao and g4_rvol),
       count(*) filter (where g3_recuperacao and g4_rvol and risk_pct >= 0.006),
       count(*) filter (where g3_recuperacao and g4_rvol and risk_pct >= 0.006
                          and risk_atr <= 3.0 and stop_price > 0),
       count(distinct bar_open::date) filter (where g3_recuperacao and g4_rvol
                          and risk_pct >= 0.006 and risk_atr <= 3.0),
       (select count(*) from eventos_seq s where s.gap is null or s.gap >= 16)
  from gated
 order by 1;

-- -------------------------------------------------------------------------------------
-- Q3 — onde cai a porta de custo: distribuição de risco% e risco_atr nos três estágios do
--      funil. É o número que diz se `risk_pct_min` é uma porta ou uma parede.
-- -------------------------------------------------------------------------------------
with bars as (
  select c.market_id, m.symbol,
         date_bin(interval '15 minutes', c.open_time, timestamptz '2026-01-01 00:00:00+00') as bar_open,
         count(*) as minutes, max(c.high) as h, min(c.low) as l,
         (array_agg(c.close order by c.open_time desc))[1] as cl, sum(c.volume) as v
    from candles c join markets m on m.id = c.market_id
   where m.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT')
     and m.market_type = 'perpetual' and c.timeframe = '1m' and c.is_final
     and c.open_time >= timestamptz '2026-08-08 00:00:00+00'
     and c.open_time <  timestamptz '2026-09-08 00:00:00+00'
   group by 1,2,3
),
full_bars as (select * from bars where minutes = 15),
seq as (
  select f.*, row_number() over w as rn, lag(f.cl) over w as prev_close,
         lag(f.bar_open) over w as prev_open
    from full_bars f window w as (partition by f.market_id order by f.bar_open)
),
tr as (
  select s.*,
         case when s.prev_close is null then null
              else greatest(s.h - s.l, abs(s.h - s.prev_close), abs(s.l - s.prev_close)) end as tr,
         case when s.prev_open = s.bar_open - interval '15 minutes' then 1 else 0 end        as contig
    from seq s
),
win as (
  select t.*,
         array_agg(t.tr::float8) over w1 as trs,
         min(t.contig)           over w1 as contiguous_97,
         array_agg(t.v::float8)  over w2 as vols
    from tr t
  window w1 as (partition by t.market_id order by t.bar_open rows between 95 preceding and current row),
         w2 as (partition by t.market_id order by t.bar_open rows between 20 preceding and 1 preceding)
),
atr as (
  select w.market_id, w.symbol, w.bar_open, w.rn, w.h, w.l, w.cl, w.v, w.contiguous_97, w.vols,
         case when w.rn >= 97 and cardinality(w.trs) = 96 and w.contiguous_97 = 1 then
              (select avg(u.x) from unnest(w.trs) with ordinality u(x, o) where o <= 14)
                * power(13.0::float8/14.0, 82)
              + coalesce((select sum(u.x * power(13.0::float8/14.0, 96 - o) / 14.0)
                            from unnest(w.trs) with ordinality u(x, o) where o >= 15), 0)
         end as atr
    from win w
),
neigh as (
  select a.*,
         min(a.l) over (partition by a.market_id order by a.bar_open rows between 3 preceding and 1 preceding) as l_left,
         min(a.l) over (partition by a.market_id order by a.bar_open rows between 1 following and 3 following) as l_right,
         max(a.h) over (partition by a.market_id order by a.bar_open rows between 3 preceding and 1 preceding) as h_left,
         max(a.h) over (partition by a.market_id order by a.bar_open rows between 1 following and 3 following) as h_right,
         count(*) over (partition by a.market_id order by a.bar_open rows between 3 preceding and 3 following) as neigh_n
    from atr a
),
marked as (
  select n.*,
         case when n.atr is not null and n.neigh_n = 7
                   and n.l < n.l_left and n.l <= n.l_right
                   and (least(n.h_left, n.h_right) - n.l)::float8 / n.atr >= 1.0
              then n.rn end as pivot_rn_self,
         case when n.atr is not null and n.neigh_n = 7
                   and n.l < n.l_left and n.l <= n.l_right
                   and (least(n.h_left, n.h_right) - n.l)::float8 / n.atr >= 1.0
              then n.l end  as pivot_low_self
    from neigh n
),
withpiv as (
  select m.*,
         max(m.pivot_rn_self) over (partition by m.market_id order by m.bar_open
                                    rows between 40 preceding and 3 preceding) as piv_rn,
         (select percentile_cont(0.5) within group (order by u.x)
            from unnest(m.vols) u(x)) as vol_median
    from marked m
),
ev as (
  select w.market_id, w.symbol, w.bar_open, w.rn, w.cl, w.l, w.v, w.atr,
         w.atr / w.cl::float8                                            as atr_pct,
         p.pivot_low_self                                                as piv_low,
         case when w.vol_median > 0 then w.v::float8 / w.vol_median end  as rvol,
         (w.l::float8 - 0.10 * w.atr)                                    as stop_price
    from withpiv w
    left join marked p on p.market_id = w.market_id and p.rn = w.piv_rn
   where w.atr is not null and w.contiguous_97 = 1
),
gated as (
  select e.*,
         (e.cl::float8 - e.stop_price) / e.cl::float8 as risk_pct,
         (e.cl::float8 - e.stop_price) / e.atr        as risk_atr,
         (e.piv_low is not null and e.l::float8 <= e.piv_low::float8 - 0.25 * e.atr) as g2_varredura,
         (e.piv_low is not null and e.l::float8 <= e.piv_low::float8 - 0.25 * e.atr
            and e.cl > e.piv_low)                     as g3_recuperacao,
         (e.rvol >= 1.5)                              as g4_rvol
    from ev e
),
estagios as (
  select 'A varreu'                       as estagio, g.* from gated g where g.g2_varredura
  union all
  select 'B varreu+recuperou'             as estagio, g.* from gated g where g.g3_recuperacao
  union all
  select 'C varreu+recuperou+rvol'        as estagio, g.* from gated g where g.g3_recuperacao and g.g4_rvol
  union all
  select 'D controle: varreu, NAO recuperou' as estagio, g.* from gated g
   where g.g2_varredura and not g.g3_recuperacao and g.g4_rvol
)
select estagio,
       count(*)                                                                          as n,
       round((percentile_cont(0.10) within group (order by risk_pct))::numeric, 5)        as risco_pct_p10,
       round((percentile_cont(0.50) within group (order by risk_pct))::numeric, 5)        as risco_pct_p50,
       round((percentile_cont(0.90) within group (order by risk_pct))::numeric, 5)        as risco_pct_p90,
       round((percentile_cont(0.10) within group (order by risk_atr))::numeric, 3)        as risco_atr_p10,
       round((percentile_cont(0.50) within group (order by risk_atr))::numeric, 3)        as risco_atr_p50,
       round((percentile_cont(0.90) within group (order by risk_atr))::numeric, 3)        as risco_atr_p90,
       round(100.0 * count(*) filter (where risk_pct >= 0.006) / count(*), 1)             as pct_no_piso,
       round((0.0020 / percentile_cont(0.50) within group (order by risk_pct))::numeric, 4) as pedagio_mediano_r
  from estagios
 group by 1
 order by 1;

-- -------------------------------------------------------------------------------------
-- Q4 — sensibilidade DIAGNÓSTICA das três convenções (`sweep_atr`, `rvol_min`,
--      `risk_pct_min`). O contrato já está congelado: isto NÃO escolhe parâmetro, mede
--      quanto cada porta custa, para que uma eventual v2 seja um experimento novo com
--      número em vez de palpite.
-- -------------------------------------------------------------------------------------
with bars as (
  select c.market_id, m.symbol,
         date_bin(interval '15 minutes', c.open_time, timestamptz '2026-01-01 00:00:00+00') as bar_open,
         count(*) as minutes, max(c.high) as h, min(c.low) as l,
         (array_agg(c.close order by c.open_time desc))[1] as cl, sum(c.volume) as v
    from candles c join markets m on m.id = c.market_id
   where m.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT','DOGEUSDT')
     and m.market_type = 'perpetual' and c.timeframe = '1m' and c.is_final
     and c.open_time >= timestamptz '2026-08-08 00:00:00+00'
     and c.open_time <  timestamptz '2026-09-08 00:00:00+00'
   group by 1,2,3
),
full_bars as (select * from bars where minutes = 15),
seq as (
  select f.*, row_number() over w as rn, lag(f.cl) over w as prev_close,
         lag(f.bar_open) over w as prev_open
    from full_bars f window w as (partition by f.market_id order by f.bar_open)
),
tr as (
  select s.*,
         case when s.prev_close is null then null
              else greatest(s.h - s.l, abs(s.h - s.prev_close), abs(s.l - s.prev_close)) end as tr,
         case when s.prev_open = s.bar_open - interval '15 minutes' then 1 else 0 end        as contig
    from seq s
),
win as (
  select t.*,
         array_agg(t.tr::float8) over w1 as trs,
         min(t.contig)           over w1 as contiguous_97,
         array_agg(t.v::float8)  over w2 as vols
    from tr t
  window w1 as (partition by t.market_id order by t.bar_open rows between 95 preceding and current row),
         w2 as (partition by t.market_id order by t.bar_open rows between 20 preceding and 1 preceding)
),
atr as (
  select w.market_id, w.symbol, w.bar_open, w.rn, w.h, w.l, w.cl, w.v, w.contiguous_97, w.vols,
         case when w.rn >= 97 and cardinality(w.trs) = 96 and w.contiguous_97 = 1 then
              (select avg(u.x) from unnest(w.trs) with ordinality u(x, o) where o <= 14)
                * power(13.0::float8/14.0, 82)
              + coalesce((select sum(u.x * power(13.0::float8/14.0, 96 - o) / 14.0)
                            from unnest(w.trs) with ordinality u(x, o) where o >= 15), 0)
         end as atr
    from win w
),
neigh as (
  select a.*,
         min(a.l) over (partition by a.market_id order by a.bar_open rows between 3 preceding and 1 preceding) as l_left,
         min(a.l) over (partition by a.market_id order by a.bar_open rows between 1 following and 3 following) as l_right,
         max(a.h) over (partition by a.market_id order by a.bar_open rows between 3 preceding and 1 preceding) as h_left,
         max(a.h) over (partition by a.market_id order by a.bar_open rows between 1 following and 3 following) as h_right,
         count(*) over (partition by a.market_id order by a.bar_open rows between 3 preceding and 3 following) as neigh_n
    from atr a
),
marked as (
  select n.*,
         case when n.atr is not null and n.neigh_n = 7
                   and n.l < n.l_left and n.l <= n.l_right
                   and (least(n.h_left, n.h_right) - n.l)::float8 / n.atr >= 1.0
              then n.rn end as pivot_rn_self,
         case when n.atr is not null and n.neigh_n = 7
                   and n.l < n.l_left and n.l <= n.l_right
                   and (least(n.h_left, n.h_right) - n.l)::float8 / n.atr >= 1.0
              then n.l end  as pivot_low_self
    from neigh n
),
withpiv as (
  select m.*,
         max(m.pivot_rn_self) over (partition by m.market_id order by m.bar_open
                                    rows between 40 preceding and 3 preceding) as piv_rn,
         (select percentile_cont(0.5) within group (order by u.x)
            from unnest(m.vols) u(x)) as vol_median
    from marked m
),
ev as (
  select w.market_id, w.symbol, w.bar_open, w.rn, w.cl, w.l, w.v, w.atr,
         p.pivot_low_self                                                as piv_low,
         case when w.vol_median > 0 then w.v::float8 / w.vol_median end  as rvol,
         (w.l::float8 - 0.10 * w.atr)                                    as stop_price
    from withpiv w
    left join marked p on p.market_id = w.market_id and p.rn = w.piv_rn
   where w.atr is not null and w.contiguous_97 = 1
),
variantes(nome, sweep_atr, rvol_min, risk_min) as (
  values ('0 CONGELADA 0,25 / 1,5 / 0,006', 0.25::float8, 1.5::float8, 0.006::float8),
         ('1 sweep_atr 0,10',               0.10, 1.5, 0.006),
         ('2 sweep_atr 0,50',               0.50, 1.5, 0.006),
         ('3 sem RVOL',                     0.25, 0.0, 0.006),
         ('4 risk_pct_min 0,004',           0.25, 1.5, 0.004),
         ('5 risk_pct_min 0,003',           0.25, 1.5, 0.003),
         ('6 sem piso de custo',            0.25, 1.5, 0.0)
)
select v.nome,
       count(*)                                as eventos,
       count(distinct e.bar_open::date)        as dias_distintos,
       count(distinct e.symbol)                as mercados,
       round(100.0 * max(cnt.por_mercado) / count(*), 1) as pct_do_maior_mercado
  from variantes v
  join ev e
    on e.piv_low is not null
   and e.l::float8 <= e.piv_low::float8 - v.sweep_atr * e.atr
   and e.cl > e.piv_low
   and coalesce(e.rvol, 0) >= v.rvol_min
   and (e.cl::float8 - e.stop_price) / e.cl::float8 >= v.risk_min
   and (e.cl::float8 - e.stop_price) / e.atr <= 3.0
   and e.stop_price > 0
  join lateral (
    select count(*) as por_mercado
      from ev e2
     where e2.symbol = e.symbol
       and e2.piv_low is not null
       and e2.l::float8 <= e2.piv_low::float8 - v.sweep_atr * e2.atr
       and e2.cl > e2.piv_low
       and coalesce(e2.rvol, 0) >= v.rvol_min
       and (e2.cl::float8 - e2.stop_price) / e2.cl::float8 >= v.risk_min
       and (e2.cl::float8 - e2.stop_price) / e2.atr <= 3.0
       and e2.stop_price > 0
  ) cnt on true
 group by v.nome
 order by v.nome;

commit;
