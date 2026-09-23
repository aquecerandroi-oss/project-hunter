# R69 — desenho do snapshot de coorte (congelado antes de correr)

## Hipótese
Os 13 filtros da mesa são limiares ABSOLUTOS. Hipótese: a mesma variável expressa como
**percentil da moeda dentro da coorte viva naquele instante** separa onde o absoluto falhou
(R65 e R67: nada sobrevive a Benjamini-Hochberg); e o **estado da coorte** (quente/fria)
prediz se vale a pena entrar.

## Fonte da coorte
`meme_features_15s` (4,17 M linhas 12–23/09): uma linha por mint rastreado por tique de ~15 s,
com `as_of` (instante do tique), `computed_at` (quando a linha foi escrita), `tape_as_of`.
Variáveis: age_s, curve_progress_pct, progress_delta_60s, mcap_sol, mcap_delta_60s,
mcap_slope_60s, buys_60s, sells_60s, unique_buyers_60s, net_sol_flow_60s,
curve_volume_60s_sol, snipers, dev_share, holders.

## Definição da coorte viva em t
`coorte(t)` = para cada mint, a linha de `meme_features_15s` mais recente com
  `as_of <= t`  E  `as_of > t - 120 s`  E  `computed_at <= t`
(120 s = 8 tiques de 15 s; um mint que deixou de ser rastreado sai da coorte em ≤ 120 s.)

## Percentil
Para a variável v e a decisão (mint m, instante t):
  `p_v = [ #{c em coorte(t) : v(c) < v(m)} + 0.5 * #{c : v(c) = v(m)} ] / #{c : v(c) não nulo}`
O valor do sujeito v(m) vem da MESMA fonte (sua linha de coorte), não de `meme_proposals.reasons`,
para que sujeito e coorte estejam na mesma unidade e no mesmo tique. Paridade com `reasons`
é verificada e reportada.

## Guarda anti-antecipação (o ponto que pode vazar em silêncio)
1. `as_of <= t` — o tique não pode ser posterior à decisão.
2. `computed_at <= t` — a linha não pode ter sido ESCRITA depois da decisão (o worker pode
   recalcular/preencher retroativamente; sem isto a coorte veria números que não existiam).
3. Nenhuma linha do futuro do próprio sujeito.
4. Teste local: função pura `live_cohort(rows, t, window_s)` com teste que acrescenta linhas
   com `as_of > t` e com `computed_at > t` e exige saída idêntica; e paridade SQL↔Python
   sobre uma amostra de decisões com as linhas cruas exportadas.
5. Medição do vazamento: correr a coorte SEM a guarda (2) e reportar quantas linhas entrariam.

## Estado da coorte (por balde de 5 min, 12–23/09)
Todos calculados só com `as_of` dentro do balde e `computed_at <= fim do balde`:
- `live_n` — mints distintos na coorte
- `births_min` — mints criados/min (`meme_tokens.created_at`), TODOS, não só rastreados
- `frac_pos_flow` — fração da coorte com `net_sol_flow_60s > 0`
- `med_prog_60_300` — progresso mediano das moedas com `age_s` entre 60 e 300 s
- `grads_h` — graduações/hora (`meme_tokens.migrated_at`)

## Desfechos (os mesmos do R65/R67)
- primário: `ret = pnl_sol / size_sol` (retorno líquido por SOL arriscado), papel + real
- secundário: MFE em 300 s — só onde há fita/fotos; declarado como piso quando só há fotos

## Disciplina estatística (herdada do R65/R67)
Uma aposta por mint (dedup), bootstrap por cluster de mint (10 000), permutação
estratificada por dia (10 000), Benjamini-Hochberg sobre a grade inteira,
teste planalto-vs-pico, split temporal 12–19/09 (ajuste) / 20–23/09 (teste).

## Cobertura / viés declarado
O teto de rastreamento era 120 mints (300 desde hoje). A coorte NÃO é o mercado:
quantificar `rastreados / criados` por balde de 5 min e comparar a taxa de graduação
de rastreados vs não rastreados.

---
# EMENDA 1 (após revisão de desenho da Astra, ANTES de qualquer teste) — 2026-09-23

1. **`t` = instante da decisão**, `meme_proposals.proposed_at`, não `entry_at` (o fill).
2. **Percentil deixa o sujeito FORA da referência** (leave-one-out): denominador `N_{v,-m}`.
3. **`tape_as_of <= as_of <= t`** exigido além de `computed_at <= t`.
   `computed_at` é `now()` = início da transação, não o commit → **sensibilidade com atraso
   conservador de 5 s** (`computed_at <= t - 5 s`) e limitação declarada.
4. **População primária**: `flow_v2`, `measured`, uma aposta por mint, **`age_s <= 300 s`**
   na decisão (reduz a cauda mantida por posições abertas). Sem misturar papel e real.
5. **Família congelada AGORA: 17 hipóteses** = 13 percentis + 4 medidas de estado da coorte.
   BH a 10 % + Benjamini-Yekutieli como referência conservadora. Cortes são descritivos.
6. **Teste B**: estado congelado no **INÍCIO** do balde; `births` do balde anterior;
   `grads` conhecidas na hora anterior por `graduated_board_seen_at` (tempo de conhecimento),
   não `migrated_at`. Reamostragem em **blocos de 60 min** (sensibilidade 120 min + LODO).
   Balde sem entrada tem desfecho **indefinido**, não zero.
7. **Falseamento antes do principal**: (i) invariância ao futuro (teste unitário);
   (ii) variável aleatória estável por mint atravessando o mesmo pipeline;
   (iii) empates → 0,5; (iv) paridade SQL↔Python sobre amostra.
8. **Ponto cego**: graduação comparada com **horizonte de acompanhamento igual**, e a
   classificação rastreado/não-rastreado usa `first_seen_source` (como soubemos da moeda),
   não a existência de uma graduação posterior.
9. **Discordância registada**: a Astra queria o teste principal como *contribuição
   incremental do percentil sobre o absoluto* num modelo. Com n ≈ 500 e o histórico de
   sobreajuste do R65/R67, faço a versão não-paramétrica: associação marginal do percentil
   **e** estratificação por tercil do absoluto (o percentil só conta se separar DENTRO do
   estrato do absoluto). Declarado como aproximação, não como o teste que ela pediu.

# EMENDA 2 (após ver SÓ a distribuição do regressor, antes de qualquer desfecho) — 2026-09-23
O corte `percentil >= 0,50` é degenerado: o portão `flow_v2` já seleciona a **cauda superior
da coorte** (mediana do percentil: progresso 0,963 · mcap 0,946 · compras 0,934 ·
compradores 0,965 · fluxo 0,985 · volume 0,957). Com 0,50, `p_prog` e `p_mcap` ficam com
1–2 observações de um lado. **Corte passa a ser a MEDIANA DA AMOSTRA** do próprio percentil —
exatamente o mesmo corte que o R65/R67 usaram na versão absoluta, o que preserva o
confronto directo relativo-vs-absoluto. A família continua com 17 hipóteses.
Esta decisão foi tomada olhando apenas o regressor; nenhum desfecho foi consultado.
