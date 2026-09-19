# R61 — KOL e "call" antecipam ou confirmam o bum? (boards `kol_count`, `meme_event_matches`, identidade social)

**Data:** 2026-09-19, `as_of` 04:55 UTC (01:55 BRT). **Janela:** últimas 72 h (16/09 04:55 → 19/09 04:55 UTC), partições `_2026_09`. **Pergunta do Everton (02:0x BRT):** "tem muita gente chamando moeda; com muitos seguidores a moeda explode rápido e cai rápido — estamos analisando as que estão começando a bombar?" → o sinal de influenciador/call que **já gravamos** antecipa o bum ou só o confirma?

**Resposta curta: confirma.** Com o que temos (o `kol_count` dos boards, gravado por minuto), a primeira aparição de um KOL chega com o pico **no mesmo minuto**: em 59 % das moedas o pico da série de 15 s é **anterior ou igual** ao instante em que vemos o KOL; o bum (+50 % em 60 s), quando existe (37 % das moedas), começa em mediana **16 s depois** do que vemos — e o nosso próprio instante tem **±55 s de incerteza** (bucket de minuto). Comprar 20 s depois da aparição, com 1,25 %/perna + 3 % de slippage, trailing 20 % ou 5 min, dá **R médio −0,071, acerto 15 % (n = 3 486)** — melhor que o controle sem KOL (−0,114, acerto 5 %), mas negativo em **todas** as células que a regra do brief consegue executar. `meme_event_matches` (notícia → moeda) não carrega informação nenhuma nesta janela: as 2 968 casadas são clones de nome criados **19 h** (mediana) depois do evento, R −0,090, acerto 5 % — igual ao controle. Identidade social no nascimento muda a **probabilidade de graduar** (perfil no X 9,9 % vs post 2,1 %; X + Telegram 11,2 % vs nada 2,6 %) mas não o timing, e sobe também a taxa de pump-and-dump (9,4 % vs 4,8 %).

O único caminho com sinal positivo é **ler o mesmo `kol` no patch de 1 s que o worker já recebe e hoje só persiste por minuto**: a estimativa "entrada no meio do intervalo de incerteza" (proxy de feed a 1 s) dá **+0,08 R [+0,01, +0,16], acerto 38 %, n = 445** para aparições entre 2 e 30 min de idade — frágil (sem os 3 maiores cai para +0,04; por dia: +0,20, +0,05, +0,04, −0,03). É tese para pré-registrar (EXP-M20), não para ligar.

## 1. Dados, definições, cobertura

| item | valor |
|---|---|
| boards (`meme_board_observations_2026_09`, 72 h) | `new` 243 685 linhas / 114 326 mints; `graduating` 155 019 / 5 043; `movers` 152 927 / 15 594; `graduated` 123 381 / 2 807. **Uma linha por mint por board por minuto fechado**; `observed_at` = último `serverTs` do board no minuto; `mint_updated_at` = último patch do mint |
| `kol_count` | `kol` da entrada do board = `numKolsTraded` do indexador da pump.fun (carteiras da lista "KOL" do site que negociaram a moeda). **Não é chamada pública**: é trade on-chain de carteira rotulada. **`age_s` é obsoleto** nos deltas (patch só traz campos alterados) — idade calculada como `t − meme_tokens.created_at` |
| moedas criadas (`meme_tokens`, 72 h) | 96 236; `twitter` 46 353 (48 %), `telegram` 1 516 (1,6 %), `website` 30 689, graduadas (`completed_at`) 3 079 (3,2 %) |
| série fina (`meme_curve_snapshots_2026_09`) | 2,25 M linhas / 92 715 mints; `solana_rpc` 2,13 M + `pumpfun_rest` 116 k. Cadência medida em 3 000 moedas de 20–26 h atrás: 0–60 s ≈ 4,8 fotos/mint; 60–120 s ≈ 4,9; 120–300 s ≈ 13,8 (~13 s); **300–600 s ≈ 2,2 e depois de 10 min só 4 de 3 000 mints** (as fixadas/top-K). `meme_features_15s` deriva dessas fotos (1,57 M linhas / 92 308 mints, idade < 300 s ou fixada) |
| série lenta | os próprios boards (`market_cap_usd`, 1 min, enquanto o mint está em algum board) |
| eventos | `meme_events`: 22 registrados (16/09 10:30 → 17/09 14:00 UTC — **nenhum nas últimas 39 h**); `meme_event_matches`: 3 365 linhas / 2 995 mints casados de 17/09 02:41 a 19/09 04:42 |
| custos do brief | taxa 1,25 %/perna, slippage 3 % por lado, entrada na 1.ª foto ≥ sinal + 20 s (até +90 s), saída trailing 20 % do pico pós-entrada **ou** 5 min (1.ª foto > 300 s), fechamento forçado na última foto quando a série acaba antes (`censored`) |
| código | `.claude/state/r61/analyze2.py` (NumPy/Polars), `analyze_events.py`, `strat.py`, `ci.py`; SQL `q0–q8.sql`, `e1–e3.sql` (eventos KOL + séries), `c1–c3.sql` (controle), `m1–m3.sql` (casamentos); saídas `out2.txt`, `out_events.txt`, `out_strat.txt`, `out_ci.txt` |

### 1.1 O que é "primeira aparição de KOL" aqui

Por mint, ordenando as linhas de board por `observed_at`, o **primeiro incremento** de `kol_count` (`lag(kol_count) < kol_count`). Instante do sinal `t_kol = mint_updated_at` da linha do incremento (o último patch do mint naquele minuto — o mais tarde que poderíamos ter sabido); limite inferior `t_prev = mint_updated_at` da linha anterior. O KOL negociou em algum ponto de `[t_prev, t_kol]`; a largura desse intervalo é a **incerteza** do sinal (p50 55 s, p90 76 s).

```sql
WITH b AS (
  SELECT mint, board, observed_at, mint_updated_at, kol_count, market_cap_usd, holders, txs,
         lag(kol_count) OVER w AS prev_kol, lag(mint_updated_at) OVER w AS prev_upd
  FROM meme_board_observations_2026_09
  WHERE observed_at > now() - interval '72 hours' AND kol_count IS NOT NULL
  WINDOW w AS (PARTITION BY mint ORDER BY observed_at, board)
), inc AS (
  SELECT DISTINCT ON (mint) * FROM b WHERE prev_kol IS NOT NULL AND kol_count > prev_kol ORDER BY mint, observed_at
) SELECT i.*, t.created_at, t.completed_at, t.twitter IS NOT NULL AS has_tw, t.telegram IS NOT NULL AS has_tg, t.twitter_kind
  FROM inc i LEFT JOIN meme_tokens t USING (mint);
```

| população (72 h) | mints |
|---|---|
| mints com `kol_count` observado em algum board | 116 519 |
| com `kol_count ≥ 1` em algum momento | 38 158 (33 %) |
| **já nascem com KOL** (≥ 1 na primeira linha, idade mediana 1 s, holders 1–3, txs ~25) | 33 767 — é o bundle do bloco de criação com carteira da lista; **não é sinal** |
| transição **0 → ≥ 1 testemunhada** | 4 391 |
| primeiro incremento k → k+1 com k ≥ 1 | 1 920 |
| analisadas (com `created_at` e série) | **4 531** (3 423 de 0→1, 1 108 de k→k+1) |

Reforço de que o rótulo "KOL" no nascimento é marcador de bot: entre as moedas **sem nenhuma rede social** 64 % têm KOL nos boards; entre as com X, 15 %.

### 1.2 Controle

Para cada aparição, uma moeda **sem KOL em toda a vida nos boards** (≥ 2 linhas de board, criada na janela; pool de 8 000 sorteadas por `md5(mint)`), com foto na **mesma idade** (±90 s) e **mcap dentro de ±25 %** do mcap do caso no instante do sinal; sem reposição. Casadas 2 103 de 3 699 (as de mcap alto/idade grande ficam sem par — o pool sem KOL é de moedas pequenas).

## 2. Lead/lag — o KOL chega com o pico

Série de 15 s (fotos), n = 3 699 aparições com foto até 90 s antes/30 s depois do sinal:

| medida | p10 | p25 | p50 | p75 | p90 | leitura |
|---|---|---|---|---|---|---|
| idade no sinal (s) | 24 | 45 | **64** | 123 | 737 | 75 % das aparições estão no 2.º minuto de vida |
| incerteza `t_kol − t_prev` (s) | 14 | 30 | **55** | 61 | 76 | o bucket de minuto é a resolução |
| pico − `t_kol` (s) | −58 | −40 | **−9** | +45 | +242 | pico ≤ sinal em **59 %**; antes até do limite inferior em só 12 % → pico e KOL no **mesmo minuto** |
| bum (+50 %/60 s) − `t_kol` (s), só onde há bum (37 %) | −108 | −20 | **+16** | +51 | +115 | 65 % dos bums começam depois do que vemos; **40 % > 30 s depois** |
| bum − `t_prev` (limite otimista) | −44 | +30 | +66 | +102 | +166 | 75 % > 30 s depois do limite inferior |
| crash (−50 % do pico) − `t_kol`, onde visto (42 %) | −38 | −17 | **+17** | +93 | +237 | metade dos crashes vistos acontece em < 20 s do sinal |
| mcap no sinal / pico anterior | 0,52 | 0,61 | 0,90 | 1,00 | 1,00 | **41 %** das moedas já caíram ≥ 20 % do pico quando o KOL aparece |

Boards (1 min, n = 4 531): pico − `t_kol` p50 = 0 s; pico ≤ sinal 68 %; pico > 60 s depois em **24 %**. Controle sem KOL: bum em 11 % (vs 37 %), pico ≤ sinal 69 %.

Por idade no sinal (série de 15 s):

| idade | n | bum presente | dos bums, > 30 s depois de `t_kol` | pico ≤ sinal | já −20 % do pico | crash visto |
|---|---|---|---|---|---|---|
| < 2 min | 3 384 | 37 % | 51 % | 61 % | 41 % | 50 % |
| 2–5 min | 453 | 66 % | **8 %** (87 % dos bums já começaram) | 46 % | 40 % | 39 % |
| 5–30 min | 392 | 28 % | 3 % | 47 % | 29 % | 11 % |
| ≥ 30 min | 302 | 3 % (série quase não cobre) | — | — | — | — |

Leitura: na moeda de < 2 min o KOL é o próprio bundle/sniper-com-crachá e o bum é o do lançamento; na moeda de 2–5 min o KOL entra **depois** de o bum ter começado (87 %) — ele é seguidor, não gatilho. Em nenhuma faixa o sinal aparece antes de um bum que ainda não começou com frequência que permita "comprar antes da onda".

## 3. Desfecho depois da aparição e R em papel

Razões mcap(t)/mcap(sinal), série de 15 s (r1, r5, rmax) e boards (r15, r60):

| célula | n | r1 p50 | r5 p50 (≤0,5×) | r15 p50 (≥2× / ≤0,5×) | r60 p50 (≤0,5×) | rmax ≥ 2× | graduou |
|---|---|---|---|---|---|---|---|
| todas | 4 531 | 0,99 | 0,94 (25 %) | 0,96 (14 % / 33 %) | 0,46 (51 %) | 16 % | 19 % |
| 0 → ≥1 | 3 423 | 1,00 | 0,98 (23 %) | 0,99 (12 % / 32 %) | 0,48 (51 %) | 15 % | 16 % |
| k → k+1 | 1 108 | 0,91 | 0,73 (32 %) | 0,84 (18 % / 33 %) | 0,43 (52 %) | 20 % | 25 % |
| controle sem KOL | 2 103 | 1,00 | 0,95 (16 %) | — (n 59) | — | 3 % | 2 % |

A moeda com KOL é mais **viva** (mais variância nos dois sentidos: rmax ≥ 2× 16 % vs 3 %; r5 ≤ 0,5× 25 % vs 16 %), mas a mediana anda de lado ou cai, e em 1 h metade perdeu mais da metade.

R em papel (entrada na 1.ª foto ≥ `t_kol` + 20 s; 1,25 %/perna, 3 % slippage/lado, trailing 20 % ou 5 min; `censored` = fechado na última foto):

| célula | n | R médio | mediana | acerto | p90 | maior | top-3 do bruto | saídas (trail / tempo / censurada) |
|---|---|---|---|---|---|---|---|---|
| **todas** | 3 486 | **−0,071** | −0,093 | 15 % | +0,17 | +39,6 | 18 % | 1 660 / 559 / 1 267 |
| controle sem KOL | 1 982 | −0,114 | −0,082 | 5 % | −0,08 | +11,8 | 36 % | 384 / 432 / 1 166 |
| 0 → ≥1 | 2 670 | −0,057 | −0,082 | 13 % | +0,15 | +39,6 | 23 % | |
| k → k+1 | 816 | −0,116 | −0,238 | 18 % | +0,28 | +7,9 | 16 % | |
| kol ≥ 3 depois do salto | 501 | −0,103 | −0,242 | 18 % | +0,29 | +7,9 | 24 % | |
| idade < 2 min | 3 082 | −0,075 | −0,087 | 12 % | +0,11 | +39,6 | 21 % | |
| idade 2–5 min | 322 | **−0,019** [IC95 −0,073, +0,036] | −0,190 | 30 % | +0,68 | +2,6 | 13 % | 194 / 52 / 76 |
| idade 5–30 min | 75 | −0,094 [−0,181, −0,001] | −0,139 | 35 % | +0,34 | +1,6 | 40 % | |
| idade ≥ 30 min | 7 | −0,121 | | 0 % | | | | série não cobre |
| aparição em `graduating/movers/graduated` | 1 140 | −0,066 | −0,212 | 23 % | +0,43 | +7,9 | 11 % | |
| aparição em `new` | 2 346 | −0,073 | −0,082 | 11 % | +0,03 | +39,6 | 29 % | |
| holders no sinal < 10 | 1 858 | −0,060 | | 8 % | | | | graduou 1 % |
| holders 30–100 | 927 | −0,083 | | 23 % | | | | graduou 16 % |
| holders ≥ 100 | 354 | −0,062 | | 25 % | | | | graduou 66 % |
| mcap no sinal 100–300 SOL | 644 | −0,084 | | 23 % | | | | bum 76 %, graduou 31 % |
| X = perfil | 301 | −0,046 | | 17 % | | | | graduou 56 % |
| X = post | 1 558 | −0,075 | | 19 % | | | | graduou 18 % |

**Nenhuma célula executável é positiva.** A melhor (2–5 min) tem IC que cruza zero e mediana −0,19: acerto 30 % com poucos ganhos grandes.

### 3.1 Os dois limites — quanto vale a latência

O KOL negociou em `[t_prev, t_kol]`. Três entradas: `R` (no que vemos, `t_kol` + 20 s), `R_mid` (meio do intervalo + 20 s — proxy honesto de ler o patch a 1 s) e `R_opt` (`t_prev` + 20 s — **limite superior contaminado por look-ahead**: pode entrar antes de o KOL ter negociado; serve só como teto).

| célula | n | R | R_mid | R_opt |
|---|---|---|---|---|
| todas | 3 486–3 590 | −0,071 (15 %) | −0,094 (17 %) | −0,078 (21 %) |
| idade < 2 min | 3 082–3 109 | −0,075 | −0,119 | −0,114 |
| idade 2–5 min | 322–370 | −0,019 | +0,033 [−0,023, +0,092] (36 %) | +0,122 [+0,054, +0,191] (45 %) |
| idade 5–30 min | 75–104 | −0,094 | +0,284 [+0,024, +0,645] (44 %; sem top-3 **+0,058**; top-3 = 50 % do bruto) | +0,293 |
| **idade 2–30 min** | 397–474 | −0,033 [−0,080, +0,017] | **+0,081 [+0,011, +0,163]**, acerto 38 %, sem top-3 +0,037 | +0,159 [+0,088, +0,240] |
| 2–30 min e ainda no pico anterior (≥ 0,95) | 160–192 | −0,063 | +0,146 [+0,008, +0,322], sem top-3 +0,040 | +0,363, acerto 54 % |
| 2–30 min e holders ≥ 30 | 321–376 | −0,036 | +0,100 [+0,014, +0,204], sem top-3 +0,045 | +0,209 |
| 2–30 min por dia (`R_mid`) | 16/09 n 111; 17/09 168; 18/09 143; 19/09 23 | | +0,203 (sem top-3 +0,033); +0,051; +0,039; −0,026 | |

Leitura: na moeda de < 2 min latência não muda nada (os três limites são negativos — o KOL é o bloco). Entre 2 e 30 min, ler o patch a 1 s em vez do minuto fechado moveria a estimativa de −0,03 para ≈ +0,08 (proxy), com cauda concentrada e dia a dia instável. É a **única** porta que esta pesquisa abre, e é estreita: ~450 aparições em 72 h (≈ 150/dia) e a metade do ganho está em 3 moedas.

## 4. `meme_event_matches` — notícia → moeda: sem informação nesta janela

```sql
SELECT match_kind, percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM x.matched_at - t.created_at)),
       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM t.created_at - e.observed_at))
FROM meme_event_matches x JOIN meme_tokens t USING (mint) JOIN meme_events e ON e.id = x.event_id
WHERE x.matched_at > now() - interval '72 hours' GROUP BY 1;
```

| medida | valor |
|---|---|
| eventos com casamento na janela | 22 registrados (todos 16–17/09; o último às 14:00 UTC de 17/09 — nada nas 39 h seguintes) |
| mints casados | 2 998 (`buy` 2 968, `avoid` 30); o evento **UsePaid/`PAID`** sozinho casou 1 252, `ARC` 396, `STOCKS` 376, `GROK` 306, `SEC` 292 — casamento por ticker/keyword no nome |
| `created_at − event.observed_at` | p10 1 h, p25 8 h, **p50 19 h**, p75 34 h, p90 46 h — são **clones tardios de nome**, não a moeda da notícia |
| `matched_at − created_at` | p10 8 s, p50 41 s, p75 15 min, p90 6,6 h (cursor do job) |
| pico ≤ `matched_at` (15 s) | 69 % |
| bum (+50 %/60 s) | 7 % (controle 11 %); quando há, começa 60 s depois do casamento (p50) |
| r1 / r5 p50 | 1,00 / 1,00; rmax ≥ 2× 6 %; r15 (boards, n 97) ≤ 0,5× em 58 % |
| **R papel** (`buy`) | n 2 041, **−0,090**, acerto **5 %**, p90 −0,08 — idêntico ao controle sem sinal nenhum |
| graduou | 5–6 % (`avoid`: 30 clones WOTF no board `graduated`) |
| tem KOL nos boards | 20 % |

Conclusão: o casamento evento→moeda, como está (janela de 72 h por ticker/keyword), marca **clones** horas depois — vale como *aviso* (`avoid`), não como gatilho. O que a EXP-M8 quer medir (a moeda que nasce **minutos** depois da notícia) não aconteceu nas 72 h: nenhum evento novo foi registrado e os casamentos ≤ 1 h do evento são 10 % (p10) sem sinal de R.

## 5. Identidade social no nascimento — muda a probabilidade, não o timing

Moedas criadas de 72 h a 2 h atrás com `social_observed_at` (n = 87 593; 13 % das sem social não tiveram a leitura feita e ficaram fora). Bum = pico da série de 15 s nos primeiros 30 min ≥ 60 SOL (≈ 2× o mcap de nascimento); rug = pico ≥ 60 SOL **e** última foto ≤ 50 % do pico (a série termina em 300 s para a moeda não fixada → é "dump nos primeiros 5 min").

```sql
-- q8.sql: grupos A (identidade), B (twitter_kind), C (reuse), D (website) × pico ≥ 60/100 SOL, rug, graduação, board, KOL
```

| grupo | n | pico ≥ 60 SOL | pico ≥ 100 SOL | rug após 60 | **graduou** | chegou a `graduating/movers` | tem KOL |
|---|---|---|---|---|---|---|---|
| nada | 42 069 | 11,8 % | 4,8 % | 4,8 % | 2,61 % | 3,0 % | 63,8 % |
| só X | 44 028 | 14,1 % | 6,3 % | **9,4 %** | 3,79 % | 19,2 % | 15,0 % |
| **X + Telegram** | 1 331 | 10,8 % | 5,8 % | 4,8 % | **11,19 %** | 18,1 % | 18,7 % |
| só Telegram | 165 | 3,7 % | 1,9 % | 3,1 % | 2,42 % | 6,5 % | 16,8 % |
| X = post | 31 764 | 13,9 % | 6,0 % | 9,5 % | 2,12 % | 19,1 % | 13,2 % |
| **X = perfil** | 11 024 | 14,8 % | 7,4 % | 9,1 % | **9,85 %** | 21,5 % | 19,7 % |
| X = comunidade | 253 | 10,1 % | 2,8 % | 5,6 % | 2,37 % | 10,4 % | 10,0 % |
| X = outro | 2 318 | 11,9 % | 4,9 % | 7,4 % | 2,24 % | 10,4 % | 20,9 % |
| website sim / não | 30 002 / 57 591 | 16,2 / 11,3 % | 7,5 / 4,6 % | 10,8 / 5,2 % | 5,65 / 2,13 % | 22,2 / 5,7 % | 16,0 / 50,3 % |
| `twitter_reuse_count` | conhecido só em 2 085 (todas 0) | — | — | — | 25,7 % | 99 % | — |

- **Graduação:** perfil no X 9,9 % vs post 2,1 % (×4,7); X + Telegram 11,2 % vs nada 2,6 % (×4,3); website ×2,7. É o mesmo sinal lento do M-P17/KB-0100: identidade seleciona a moeda que **dura**.
- **Bum de curto prazo:** quase igual entre grupos (11–15 %) e o pump-and-dump nos primeiros 5 min é **maior** com X (9,4 % vs 4,8 %) — o X é a ferramenta do call, e o call vende.
- `twitter_reuse_count` só é lido para moeda com aposta aberta ou no board `graduating` (T4.26) → amostra selecionada (99 % chegaram a board, 26 % graduaram) e sempre 0: **inutilizável** para esta pergunta.
- O 64 % "tem KOL" nas moedas sem social confirma a seção 1.1: o crachá KOL no bloco é bot.

## 6. Ressalvas de cobertura (honestas)

1. **Resolução do sinal:** `kol_count` é gravado por minuto fechado; o KOL negociou em `[t_prev, t_kol]` (p50 55 s). Todo lead/lag desta nota tem essa barra de erro; o pico "no mesmo minuto" pode ser tanto 30 s antes quanto 30 s depois do trade do KOL. O worker **recebe os patches a 1 s** (`boards.py::ingest`) e só persiste o último do minuto — a resolução é nossa, não da fonte.
2. **Série fina só até 5 min:** fotos a ~13 s entre 2 e 5 min de idade; depois de 10 min só as moedas fixadas/top-K. Por isso as células "5–30 min" e "≥ 30 min" têm n pequeno na série de 15 s (75 e 7) e a leitura de 15/60 min vem dos boards (1 min, só enquanto a moeda está listada: cobertura mediana depois do sinal = 94 s no `new`).
3. **Boards cobrem o que o site mostra:** `new` lista quase toda criação por 1–2 min (114 k mints); `graduating`/`movers`/`graduated` só as que chegam lá (5 k / 15,6 k / 2,8 k). Uma moeda que ganha KOL fora de board (entre sair do `new` e entrar no `movers`) não aparece — o "primeiro incremento" pode ser tardio nessas.
4. **Censura de saída:** 36 % das apostas de papel fecham na última foto (série acabou antes dos 5 min). A regra "trailing 20 % ou 5 min" é avaliada como o motor a executaria; o valor final da posição censurada é o da última foto (viés desconhecido nos dois sentidos).
5. **Custos do enunciado** (1,25 %/perna, 3 %/lado), sem prioridade nem impacto próprio; o Lab usa 1,75 %/perna. Só quote SOL (as fotos de curva são do programa pump).
6. **Controle** casado em idade e mcap, não em holders/fluxo; as aparições de mcap alto ficaram sem par (1 596 de 3 699).
7. **72 h de uma semana** (16–19/09, quarta a sexta de madrugada BRT no fim). Sem regime de bull de memes na janela.
8. `R_opt` **não é alcançável** (look-ahead por construção); `R_mid` é um proxy, não uma medição.

## 7. Conclusão e o que o T4.68 teria de entregar

**Há sinal de "call" acionável antes da onda (lead > 30 s com R positivo)?** Com os dados que gravamos, **não**: o `kol_count` confirma (pico no mesmo minuto, R ≤ 0 em toda célula executável) e o `meme_event_matches` marca clones (R = controle). O que existe é (a) um sinal **lento** de identidade (perfil no X, X + Telegram, website → ×3–5 na graduação) que já está no `IdentityFeatures` e serve para **escolher** a moeda, não para **entrar**; e (b) uma **porta estreita** entre 2 e 30 min de idade que só abre lendo o KOL no patch de 1 s (`R_mid` +0,08 [+0,01, +0,16], n 445, cauda concentrada).

Passos que esta nota sustenta:

1. **T4.68a (barato, sem fonte nova):** no `boards.py`, ao ingerir um patch com `kol` maior que o espelho, emitir um evento em memória `kol_seen{mint, kol_before, kol_after, board, server_ts, received_at}` para o portão de evento (mesmo desenho de `event_gate_rows.build_event_row`) e persistir `kol_first_seen_at` em `meme_tokens` (coluna write-once). Custo: uma migração de uma coluna; ganho: a barra de erro cai de 55 s para ~1–3 s e a EXP-M20 fica mensurável de verdade.
2. **EXP-M20 (pré-registro, `research_only`):** braço `kol_v0/1` — compra só quando `kol_seen` chega com idade 120–1 800 s, mcap ≥ 0,95 do pico anterior, holders ≥ 30; saídas trailing 20 % / 300 s; previsão honesta **inconclusivo → descartar** (R_mid sem top-3 = +0,04; um dia em quatro negativo). Controle: `flow_v2/6` no mesmo minuto e as mesmas moedas sem o gatilho.
3. **T4.68 — feed de canais de call (Telegram/X): a especificação** que os números pedem, se um dia for feito:

| campo | por quê |
|---|---|
| `posted_at` do servidor da plataforma (ms) **e** `received_at` nosso | a latência post → nós tem de ser medida por mensagem; o sinal só interessa com `received_at − posted_at` ≤ 5 s (o bum de 2–5 min começa 16 s depois do que vemos hoje com 55 s de erro) |
| `channel_id`, `author_handle`, `followers`/`members` no instante | Everton: "com muitos seguidores explode rápido" — sem o tamanho não dá para separar caller de ruído |
| `mint` extraído (CA) **ou** `ticker` + `name` + `url` do pump.fun | 1 252 casamentos por ticker `PAID` mostram que ticker sozinho casa clone; CA é obrigatório para casar sem ambiguidade |
| `is_first_mention` (por canal e global) e `mention_rank` | o segundo call já é a onda; só o primeiro pode anteceder |
| `text` cru e `media` (sim/não) | para a classificação `buy`/`avoid`/`shill pago` depois |
| histórico por `author_handle`: acerto e R das chamadas anteriores (calculado por nós) | ponderar o caller; sem isso é o mesmo que o crachá KOL do site |
| latência-alvo do ingest | p50 ≤ 3 s, p95 ≤ 10 s do `posted_at`; acima de 30 s o feed é o `kol_count` de novo |
| volume esperado | dezenas de canais × centenas de posts/dia; **um** evento por (canal, mint) — dedupe por CA |
| gate de ativação | só depois de 3 dias de coleta **sem** apostar, medindo o mesmo lead/lag desta nota (pico − `posted_at`) com a série de 15 s; a régua é a mesma: **lead > 30 s em ≥ 50 % dos bums e `R` > 0 com IC fora de zero** |

Sem esse feed, o que temos de "call" é o trade do KOL — e ele chega junto com o pico.

## Relacionados

KB-0142 (esta nota) · KB-0141 (sniper de lançamento: o bloco é do bundle) · KB-0138 (explosão de compradores) · KB-0136 (carteiras vencedoras) · KB-0100 (eventos sem casamento) · EXP-M8 (evento) · EXP-M19 (subida com gente atrás) · `docs/DATABASE.md` §35 (boards), §52 (identidade/eventos)
