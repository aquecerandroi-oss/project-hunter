-- R41 16/09 21h32 BRT -- as PRIMEIRAS ordens CONFIRMADAS da mesa real (TAXCOIN, 21:31 BRT):
-- intent, fill, admissao completa e a cadeia depois da compra. Primeiro lamport gasto do dia.
SET statement_timeout = 200000;

-- (a) linha a linha
SELECT to_char(o.received_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  coalesce(t.symbol,$$?$$) AS symbol, left(p.mint,6) AS mint6, o.side, o.status,
  coalesce(o.reason,$$-$$) AS motivo, o.attempt, o.intent::text AS intent, o.fill::text AS fill,
  left(o.tx_signature,16) AS tx16,
  to_char(o.settled_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS liquidada,
  extract(epoch FROM (o.settled_at - o.received_at))::int AS latencia_s,
  p.origin, p.status AS proposta, p.mode
FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
LEFT JOIN meme_tokens t ON t.mint=p.mint
WHERE o.tx_signature IS NOT NULL ORDER BY o.received_at;

-- (b) checagens da admissao da ordem de COMPRA
SELECT to_char(o.received_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  o.side, c->>$$name$$ AS checagem, c->>$$state$$ AS estado,
  c->>$$value$$ AS valor, c->>$$limit$$ AS limite, c->>$$refusal$$ AS refusal
FROM meme_live_orders o, LATERAL jsonb_array_elements(o.admission->$$checks$$) c
WHERE o.tx_signature IS NOT NULL ORDER BY o.received_at, c->>$$name$$;

-- (c) a cadeia da TAXCOIN desde a compra (real_sol_reserves, invariante)
SELECT to_char(c.observed_at AT TIME ZONE $$America/Sao_Paulo$$,$$HH24:MI:SS$$) AS hora_brt,
  round(c.real_sol_reserves,4) AS rsol, round(c.mcap_sol,2) AS mcap,
  round(c.virtual_sol_reserves - c.real_sol_reserves,3) AS invariante, c.complete, c.mayhem_enabled
FROM meme_curve_snapshots c
WHERE c.mint IN (SELECT p.mint FROM meme_live_orders o JOIN meme_proposals p ON p.id=o.proposal_id
                 WHERE o.tx_signature IS NOT NULL)
  AND c.observed_at >= timestamptz $$2026-09-16 21:29-03$$
ORDER BY c.observed_at;
