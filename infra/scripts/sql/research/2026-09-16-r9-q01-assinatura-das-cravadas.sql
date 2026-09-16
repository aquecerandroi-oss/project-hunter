-- R9/Q01 (KB-0103) — assinatura medida dos clones "fundo/instituicao" com preco forjado.
-- Universo: moedas CRIADAS entre 14/09 e 16/09 (dias BRT) que ENCHERAM a curva (completed_at NOT NULL).
-- Eixos, todos derivados de dados que o radar ja guarda:
--   (a) clones no dia .... outras moedas com o MESMO upper(symbol) criadas no MESMO dia BRT;
--   (b) sem social ....... twitter IS NULL AND website IS NULL (colunas sociais da 0041);
--   (c) pico/velocidade .. max(real_sol_reserves) e quantas FOTOS da curva pegaram a subida (1 < rsr < 84);
--   (d) criador em serie . outras moedas do mesmo creator nos 7 d anteriores a criacao desta;
--   (e) compradores ...... max(unique_buyers_60s) e sum(buys_60s) da serie de 15 s durante a subida.
-- Uma linha por moeda; a agregacao fica nas consultas Q02/Q03. Saida: o cruzamento (clone x social x compradores).
WITH g AS (
  SELECT t.mint, upper(t.symbol) AS sym, t.creator, t.created_at, t.completed_at, t.migrated_at,
         (t.twitter IS NULL AND t.website IS NULL) AS sem_social,
         (t.created_at AT TIME ZONE 'America/Sao_Paulo')::date AS dia_brt
  FROM meme_tokens t
  WHERE t.created_at >= (date '2026-09-14' AT TIME ZONE 'America/Sao_Paulo')
    AND t.created_at <  (date '2026-09-17' AT TIME ZONE 'America/Sao_Paulo')
    AND t.completed_at IS NOT NULL
),
-- (a) clones do mesmo simbolo no mesmo dia BRT (todas as criacoes do dia, nao so as graduadas)
sym_dia AS (
  SELECT upper(symbol) AS sym, (created_at AT TIME ZONE 'America/Sao_Paulo')::date AS dia_brt, count(*) AS n_sym_dia
  FROM meme_tokens
  WHERE created_at >= (date '2026-09-14' AT TIME ZONE 'America/Sao_Paulo')
    AND created_at <  (date '2026-09-17' AT TIME ZONE 'America/Sao_Paulo')
  GROUP BY 1, 2
),
-- (d) criador em serie: outras moedas do mesmo criador nos 7 d anteriores
cria AS (
  SELECT g.mint,
         (SELECT count(*) FROM meme_tokens o
           WHERE o.creator = g.creator AND o.mint <> g.mint
             AND o.created_at >= g.created_at - interval '7 days' AND o.created_at <= g.created_at) AS n_criador_7d,
         (SELECT count(*) FROM meme_tokens o
           WHERE o.creator = g.creator AND o.mint <> g.mint
             AND o.created_at >= g.created_at - interval '1 hour' AND o.created_at <  g.created_at) AS n_criador_1h,
         (SELECT count(*) FROM meme_tokens o
           WHERE upper(o.symbol) = g.sym AND o.mint <> g.mint
             AND o.created_at >= g.created_at - interval '24 hours' AND o.created_at < g.created_at) AS sym_dup_24h
  FROM g
),
-- (c) a curva: pico de SOL real e quantas fotos pegaram a subida
curva AS (
  SELECT g.mint,
         max(s.real_sol_reserves) AS pico_sol,
         max(s.mcap_sol) AS pico_mcap_sol,
         count(*) FILTER (WHERE s.real_sol_reserves > 1 AND s.real_sol_reserves < 84) AS fotos_na_subida,
         count(*) AS fotos
  FROM g JOIN meme_curve_snapshots s ON s.mint = g.mint
   AND s.observed_at >= g.created_at AND s.observed_at <= g.completed_at + interval '2 minutes'
  GROUP BY 1
),
-- (e) a fita de 15 s durante a subida
fita AS (
  SELECT g.mint,
         max(f.unique_buyers_60s) AS max_compradores_60s,
         sum(f.buys_60s) AS soma_buys,
         max(f.holders) AS max_holders,
         count(*) AS linhas_15s
  FROM g JOIN meme_features_15s f ON f.mint = g.mint
   AND f.as_of >= g.created_at AND f.as_of <= g.completed_at + interval '1 minute'
  GROUP BY 1
)
SELECT g.mint, g.sym, g.dia_brt, g.sem_social,
       coalesce(sd.n_sym_dia, 1) AS n_sym_dia,
       c.n_criador_7d, c.n_criador_1h, c.sym_dup_24h,
       round(cu.pico_sol::numeric, 3) AS pico_sol,
       cu.fotos_na_subida, cu.fotos,
       fi.max_compradores_60s, fi.soma_buys, fi.max_holders, fi.linhas_15s,
       round(extract(epoch FROM g.completed_at - g.created_at)::numeric, 0) AS s_ate_encher,
       (g.migrated_at IS NOT NULL) AS migrou
FROM g
LEFT JOIN sym_dia sd ON sd.sym = g.sym AND sd.dia_brt = g.dia_brt
LEFT JOIN cria c ON c.mint = g.mint
LEFT JOIN curva cu ON cu.mint = g.mint
LEFT JOIN fita fi ON fi.mint = g.mint;
