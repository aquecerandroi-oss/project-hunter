---
tags: [knowledge, nota, meme, pumpfun, celula-lenta, porta, cadencia, R, executor, m5]
tema: memecoin / pump.fun / a "célula lenta" (30 SOL reais com ≥ 3 min de vida) serve de porta para a mesa do estágio 1? cadência, R simulado e a admissão do executor
fonte: banco da VPS (meme_tokens, meme_curve_snapshots, meme_features_1m), 12–16/09/2026 (dias BRT)
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r16-q01-porta-celula-lenta-r.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-r16-q0{1,2,3}-*.sql; 807 lentas em 5 dias, 591 entradas simuladas na variante sem teto de progresso)
hipotese_testavel: sim
astra: não consultada nesta nota (medição quant, 16/09 ~21h BRT)
confianca: backtest do autor (3 dias cheios + 2 parciais)
owner: astra-quant
updated: 2026-09-16
status: vivo
---

# KB-0107 — A célula lenta como porta da mesa: cadência e R simulado (12–16/09)

**A pergunta.** A [[11-KNOWLEDGE/KB-0104-taxas-base-sem-as-nascidas-cheias|KB-0104]] mostrou que a **célula lenta** — a moeda
que alcança **30 SOL reais** na curva **≥ 3 min depois da criação** — é o único número da
[[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] que saiu intacto da errata das nascidas
cheias: ~613 moedas/dia e **19,6 % de graduação orgânica, 23,6× a taxa-base**. Ela dá **cadência e R** para a mesa do estágio 1,
ou só uma taxa de graduação bonita?

## 0. A porta L (escrita antes de olhar o R)

Entrada = a **primeira barra de 1 min** (`meme_features_1m`) em que valem, cumulativamente:
`real_sol_reserves ≥ 30` (foto de curva, `meme_curve_snapshots`) · `idade ≥ 180 s` · `curve_progress_pct ≤ 0,50`
(**fração 0–1**, KB-0099 §4) · fita presente (`tape_reason IS NULL`) · `net_sol_flow_1m > 0` · curva viva ·
**não-Mayhem** (`mayhem_enabled = false` **e** `mayhem_mode IS NULL`) · **não nascida cheia** (KB-0104, perna D:
`completed_at − created_at ≤ 60 s`). Variantes: **L1** só isso; **L2** + `holders ≥ 20`; **L3** + `snipers` 21–60
([[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]], a corcova); **L4** + `top10_share ≤ 0,30`.
A entrada só é procurada até **30 min** depois do cruzamento dos 30 SOL (sem isso, "a primeira barra que passa" cairia horas
depois; o atraso medido é mediano de **37 s**, p90 417 s).

**Saída = a metodologia do KB-0099 §3 / `r4-q05`, sem mudar nada:** barras de 1 min, alvo **3×**, trailing **35 %** armado
depois de 1,5×, piso **−50 %**, tempo **30 min**, taxa **1,75 % por perna**, stop preenchido no mcap **observado** da barra.
`R = (múltiplo líquido − 1) / 0,5`. IC 95 % por **bootstrap** (10 mil reamostragens; por dia, dentro do dia; no total,
por **blocos de dia**).

## 1. Quantas lentas há por dia (universo da porta)

| Dia BRT | Lentas (30 SOL reais, idade ≥ 180 s, não-Mayhem, não nascidas cheias) | com barra de 1 min |
|---|---|---|
| 12/09 (parcial) | 75 | 74 |
| 13/09 | 132 | 131 |
| 14/09 | 178 | 174 |
| 15/09 | 292 | 278 |
| 16/09 (parcial) | 130 | 127 |

Bate com a KB-0098 §6 (136/183/273 em 13–15/09) dentro da diferença de rótulo (aqui o dia é o do **cruzamento**, e as
nascidas cheias saem). **A cobertura de série de 1 min da célula lenta é quase total (98 %)** — ao contrário das graduadas,
que a KB-0104 mostrou serem invisíveis na série de 15 s.

## 2. O choque de unidades que define esta nota: 30 SOL reais **não** é "5–50 % de curva"

`curve_progress_pct` é fração de **tokens vendidos**; `real_sol_reserves` é **SOL levantado**. A curva liga os dois de forma
côncava, então quando a moeda tem 30 SOL reais ela já está **bem acima** da janela da mesa (medido nas fotos de curva de 6 h):

| SOL reais na foto | 0–10 | 10–20 | 20–30 | **30–40** | 40–50 | 50–60 | 60–70 | 70–80 | 80–85 |
|---|---|---|---|---|---|---|---|---|---|
| progresso mediano | 0,21 | 0,56 | 0,69 | **0,78** | 0,84 | 0,90 | 0,94 | 0,97 | 1,00 |

Na barra de entrada da porta L o progresso tem **mediana 0,71** (p10 0,63; p90 0,83) e **só 3 %** das entradas ficam ≤ 0,50.
O funil confirma (Q02, moedas que têm ao menos uma barra passando cada perna, acumulado):

| Dia | com barra | **prog ≤ 0,50** | + fita | + fluxo > 0 | + holders ≥ 20 | + snipers 21–60 | + top-10 ≤ 30 % | *(sem o teto)* + fita | + fluxo | + holders |
|---|---|---|---|---|---|---|---|---|---|---|
| 13/09 | 131 | **26** | 26 | 11 | 8 | 4 | 10 | 130 | 118 | 110 |
| 14/09 | 174 | **32** | 32 | 8 | 5 | 4 | 7 | 168 | 150 | 141 |
| 15/09 | 278 | **22** | 22 | 11 | 9 | 5 | 7 | 268 | 228 | 215 |
| 16/09 (p) | 127 | **21** | 21 | 5 | 3 | 2 | 4 | 124 | 111 | 102 |

**O teto de progresso de 50 % mata 85–92 % da célula lenta sozinho** — e ele não é um parâmetro de conjunto: é
`curve_progress_max_pct = Decimal("0.50")` no `MEME_PAPER_V0` (`packages/risk-core/hunter_risk_meme/limits.py`), recusa
`progress_above_window`. Por isso esta nota mede **duas famílias**: a porta L como encomendada (§3) e a mesma porta **sem o
teto de progresso** (§4, sufixo ′).

## 3. Porta L como encomendada (com `progresso ≤ 0,50`) — R alto, cadência quase nula

| Dia (L1) | n dispara | com R | cad/h 13–22 BRT | R médio | R mediano | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % (dia) |
|---|---|---|---|---|---|---|---|---|---|
| 12/09 (p) | 4 | 3 | 0,4 | +2,866 | +3,792 | +8,60 | 66,7 % | 0 % | [+1,01; +3,79] |
| 13/09 | 11 | 10 | 0,7 | +0,100 | −0,091 | +1,00 | 10,0 % | 30,0 % | [−0,50; +1,00] |
| 14/09 | 8 | 5 | 0,2 | +0,499 | −0,302 | +2,50 | 20,0 % | 20,0 % | [−0,43; +2,15] |
| 15/09 | 11 | 5 | 0,6 | +3,123 | +3,792 | +15,62 | 80,0 % | 0 % | [+2,37; +3,79] |
| 16/09 (p) | 5 | 5 | 0,0 | −0,210 | −0,197 | −1,05 | 0 % | 40,0 % | [−0,62; +0,25] |
| **5 dias** | **39** | 28 | **0,4** | **+0,952** | −0,025 | +26,66 | 28,6 % | 21,4 % | blocos [+0,07; +2,42] |

| Variante (5 d) | n | n/dia | R médio | R mediano | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % (blocos de dia) |
|---|---|---|---|---|---|---|---|---|
| L1 | 39 | 7,8 | +0,952 | −0,025 | +26,66 | 28,6 % | 21,4 % | [+0,07; +2,42] |
| L2 (holders ≥ 20) | 28 | 5,6 | +0,972 | +0,028 | +19,44 | 30,0 % | 25,0 % | [−0,20; +2,36] |
| L3 (snipers 21–60) | 16 | 3,2 | +0,975 | −0,025 | +11,70 | 25,0 % | 8,3 % | [−0,24; +2,62] |
| L4 (top-10 ≤ 30 %) | 31 | 6,2 | +0,884 | −0,060 | +20,33 | 26,1 % | 17,4 % | [+0,19; +2,39] |

**Como ler:** ~8 disparos/dia (**0,4/hora** em 13–22 BRT) e um R médio de **+0,95** que é **toda cauda** — 7 das 28 apostas
medidas saíram no alvo 3× (+3,79 R cada = +26,5 R) e as outras 21 somam **+0,2 R**. Com mediana ≈ 0 e IC de blocos que quase
toca o zero em três das quatro variantes, **este braço não é uma mesa: é um bilhete de loteria com n = 28 em 5 dias.**

## 4. Porta L sem o teto de progresso (L′) — é aqui que existe mesa

| Dia (L1′) | n | com R | cad/h 13–22 | R médio | R mediano | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % (dia) |
|---|---|---|---|---|---|---|---|---|---|
| 12/09 (p) | 39 | 34 | 3,8 | +0,343 | −0,051 | +11,66 | 8,8 % | 23,5 % | [−0,02; +0,77] |
| 13/09 | 108 | 97 | 5,9 | +0,231 | +0,113 | +22,44 | 10,3 % | 28,9 % | [−0,03; +0,51] |
| 14/09 | 139 | 122 | 7,4 | +0,455 | +0,165 | +55,46 | 13,9 % | 23,8 % | [+0,20; +0,71] |
| 15/09 | 205 | 182 | 11,7 | +0,471 | +0,157 | +85,67 | 12,6 % | 20,9 % | [+0,29; +0,66] |
| 16/09 (p) | 102 | 91 | 2,5 | +0,254 | +0,003 | +23,10 | 11,0 % | 23,1 % | [−0,01; +0,53] |
| **5 dias** | **593** | 526 | **6,2** | **+0,377** | **+0,111** | **+198,33** | 12,0 % | 23,6 % | blocos **[+0,25; +0,46]** |

| Variante′ (5 d) | n | n/dia | cad/h 13–22 | R médio | R mediano | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % (blocos) |
|---|---|---|---|---|---|---|---|---|---|
| **L1′** (base) | 591 | 118 | 6,2 | **+0,377** | +0,111 | +198,3 | 12,0 % | 23,6 % | **[+0,25; +0,46]** |
| **L2′** (+ holders ≥ 20) | 550 | 110 | 5,8 | +0,349 | +0,046 | +170,6 | 11,5 % | 22,9 % | **[+0,26; +0,41]** |
| **L3′** (+ snipers 21–60) | 191 | 38 | 1,7 | **+0,446** | +0,127 | +77,1 | 13,9 % | 24,9 % | **[+0,26; +0,65]** |
| L4′ (+ top-10 ≤ 30 %) | 492 | 98 | 5,1 | +0,372 | +0,045 | +163,1 | 12,1 % | 22,8 % | [+0,27; +0,44] |

**Três leituras honestas:** (i) a **mediana é positiva** (+0,11 em L1′), coisa que nenhuma porta do KB-0099/KB-0102
conseguiu — lá a mediana era −0,31 e **toda** a vantagem vinha de 16 caudas; aqui 27 alvos 3× de 526 apostas explicam
+102 R dos +198 R, ou seja **metade** do resultado vem do corpo; (ii) os três filtros extras **não** melhoram o R médio de
forma separável do ruído — o único que muda algo é o piso de snipers (L3′, +0,45), coerente com a corcova 31–60 da KB-0102,
ao custo de 3,5× menos cadência; (iii) o dia manda: 15/09 dá 11,7/h e +0,47, 16/09 dá 2,5/h e +0,25 — a mesma variância
entre dias que a KB-0099 §3 já tinha avisado.

## 5. A admissão do executor (idade ≤ 600 s) — o teto **não** é o problema

| Variante′ | entradas | **180–600 s** | 600–1 800 s | > 1 800 s | idade mediana | cad/h 13–22 **admissível** | R ≤ 600 s (IC 95 %) | R > 600 s (IC 95 %) |
|---|---|---|---|---|---|---|---|---|
| L1′ | 591 | **362 (61 %)** | 139 | 90 | 433 s | **3,6** | **+0,465** [+0,31; +0,62] | +0,220 [+0,08; +0,37] |
| L2′ | 550 | 323 (59 %) | 141 | 86 | 465 s | 3,2 | +0,429 [+0,27; +0,59] | +0,220 [+0,08; +0,37] |
| L3′ | 191 | **129 (68 %)** | 44 | 18 | 396 s | 1,2 | **+0,504** [+0,24; +0,79] | +0,301 [−0,01; +0,64] |
| L4′ | 492 | 304 (62 %) | 120 | 68 | 433 s | 3,0 | +0,460 [+0,30; +0,63] | +0,214 [+0,07; +0,37] |

(Na porta com teto de progresso, 74–81 % das entradas já nascem dentro dos 600 s.) **O corte de `token_too_old` custa ~39 %
das entradas e não custa R nenhum: o que ele joga fora rende metade** (+0,22 contra +0,47). Cadência admissível na janela útil:
**3,6/hora** (L1′), 3,2 (L2′), 1,2 (L3′). Por dia, L1′ admissível dá 1,9 / 4,0 / 4,9 / 6,0 / 1,0 por hora em 12→16/09.

## 6. Comparação com a porta calibrada do KB-0099

| | KB-0099 §3 (porta calibrada, 15 s) | **L2′ (célula lenta, 1 min)** |
|---|---|---|
| Cadência 13–22 BRT | **7,1/h** (15/09) · 2/h (16/09) | 5,8/h bruta · **3,2/h** dentro dos 600 s (10,8 e 2,4 nos mesmos dias) |
| R médio | **+0,08 → +0,27** | **+0,35** (IC blocos [+0,26; +0,41]); +0,43 nas admissíveis |
| R mediano | −0,31 a −0,35 | **+0,05** |
| De onde vem | 16 caudas em 169 apostas; sem elas, −0,31/aposta | 22 alvos 3× em 489; o corpo já é ≈ 0 |
| Idade na entrada | 30–300 s | 180–600 s (mediana 465 s) |
| Progresso na entrada | 0,05–0,50 | **0,60–0,85** (fora da janela do risco hoje) |

**Não é comparação limpa:** a KB-0099 entra na foto de 15 s com pedigree (E2) e horizonte de 10 min; esta nota entra na barra
de 1 min, **sem pedigree**, com horizonte de 30 min. As duas diferenças puxam em direções opostas (sem pedigree deveria
**piorar** o R; horizonte maior deveria melhorá-lo pouco, ver §7). O que sobrevive à ressalva é a forma: **a lenta ganha no
corpo, a rápida ganha só na cauda.**

## 7. Limites declarados (nada aqui está resolvido)

- **A cobertura da simulação de saída é curta.** No horizonte de 30 min há **mediana de 4–5 barras** e só ~4 % das entradas
  têm 25+ barras (Q03). A saída `tempo` (375 de 526 em L1′) marca a **última barra observada**, tipicamente ~5 min depois da
  entrada — **o R desta nota é uma marcação de ~5 min, não de 30 min**, e por isso corta tanto a cauda quanto a ruína.
- **~20 % das entradas graduam dentro do horizonte** (21/108, 26/139, 32/205) e a série de curva acaba ali; o que a moeda fez
  na pool depois **não** está neste R (é o buraco que a T4.11/EXP-M4 cobre).
- 11–17 % das entradas não têm **nenhuma** barra futura e ficam sem R (contadas em "n dispara", fora do R).
- Sem pedigree/E2, sem TTL, sem dedup, sem cooldown, sem atraso de decisão ([[11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]]),
  sem slippage/impacto além da taxa ([[11-KNOWLEDGE/KB-0088-o-teto-de-participacao-nos-motores-de-backtest|KB-0088]]) — e comprar a 70 % de
  curva com 0,05 SOL está **dentro** do teto de participação do [[03-TRADING/Meme/Estudo-2026-09-16-tamanho-estagio-2|Estudo T4.29b]], mas 0,25 SOL não estaria.
- `at_30` vem da foto de curva (60 req/min para o universo inteiro): é **quando o radar viu** 30 SOL, não o slot on-chain.
- **3 dias cheios e 2 parciais.** Mesma régua de sempre: sem replicação prospectiva, é anedota com n grande.
- Em dinheiro: 32 apostas/dia (L2′ admissível) × 0,05 SOL × 0,43 R × 0,5 ≈ **0,34 SOL/dia** — 2,4× o dia bom da KB-0099 e
  ainda **duas ordens de grandeza** abaixo da [[11-KNOWLEDGE/KB-0090-a-meta-em-dinheiro|meta de R$ 9 mil/dia]].

## 8. Recomendação (4 linhas)

1. **Sim, vale um `operator/6`** — mas como **braço de papel pré-registrado `descartar`**, não como substituto do `operator/5`:
   a lenta entrega **3,2 propostas/hora admissíveis** em 13–22 BRT com **+0,35 R** (IC de blocos [+0,26; +0,41]) e **mediana
   positiva**, contra +0,08/+0,27 com mediana −0,31 da porta calibrada.
2. **Variante: L2′** (30 SOL reais + idade ≥ 180 s + fita + fluxo > 0 + `holders ≥ 20` + não-Mayhem + não nascida cheia,
   **sem teto de progresso**), com **L3′** (piso de snipers 21–60) como braço irmão para quem aceita 1,2/hora por +0,10 R.
3. **O teto de 600 s do executor NÃO precisa subir**: ele custa 39 % das entradas e o que ele corta rende metade (+0,22 × +0,47).
   O que bloqueia a célula lenta é **`curve_progress_max_pct = 0,50`** no `MEME_PAPER_V0` — 30 SOL reais são ~0,71 de curva, e
   **97 % da célula lenta é recusada por `progress_above_window` antes de qualquer outra coisa**.
4. **Condição para ligar:** subir o teto de progresso é mexer no motor de risco, então só com (a) a mesa/Everton de acordo,
   (b) o braço nascendo com `curve_progress_max_pct` próprio (0,90) e tamanho 0,05 SOL, e (c) **repetir esta medida com a
   saída marcada na pool** — o R de §4 é uma marcação de ~5 min e 20 % das entradas graduam dentro dela.

## Ligações
[[11-KNOWLEDGE/KB-0104-taxas-base-sem-as-nascidas-cheias|KB-0104]] · [[11-KNOWLEDGE/KB-0098-quantos-bums-reais-ha-por-dia-e-quanto-tempo-temos|KB-0098]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] · [[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] ·
[[05-EXPERIMENTS/EXP-M7-organica-lenta]] · [[03-TRADING/Meme/Estudo-2026-09-16-tamanho-estagio-2|Estudo T4.29b]] ·
`infra/scripts/sql/research/2026-09-16-r16-q0{1,2,3}-*.sql` · `packages/risk-core/hunter_risk_meme/limits.py`
