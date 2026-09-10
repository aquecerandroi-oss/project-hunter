-- T3.65b q03 -- LACUNA DE COLETA x MUDANCA REAL: quando cada linha de
-- `funding_rates` foi GRAVADA, comparada com o instante do assentamento.
-- Os tres motivos que sobraram no codigo atual (pos-T3.65) sao de 09/09:
-- `funding_schedule_unknown` x5 em PROMUSDT e `funding_missing:2026-09-09T00:00`
-- em TAOUSDT. Se as linhas daquele periodo so entraram no banco DEPOIS do
-- desfecho ter sido liquidado, o motivo e ATRASO DE COLETA, nao cadencia.
-- SOMENTE LEITURA.
begin transaction isolation level repeatable read read only;
set local statement_timeout = '240s';
\pset border 2
\pset numericlocale off
select now() as read_at;

-- 1. a linha do `funding_missing` do TAO existe hoje? quando entrou?
select m.symbol, f.funding_time, f.xmin::text as xmin, f.rate, f.mark_price
  from funding_rates f
  join markets m on m.id = f.market_id
 where m.symbol in ('TAOUSDT','PROMUSDT')
   and f.funding_time >= timestamptz '2026-09-08 20:00+00'
   and f.funding_time <= timestamptz '2026-09-09 12:00+00'
 order by m.symbol, f.funding_time;

-- 2. atraso de gravacao por mercado e por dia (mediana), nos tres mercados
select m.symbol,
       f.xmin::text       as xmin,
       count(*)           as linhas,
       min(f.funding_time) as primeiro_assentamento,
       max(f.funding_time) as ultimo_assentamento
  from funding_rates f
  join markets m on m.id = f.market_id
 where m.symbol in ('PROMUSDT','SAHARAUSDT','TAOUSDT')
   and f.funding_time >= timestamptz '2026-06-12 00:00+00'
 group by 1, 2
 order by 1, 3;

commit;
-- NOTA (T3.65b): `funding_rates` tem 4 colunas e nenhuma de gravacao, e
-- `track_commit_timestamp` esta OFF na VPS -- a HORA de chegada de uma linha nao
-- e recuperavel do banco. `xmin` da a TRANSACAO que inseriu: ordem e agrupamento,
-- nunca relogio. Linhas de backfill compartilham poucas transacoes grandes.
