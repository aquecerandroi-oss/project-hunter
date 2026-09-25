---
tags: [knowledge, nota, meme, pumpfun, porta, participacao, execucao, volume, liquidez, m5]
tema: memecoin / pump.fun / o volume do minuto na entrada separa R? participação como risco de execução x como seleção
fonte: banco da VPS (meme_features_15s, meme_features_1m, meme_tokens), 12–16/09/2026 BRT
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r24-q01-volume-do-minuto-por-moeda-e-r.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-r24-q0{1,2,3}-*.sql; 344 entradas da porta atual em 5 dias, 3 cheios)
hipotese_testavel: sim
astra: não consultada nesta nota (pesquisa quant, 16/09 noite BRT)
confiança: backtest do autor
owner: astra-quant
updated: 2026-09-16
status: vivo
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0112 — O volume do minuto, a participação e o R

**A pergunta que abriu a nota (16/09):** no funil do R21
([[03-TRADING/Meme/Estudo-2026-09-16-por-que-a-mesa-calibrada-nao-propos|Estudo de hoje]]) o critério de participação
(`max_participation_pct 1` com 0,05 SOL ⇒ `curve_volume_60s_sol ≥ 5`) cortou **71 → 25 moedas** — mais do que qualquer
outro depois do progresso. O R21 sugeriu "se faltar volume, corte a participação (25 → 10)". **Ninguém tinha medido se o R
vive nas moedas de mais volume.** Esta nota mede, e separa duas coisas que estavam coladas: **risco de execução**
(quanto a nossa ordem move o preço) e **seleção** (o volume prevê retorno?).

## 0. Método (escrito antes de olhar o resultado)

- **Universo = a porta atual da mesa SEM o critério de participação** — reuso literal do `r19-q01`
  ([[11-KNOWLEDGE/KB-0109-top10-e-bundle-onde-o-teto-deveria-estar|KB-0109]]): primeira foto de 15 s com `age_s` 30–300 s,
  curva viva, **não-Mayhem** (`mayhem_enabled` false **e** `mayhem_mode` nulo), `curve_progress_pct` **0,05–0,50**
  (fração 0–1), `tape_reason IS NULL`, `net_sol_flow_60s > 0`, `dev_share ≤ 0,10`, **`snipers ≥ 21`**
  ([[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] §7). **Nenhum filtro de `curve_volume_*`** — é o objeto.
- **Entrada** = primeira barra de 1 min nos 5 min seguintes com `holders ≥ 20`, `unique_buyers ≥ 10`,
  `sells_1m/buys_1m ≤ 0,6`. O volume do minuto é lido **nessa barra**: `curve_volume_1m_sol` — que é **exatamente** o
  `organic_volume_1m_sol` que o executor usa no teto de participação
  (`services/meme-executor/hunter_meme_executor/admission.py:176` → `packages/risk-core/hunter_risk_meme/sizing.py:112`).
- **R simulado**: metodologia literal do [[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]]
  (`r4-q05`/`r8-q01`): alvo 3×, trailing 35 % armado depois de 1,5×, piso −50 %, tempo **30 min**, taxa **1,75 % por
  perna**, stop preenchido no mcap **observado** da barra; `R = (múltiplo líquido − 1)/0,5`.
- **IC 95 % por bootstrap de dias** (blocos, 5 000 réplicas) — a variância entre dias é maior que a entre moedas.
- **Impacto** pela fórmula fechada da T4.29b (`t429b-q02`, reproduzida em `r24-q03`):
  `impacto = SOL pré-taxa / virtual_sol_reserves`, com `vsol = 30·1 073 000 000/(1 073 000 000 − 793 100 000·t)`.
- **n = 344 entradas** (12/09: 11 · 13/09: 69 · 14/09: 109 · 15/09: 133 · 16/09: 22 — 12 e 16/09 são **parciais**).
  Cadência = média dos **3 dias cheios**. R total da coorte: **+65,52 R**; R médio **+0,190**; 15,7 % com ≥ +2 R.

## 1. `curve_volume_1m_sol` na barra de entrada — a variável do executor

| Faixa (SOL/min) | n | /dia | R médio | R mediano | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % (R médio) | impacto de 0,05 SOL |
|---|---|---|---|---|---|---|---|---|---|
| < 2 | 1 | 0,3 | +0,033 | +0,033 | +0,03 | 0 | 0 | — | 0,125 % |
| 2–5 | 12 | 4,0 | +0,228 | +0,048 | +2,74 | 1 (8,3 %) | 3 (25,0 %) | [−0,748; +0,562] | 0,118 % |
| **5–10** | 32 | 9,7 | **−0,371** | −0,296 | **−11,87** | **0 (0,0 %)** | 13 (40,6 %) | **[−0,531; −0,167]** | 0,113 % |
| **10–20** | 108 | 33,7 | **+0,496** | −0,158 | **+53,52** | 23 (21,3 %) | 43 (39,8 %) | **[+0,309; +0,597]** | 0,109 % |
| 20–50 | 156 | 46,0 | +0,077 | −0,575 | +11,99 | 24 (15,4 %) | 83 (53,2 %) | [+0,037; +0,089] | 0,106 % |
| ≥ 50 | 35 | 10,0 | +0,260 | −0,363 | +9,12 | 6 (17,1 %) | 16 (45,7 %) | [−0,210; +0,504] | 0,102 % |
| **todas** | 344 | 103,7 | +0,190 | −0,308 | +65,52 | 54 (15,7 %) | 158 (45,9 %) | [+0,063; +0,253] | 0,107 % |

**Não há escada.** Spearman `vol_1m` × R = **−0,066 (p = 0,23)**; contra o indicador de cauda (R ≥ +2) = **+0,016
(p = 0,76)**. A mediana de volume das **54 apostas de cauda é 20,9 SOL/min** contra **23,1** das outras — indistinguível.
**O volume do minuto não prevê a cauda, que é toda a vantagem desta porta** (KB-0099 §3).

O que existe é **um buraco**: a faixa **5–10 SOL/min** é negativa, tem **zero** caudas em 32 apostas (probabilidade de
0/32 com a taxa base de 15,7 %: **0,42 %**) e é negativa **nos cinco dias** (−0,75 / −0,29 / −0,16 / −0,55 / −0,07).
Não tenho mecanismo para isso além de "volume baixo demais para sustentar um 3×, alto demais para ser uma moeda parada";
com n = 32 e a busca por faixas feita depois de ver os dados, trato como **pista**, não como achado.

## 2. A mesma coorte pela variável da PORTA (`curve_volume_60s_sol`, foto de 15 s)

| Faixa (SOL/60 s) | n | /dia | R médio | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % |
|---|---|---|---|---|---|---|---|
| < 2 | 0 | — | — | — | — | — | — |
| 2–5 | 3 | 1,0 | +0,123 | +0,37 | 0 | 1 | [−1,045; +1,231] |
| 5–10 | 5 | 1,7 | −0,728 | −3,64 | 0 | 4 | [−1,470; −0,433] |
| 10–20 | 59 | 17,7 | +0,287 | +16,91 | 12 (20,3 %) | 27 | [−0,372; +0,568] |
| 20–50 | 152 | 47,0 | +0,255 | +38,68 | 30 (19,7 %) | 76 | [+0,005; +0,466] |
| ≥ 50 | 125 | 36,3 | +0,106 | +13,20 | 12 (9,6 %) | 50 | [−0,028; +0,191] |

**O corte 71 → 25 do R21 não se repete aqui, e o motivo é ordenação.** Naquele funil a participação foi avaliada
**antes** do piso de snipers; nesta coorte o piso `snipers ≥ 21` já entrou, e **só 3 das 344 entradas (0,9 %)** têm
`vol60s < 5`. Participação e snipers são quase colineares: sniper alto ⇒ moeda movimentada ⇒ volume alto. **Depois do
piso de snipers, o critério de participação a 1 % praticamente não seleciona nada.** E a única direção com sinal é
**contrária** à intuição do R21: `vol60s` × cauda dá Spearman **−0,109 (p = 0,041)** — mais volume na foto, **menos** 3×.

## 3. Risco de execução: o impacto de 0,05 SOL nunca morde

`impacto = (0,05/1,0125)/vsol`, com `vsol` derivado do progresso (T4.29b):

| progresso | `vsol` (SOL) | impacto de 0,05 SOL | teto de 0,5 % (`RISK_ENGINE_MEME` §3.1) |
|---|---|---|---|
| 2 % | 30,45 | **0,1622 %** | passa |
| 5 % | 31,15 | 0,1585 % | passa |
| 20 % | 35,20 | 0,1403 % | passa |
| 50 % | 47,59 | 0,1038 % | passa |
| 95 % | 100,73 | 0,0490 % | passa |

Nas 344 entradas reais o impacto ficou entre **0,0488 % e 0,1551 %** — **3,2× a 10× abaixo** do teto de 0,5 %, em
**todas** as faixas de volume, inclusive na de < 2 SOL/min. **Com 0,05 SOL, `impact_above_cap` é impossível na curva**
(o pior caso teórico, `t → 0`, é 0,1645 %). Isto é matemática da curva, não amostra: a reserva virtual de SOL nasce em 30
e só cresce.

**Consequência dura:** a 0,05 SOL, o teto de participação **não é** um limite de risco de execução — o impacto já está
controlado pela própria curva. Ele é, na prática, **um filtro de seleção disfarçado**. Quem morde é só o
`participation_above_cap`:

| teto | `vol_1m` mínimo | entradas recusadas | % | R que seria perdido | R médio das recusadas | R médio das mantidas | Δ R médio (bootstrap de dias) |
|---|---|---|---|---|---|---|---|
| 2 % | 2,5 SOL | 3 | 0,9 % | −1,12 | −0,374 | +0,195 | **+0,005** [+0,000; +0,009] |
| **1 % (hoje)** | 5,0 SOL | 13 | 3,8 % | **+2,77** | +0,213 | +0,190 | **−0,001** [−0,015; +0,012] |
| **0,5 %** | 10,0 SOL | 45 | **13,1 %** | −9,10 | −0,202 | **+0,250** | **+0,059** [+0,036; +0,079] |
| 0,25 % | 20,0 SOL | 153 | 44,5 % | **+44,42** | +0,290 | +0,110 | **−0,080** [−0,109; −0,038] |

O teto de **1 % não faz nada** (Δ = −0,001 R, IC cruza o zero, 3,8 % das entradas). O de **0,5 % ganha +0,059 R por
aposta** e é positivo **nos cinco dias separados** (+0,05 / +0,06 / +0,04 / +0,09 / +0,02) — mas **todo esse ganho é o
buraco da §1**: 0,5 % é exatamente a régua que apaga a faixa 5–10 SOL. Apertar para **0,25 % destrói a vantagem**
(−0,080 R, IC inteiro negativo, 44,5 % da cadência fora): aí o corte começa a comer a faixa 10–20, que é onde o R vive.

## 4. Fluxo líquido e compradores do minuto

| `net_sol_flow_1m` | n | /dia | R médio | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % |
|---|---|---|---|---|---|---|---|
| ≤ 0 | 30 | 9,0 | −0,014 | −0,41 | 3 (10,0 %) | 11 (36,7 %) | [−0,260; +0,105] |
| 0–2 | 32 | 10,7 | +0,160 | +5,12 | 5 (15,6 %) | 17 (53,1 %) | [−0,261; +0,530] |
| 2–5 | 81 | 23,7 | +0,342 | +27,72 | 12 (14,8 %) | 30 (37,0 %) | [−0,289; +0,593] |
| 5–10 | 115 | 35,0 | +0,237 | +27,28 | 22 (19,1 %) | 54 (47,0 %) | [+0,087; +0,578] |
| 10–20 | 70 | 20,7 | −0,022 | −1,57 | 8 (11,4 %) | 38 (54,3 %) | [−0,169; +0,064] |
| ≥ 20 | 16 | 4,7 | +0,462 | +7,39 | 4 (25,0 %) | 8 (50,0 %) | [−0,887; +0,775] |

Spearman `flow_1m` × R = −0,061 (p = 0,27); × cauda = +0,028 (p = 0,60). **Não separa.** Nem o fluxo ≤ 0 (30 entradas
que a porta de 15 s deixou passar porque o fluxo era positivo na foto e virou até a barra de entrada) é distinguível de
zero — o que **enfraquece** `min_net_flow` como critério de entrada, exatamente como os "subindo" do KB-0099 §2.

| `unique_buyers` (1 min) | n | /dia | R médio | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % |
|---|---|---|---|---|---|---|---|
| 10–15 | 28 | 8,7 | +0,069 | +1,94 | 2 (7,1 %) | 9 (32,1 %) | [−0,391; +0,598] |
| 15–25 | 55 | 17,3 | +0,029 | +1,60 | 4 (7,3 %) | 23 (41,8 %) | [−0,342; +0,196] |
| 25–40 | 81 | 24,3 | +0,202 | +16,35 | 11 (13,6 %) | 30 (37,0 %) | [+0,072; +0,432] |
| 40–70 | 98 | 26,7 | +0,205 | +20,05 | 16 (16,3 %) | 46 (46,9 %) | [−0,003; +0,494] |
| **70–120** | 50 | 16,3 | **+0,534** | +26,68 | **15 (30,0 %)** | **29 (58,0 %)** | [+0,329; +0,997] |
| ≥ 120 | 32 | 10,3 | −0,035 | −1,11 | 6 (18,8 %) | 21 (65,6 %) | [−0,332; +1,284] |

**`unique_buyers` é a única das três com sinal de cauda:** Spearman com (R ≥ +2) = **+0,153 (p = 0,007)**, enquanto com o
R contínuo é **−0,093 (p = 0,08)**. Mais compradores por minuto ⇒ **mais 3× e mais ruína ao mesmo tempo** (70–120: 30,0 %
de cauda contra 58,0 % de ruína). É um seletor de **variância**, não de média — e com alvo 3× e piso −50 %, variância é o
que a nossa perna de saída quer. O piso atual (`≥ 10`) está na faixa mais fraca da tabela; subir para **≥ 25** é a
hipótese que sai daqui (não a implanto nesta nota: é medida *in-sample*, e vale pré-registro).

## 5. Recomendação (4 linhas)

1. **`max_participation_pct` fica em 1 % — como limite de risco de execução, e só.** Com 0,05 SOL o impacto real é de
   0,05 % a 0,16 % (o teto de 0,5 % nunca morde), então a 1 % o critério recusa 3,8 % das entradas e muda o R em −0,001 R
   [−0,015; +0,012]: é barato, honesto e não é dele que a mesa depende. **Não suba** — o teto tem de continuar amarrado a
   tamanho, não a opinião.
2. **Não desça para 0,25 %**: −0,080 R por aposta (IC inteiro negativo) e −44,5 % de cadência. O R21 sugeriu "cortar
   participação para conseguir volume"; a medida diz que apertar participação **derruba** a vantagem.
3. **0,5 % é tentador e não deve entrar como teto de risco**: o +0,059 R [+0,036; +0,079] que ele entrega é 100 % o
   buraco da faixa 5–10 SOL/min (§1), achado depois de olhar os dados, com n = 32. Se for testar, que seja como
   **critério de seleção pré-registrado** (`min_curve_volume_1m_sol = 10`), em braço próprio, com holdout — não
   escondido dentro do motor de risco.
4. **O volume do minuto não é onde o R vive; `unique_buyers` é a única das três com sinal.** A próxima calibração deve
   mexer em `min_unique_buyers` (10 → 25, pré-registrado), não no teto de participação; e o `min_net_flow` da porta entra
   na fila dos critérios a questionar, junto com os "subindo" do KB-0099.

**Limites desta medição:** (i) entrada no mcap da barra, sem atraso de decisão
([[11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]]); (ii) saída em barras de 1 min, enquanto a
mesa decide a cada 15 s; (iii) sem TTL, dedup nem cooldown — a cadência de 103,7/dia é **teto**, não o que a mesa
propõe; (iv) o teto de participação **na saída** não foi simulado, e a
[[11-KNOWLEDGE/KB-0088-o-teto-de-participacao-nos-motores-de-backtest|KB-0088]] diz que ele corta cauda; (v) 5 dias, 2
parciais, n = 344, e todas as faixas foram escolhidas depois de ver a distribuição — nenhuma delas é pré-registrada.

## Ligações
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio]] ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao]] ·
[[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica]] ·
[[11-KNOWLEDGE/KB-0109-top10-e-bundle-onde-o-teto-deveria-estar]] ·
[[11-KNOWLEDGE/KB-0088-o-teto-de-participacao-nos-motores-de-backtest]] ·
`docs/RISK_ENGINE_MEME.md` §3.1 · `packages/risk-core/hunter_risk_meme/sizing.py`
