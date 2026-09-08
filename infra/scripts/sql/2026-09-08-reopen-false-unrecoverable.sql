-- HOTFIX T3.7e (2026-09-08, revisão do commit 50932ec da T3.7d):
-- `check_gaps` lia `market_earliest` uma vez por ciclo; quando `interleave`
-- concedia a um mercado mais de um slot do estrato histórico no mesmo ciclo,
-- um pedaço mais novo recuperado com sucesso empurrava o mínimo verdadeiro
-- para antes do que aquele valor dizia, e um pedaço mais antigo do MESMO
-- mercado, processado depois no mesmo ciclo, era comparado contra o valor já
-- obsoleto e virava `unrecoverable` (motivo `before_listing`) por engano.
-- BTCUSDT e UNIUSDT perderam janelas legítimas de agosto assim na VPS
-- (`.claude/state/notes-T3.7e.md`).
--
-- Prova estrutural, sem depender do `reason` do `system_events` (a tabela
-- `ingestion_gaps` não guarda motivo): se o mercado já tem qualquer vela
-- final ANTERIOR ao `gap_start` da própria lacuna, essa lacuna não pode ser
-- "antes da listagem" -- o mercado comprovadamente já existia antes dela.
-- Reabre para `open`; o recovery normal (com `earliest_known` correto do
-- ciclo seguinte) decide de novo a partir daí, sem pular a chamada REST.
--
-- T3.7f (re-revisão, MEDIUM): a prova acima, sozinha, também reabriria
-- qualquer outra lacuna `unrecoverable` de QUALQUER mercado/motivo que por
-- coincidência tenha uma vela mais antiga que seu `gap_start` -- por exemplo
-- uma lacuna `exhausted` (T3.7d item 3: MAX_REOPEN_PER_CYCLE excedido, nada a
-- ver com `before_listing`) de um mercado sem relação com o incidente.
-- `ingestion_gaps` não guarda `reason`/motivo (só `system_events` guarda), e
-- não há coluna `updated_at` no modelo (`IngestionGap` usa só
-- `UUIDPrimaryKeyMixin`, sem o mixin de timestamp -- ver
-- `packages/core/hunter_core/db/models/market_data.py`), então o filtro de
-- escopo abaixo usa `detected_at` (quando a lacuna foi originalmente
-- detectada) e restringe explicitamente aos dois símbolos e à janela de
-- tempo do incidente real, em vez de reabrir cegamente todo `unrecoverable`
-- do banco.
--
-- Idempotente: o WHERE só pega linhas ainda em `unrecoverable`, então rodar
-- duas vezes não reabre nada na segunda (a contagem "antes" da segunda
-- rodada já é zero). NÃO EXECUTAR sem revisão do operador.
--
-- Rodar na VPS, em /opt/project-hunter:
--   docker exec -i hunter-postgres-1 psql -U hunter -d hunter -At < infra/scripts/sql/2026-09-08-reopen-false-unrecoverable.sql

-- antes
SELECT count(*) AS unrecoverable_antes
  FROM ingestion_gaps g
  JOIN markets m ON m.id = g.market_id
 WHERE g.status = 'unrecoverable'
   AND m.symbol IN ('BTCUSDT', 'UNIUSDT')
   AND g.detected_at >= '2026-09-08 13:40'
   AND EXISTS (
         SELECT 1
           FROM candles c
          WHERE c.market_id = g.market_id
            AND c.timeframe = g.timeframe
            AND c.is_final
            AND c.open_time < g.gap_start
       );

UPDATE ingestion_gaps g
   SET status = 'open'
  FROM markets m
 WHERE m.id = g.market_id
   AND g.status = 'unrecoverable'
   AND m.symbol IN ('BTCUSDT', 'UNIUSDT')
   AND g.detected_at >= '2026-09-08 13:40'
   AND EXISTS (
         SELECT 1
           FROM candles c
          WHERE c.market_id = g.market_id
            AND c.timeframe = g.timeframe
            AND c.is_final
            AND c.open_time < g.gap_start
       );

-- depois (deve ser 0 nesta e em qualquer rodada seguinte, para este escopo)
SELECT count(*) AS unrecoverable_depois
  FROM ingestion_gaps g
  JOIN markets m ON m.id = g.market_id
 WHERE g.status = 'unrecoverable'
   AND m.symbol IN ('BTCUSDT', 'UNIUSDT')
   AND g.detected_at >= '2026-09-08 13:40'
   AND EXISTS (
         SELECT 1
           FROM candles c
          WHERE c.market_id = g.market_id
            AND c.timeframe = g.timeframe
            AND c.is_final
            AND c.open_time < g.gap_start
       );
