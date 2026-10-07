SET statement_timeout='300s';
BEGIN READ ONLY;
-- 3. propostas (qualquer conjunto) em moedas Mayhem pelo bit da cadeia (sem desfechos)
SELECT coalesce(t.mayhem_enabled::text,'null') mayhem, count(*) props, count(DISTINCT p.mint) mints,
       min(p.decided_at) first_dec, max(p.decided_at) last_dec, count(DISTINCT date_trunc('day',p.decided_at)) days
FROM meme_proposals p LEFT JOIN meme_tokens t ON t.mint=p.mint GROUP BY 1 ORDER BY 1;
-- 4. apostas de papel / posições reais em Mayhem (só contagem e datas)
SELECT 'paper' k, coalesce(t.mayhem_enabled::text,'null') mayhem, count(*) n, count(DISTINCT b.mint) mints, min(b.entry_at) a, max(b.entry_at) z
FROM meme_paper_bets b LEFT JOIN meme_tokens t ON t.mint=b.mint GROUP BY 1,2
UNION ALL
SELECT 'live', coalesce(t.mayhem_enabled::text,'null'), count(*), count(DISTINCT p.mint), min(p.entry_at), max(p.entry_at)
FROM meme_live_positions p LEFT JOIN meme_tokens t ON t.mint=p.mint GROUP BY 1,2 ORDER BY 1,2;
-- 5. recusas por mint: só mayhem_curve (o quase-passou) e propostas, por dia
SELECT refusal, count(*) n, count(DISTINCT mint) mints, min(as_of) a, max(as_of) z, count(DISTINCT date_trunc('day',as_of)) days
FROM meme_gate_refusals_by_mint WHERE refusal IN ('mayhem_curve','mayhem_unknown') OR refusal IS NULL GROUP BY 1 ORDER BY 1;
COMMIT;
