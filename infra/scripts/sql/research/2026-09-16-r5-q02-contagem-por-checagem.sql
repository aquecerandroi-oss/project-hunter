-- R5 / Q02 — custo escondido: em quantas ordens cada checagem recusaria se
-- fosse a unica. Conta TODAS as nao-passadas, nao so a primeira.
SELECT c->>'name'                                AS checagem,
       c->>'refusal'                             AS recusa,
       c->>'state'                               AS estado,
       count(*)                                  AS ordens,
       count(DISTINCT o.admission->>'mint')      AS mints
FROM meme_live_orders o,
     jsonb_array_elements(o.admission->'checks') c
WHERE c->>'state' <> 'passed'
GROUP BY 1, 2, 3
ORDER BY ordens DESC, 1;
