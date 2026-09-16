-- R6/Q03 (KB-0100) — o casamento AUTOMATICO do job de minuto (hunter_meme_worker.events.events_match_once):
-- evento sem mint observado nos ultimos 65 min <-> meme_tokens criado nos 60 min SEGUINTES,
-- por handle_hint (twitter ILIKE %handle%) ou symbol_hint (symbol = hint). Aqui reproduzimos a regra
-- SEM a janela de 65 min do lado do evento, para saber se ela teria casado alguma coisa em algum momento.
SELECT e.id, to_char(e.observed_at at time zone 'America/Sao_Paulo','DD/MM HH24:MI') AS obs_brt,
       e.kind, e.confidence, coalesce(e.symbol_hint,'-') AS symbol_hint, coalesce(e.handle_hint,'-') AS handle_hint,
       coalesce(e.mint,'NULL') AS mint_gravado, coalesce(e.matched_at::text,'-') AS matched_at,
       (SELECT count(*) FROM meme_tokens t
         WHERE t.created_at >= e.observed_at AND t.created_at < e.observed_at + make_interval(mins => 60)
           AND ((e.handle_hint IS NOT NULL AND t.twitter ILIKE '%'||e.handle_hint||'%')
                OR (e.symbol_hint IS NOT NULL AND t.symbol = e.symbol_hint))) AS candidatas_regra_do_job,
       left(e.title, 48) AS titulo
FROM meme_events e ORDER BY e.observed_at;
-- Propostas ligadas a evento (link_proposals) e contagem de eventos casados.
SELECT count(*) AS propostas_hoje, count(*) FILTER (WHERE event_id IS NOT NULL) AS com_event_id
FROM meme_proposals WHERE created_at >= date_trunc('day', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo';
-- Existe alguma moeda com o simbolo exato do hint em QUALQUER hora do dia? (se sim, o que falhou foi a janela)
SELECT e.symbol_hint, count(t.mint) AS moedas_com_simbolo_exato_no_dia,
       min(to_char(t.created_at at time zone 'America/Sao_Paulo','HH24:MI')) AS primeira_brt,
       max(to_char(t.created_at at time zone 'America/Sao_Paulo','HH24:MI')) AS ultima_brt
FROM meme_events e LEFT JOIN meme_tokens t
  ON t.symbol = e.symbol_hint
 AND t.created_at >= date_trunc('day', now() at time zone 'America/Sao_Paulo') at time zone 'America/Sao_Paulo'
WHERE e.symbol_hint IS NOT NULL GROUP BY 1 ORDER BY 1;
