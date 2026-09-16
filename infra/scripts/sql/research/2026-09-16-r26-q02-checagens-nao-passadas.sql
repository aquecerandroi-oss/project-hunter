-- R26 / Q02 — toda checagem com state <> passed em cada uma das 26 ordens de
-- hoje (a base da reavaliacao sob T4.28g / T4.28h / teto de top-10 30 %).
\pset pager off
SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS') AS brt,
       left(o.admission->>'mint', 6) AS mint,
       c->>'name'    AS checagem,
       c->>'state'   AS estado,
       c->>'refusal' AS recusa,
       c->>'value'   AS valor,
       c->>'limit'   AS limite
FROM meme_live_orders o,
     jsonb_array_elements(o.admission->'checks') c
WHERE c->>'state' <> 'passed'
ORDER BY o.received_at, (c->>'name');
