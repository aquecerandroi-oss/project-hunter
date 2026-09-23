SET statement_timeout='240s';
COPY (
WITH first_bet AS (
  SELECT DISTINCT ON (mint) id, mint, entry_at, exit_at, entry::text AS entry_json, exit::text AS exit_json,
         exit_intent->>'reason' AS exit_reason, pnl_sol, params::text AS params, mode, leg
  FROM meme_paper_bets
  WHERE status='closed' AND entry_at >= '2026-09-16' AND exit_at IS NOT NULL AND leg <> 'probe'
  ORDER BY mint, entry_at
)
SELECT * FROM first_bet ORDER BY entry_at
) TO STDOUT WITH CSV HEADER;
