-- R14 16/09 17h — termos de vigilancia do plantao das 17h (PAID / "via UsePaid", ARGUS,
-- ZEC / ZCASH / privacy) contra as criacoes da ultima hora: quantas casam, quantas entraram
-- na janela do executor, quantas encheram a curva e se a graduacao e forjada (KB-0103).

-- (a) contagem por termo (simbolo + nome + descricao)
WITH c AS (SELECT * FROM meme_tokens WHERE created_at >= now() - make_interval(mins => 70)),
txt AS (SELECT mint, (coalesce(symbol,chr(32))||chr(32)||coalesce(name,chr(32))||chr(32)
                      ||coalesce(description,chr(32))) AS s FROM c)
SELECT (SELECT count(*) FROM c) AS criadas_70min,
  count(*) FILTER (WHERE s ~* $$paid$$)    AS paid,
  count(*) FILTER (WHERE s ~* $$usepaid$$) AS usepaid,
  count(*) FILTER (WHERE s ~* $$argus$$)   AS argus,
  count(*) FILTER (WHERE s ~* $$zcash$$)   AS zcash,
  count(*) FILTER (WHERE s ~* $$zec$$)     AS zec,
  count(*) FILTER (WHERE s ~* $$privacy$$) AS privacy
FROM txt;

-- (b) por campo, entrada na janela do executor e desfecho
WITH c AS (SELECT * FROM meme_tokens WHERE created_at >= now() - make_interval(mins => 70))
SELECT count(*) FILTER (WHERE description ~* $$usepaid$$) AS desc_usepaid,
  count(*) FILTER (WHERE symbol ~* $$paid$$ OR name ~* $$paid$$) AS sym_paid,
  count(*) FILTER (WHERE symbol ~* $$zec|zcash$$ OR name ~* $$zec|zcash$$) AS sym_zec,
  count(*) FILTER (WHERE description ~* $$usepaid$$ AND EXISTS (
     SELECT 1 FROM meme_features_15s x WHERE x.mint=c.mint AND x.age_s BETWEEN 30 AND 300
       AND x.curve_progress_pct BETWEEN 0.02 AND 0.50 AND x.tape_reason IS NULL
       AND x.net_sol_flow_60s > 0)) AS usepaid_na_janela,
  count(*) FILTER (WHERE description ~* $$usepaid$$ AND completed_at IS NOT NULL) AS usepaid_encheu,
  count(*) FILTER (WHERE completed_at IS NOT NULL) AS todas_encheram
FROM c;

-- (c) as que casam por simbolo/nome, nominais
SELECT c.symbol, left(c.mint,6), to_char(c.created_at AT TIME ZONE $$America/Sao_Paulo$$, $$HH24:MI$$),
  c.completed_at IS NOT NULL, left(coalesce(c.name,chr(32)),20), left(coalesce(c.description,chr(32)),60)
FROM meme_tokens c
WHERE c.created_at >= now() - make_interval(mins => 70)
  AND (c.symbol ~* $$paid|zec|zcash|argus$$ OR c.name ~* $$zcash|argus$$)
ORDER BY c.created_at LIMIT 20;

-- (d) assinatura de forjada (KB-0103) nas PAID* que encheram
WITH c AS (SELECT * FROM meme_tokens WHERE created_at >= now() - make_interval(mins => 70)
             AND completed_at IS NOT NULL AND (symbol ~* $$paid$$ OR name ~* $$paid$$)),
tr AS (SELECT r.mint, r.trader, sum(r.sol_lamports)/1e9 AS sol FROM meme_trades r
       JOIN c ON c.mint=r.mint WHERE r.side=$$buy$$ GROUP BY 1,2),
tot AS (SELECT mint, sum(sol) AS total, count(*) AS n FROM tr GROUP BY 1),
mx AS (SELECT DISTINCT ON (mint) mint, sol FROM tr ORDER BY mint, sol DESC)
SELECT c.symbol, left(c.mint,6), extract(epoch FROM (c.completed_at-c.created_at))::int AS seg_ate_encher,
  c.migrated_at IS NOT NULL, tot.n AS compradores_fita, round(tot.total::numeric,1) AS sol_comprado,
  round(100*mx.sol/nullif(tot.total,0)::numeric,1) AS maior_pct,
  (SELECT count(*) FROM meme_features_15s x WHERE x.mint=c.mint) AS linhas_15s
FROM c LEFT JOIN tot ON tot.mint=c.mint LEFT JOIN mx ON mx.mint=c.mint ORDER BY 3;

-- (e) base-rate da hora: quantas encheram <= 60 s do mint (nascem cheias)
SELECT count(*) FILTER (WHERE extract(epoch FROM (completed_at-created_at)) <= 60) AS encheu_ate_60s,
       count(*) AS encheram
FROM meme_tokens WHERE created_at >= now() - make_interval(mins => 70) AND completed_at IS NOT NULL;
