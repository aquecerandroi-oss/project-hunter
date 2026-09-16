-- R5 / Q01 — ordem x checagem: TODAS as checagens que falharam ou ficaram
-- indisponiveis em cada ordem real de hoje (nao so a primeira, que e a unica
-- que vira meme_live_orders.reason).
--
-- admission->'checks' e um array de {name, state, refusal, value, limit, message}
-- gravado mesmo depois do primeiro reprovado (RISK_ENGINE_MEME.md 4).
SELECT to_char(o.received_at AT TIME ZONE 'America/Sao_Paulo', 'HH24:MI:SS') AS brt,
       left(o.admission->>'mint', 6)                                        AS mint,
       o.reason                                                             AS motivo_gravado,
       c->>'name'                                                           AS checagem,
       c->>'state'                                                          AS estado,
       c->>'refusal'                                                        AS recusa,
       c->>'value'                                                          AS valor,
       c->>'limit'                                                          AS limite,
       c->>'message'                                                        AS mensagem
FROM meme_live_orders o,
     jsonb_array_elements(o.admission->'checks') c
WHERE c->>'state' <> 'passed'
ORDER BY o.received_at, (c->>'name');
