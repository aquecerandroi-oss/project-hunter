SET statement_timeout='60s';
COPY (
SELECT b.mint, min(b.entry_at) AS entry_at, max(b.exit_at) AS exit_at, count(*) AS legs, avg(b.r_multiple) AS r_avg, t.creator, t.created_at
FROM meme_paper_bets b JOIN meme_tokens t USING (mint)
WHERE b.entry_at >= now() - interval '24 hours' AND b.status='closed' AND b.exit_at IS NOT NULL
GROUP BY b.mint, date_trunc('minute', b.entry_at), t.creator, t.created_at
ORDER BY 2
) TO STDOUT WITH CSV HEADER;
