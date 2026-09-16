-- R13/Q01 (KB-0105) — REPLICACAO de KB-0103 nos dias 12/09 e 13/09 (fora da amostra do R9).
-- Uma linha por moeda GRADUADA do dia BRT com cobertura de fita (meme_trades) e >= 20 SOL comprados
-- ate encher. Reusa a metodologia de 2026-09-16-r9-q03/q04: o ROTULO vem da fita (carteiras distintas),
-- nunca das colunas que as regras leem.
--   forjada  = <= 30 compradores unicos distintos na subida;
--   organica = >= 100; a faixa 31-99 fica cinza, fora da conta.
-- CORRECAO DE FUSO frente ao R9: "date 'X' AT TIME ZONE 'America/Sao_Paulo'" devolve TIMESTAMP (sem fuso),
-- comparado depois no fuso da sessao (UTC) — as janelas do R9 estao deslocadas em 3 h. Aqui os limites do
-- dia BRT sao escritos como timestamptz explicito ('... 00:00:00-03').
-- Rodar um dia por vez (regra: <= 24 h por consulta). Trocar as duas constantes abaixo.
SET statement_timeout = 240000;
WITH g AS (
  SELECT t.mint, upper(t.symbol) AS sym, t.creator, t.created_at, t.completed_at,
         (t.twitter IS NULL AND t.website IS NULL) AS sem_social,
         extract(epoch FROM t.completed_at - t.created_at) AS s_ate_encher
  FROM meme_tokens t
  WHERE t.created_at >= timestamptz '2026-09-12 00:00:00-03'
    AND t.created_at <  timestamptz '2026-09-13 00:00:00-03'
    AND t.completed_at IS NOT NULL
),
ped AS (  -- pedigree v1 replicado (E2 de hoje): creator_serial e symbol_clone
  SELECT g.mint,
         (SELECT count(*) FROM meme_tokens o WHERE o.creator = g.creator AND o.mint <> g.mint
            AND o.created_at >= g.created_at - interval '1 hour' AND o.created_at < g.created_at) AS cr1h,
         (SELECT count(*) FROM meme_tokens o WHERE upper(o.symbol) = g.sym AND o.mint <> g.mint
            AND o.created_at >= g.created_at - interval '24 hours' AND o.created_at < g.created_at) AS sd24
  FROM g
),
tr AS (
  SELECT g.mint, tr.trader, sum(tr.sol_lamports) / 1e9 AS sol
  FROM g JOIN meme_trades tr ON tr.mint = g.mint AND tr.side = 'buy'
   AND tr.block_time >= g.created_at - interval '1 minute'
   AND tr.block_time <= g.completed_at + interval '1 minute'
  GROUP BY 1, 2
),
fita AS (
  SELECT mint, count(*) AS compradores, sum(sol) AS sol_comprado,
         max(sol) / nullif(sum(sol), 0) AS fatia_do_maior
  FROM tr GROUP BY 1 HAVING sum(sol) >= 20
)
SELECT g.mint, g.sym, g.sem_social, p.cr1h, p.sd24,
       round(g.s_ate_encher::numeric, 0) AS s_ate_encher,
       f.compradores, round(f.sol_comprado::numeric, 2) AS sol_comprado,
       round(f.fatia_do_maior::numeric, 4) AS fatia_do_maior,
       EXISTS (SELECT 1 FROM meme_features_15s s WHERE s.mint = g.mint) AS tem_15s,
       CASE WHEN f.compradores <= 30 THEN 'forjada'
            WHEN f.compradores >= 100 THEN 'organica' ELSE 'cinza' END AS rotulo
FROM g JOIN ped p ON p.mint = g.mint JOIN fita f ON f.mint = g.mint;
