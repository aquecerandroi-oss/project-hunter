---
tags: [knowledge, nota, meme, pumpfun, porta, calibracao, compradores, pre-registro, m5]
tema: memecoin / pump.fun / onde colocar o piso de min_unique_buyers — cadência e R por piso, com leave-one-day-out e redundância com holders/snipers
fonte: banco da VPS (meme_features_15s, meme_features_1m, meme_tokens), 12–16/09/2026 BRT
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r28-q01-compradores-por-moeda-e-r.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-r28-q0{1,2,3}-*.sql; mesma coorte do KB-0112, 345 entradas em 5 dias, 3 cheios)
hipotese_testavel: sim
astra: não consultada nesta nota (pesquisa quant, 16/09 noite BRT)
confianca: backtest do autor, in-sample; 5 dias (2 parciais)
owner: astra-quant
updated: 2026-09-16
status: vivo
---

# KB-0114 — Compradores únicos: o piso e o R

**A pergunta (16/09):** o [[11-KNOWLEDGE/KB-0112-volume-do-minuto-participacao-e-r|KB-0112]] §4 achou que
`unique_buyers` é **a única** das três variáveis do minuto com sinal de cauda (Spearman com R ≥ +2 = +0,153) e fechou
recomendando `min_unique_buyers` **10 → 25**. Esta nota mede o que cada piso — **10, 15, 20, 25, 30, 40, 60** — faz com
**cadência** e **R**, e testa se o vencedor sobrevive a tirar cada dia.

## 0. Método (escrito antes de olhar o resultado)

- **Coorte = a mesma do KB-0112**, reuso literal do `r24-q01`/`r19-q01`: primeira foto de 15 s com `age_s` 30–300 s,
  curva viva, não-Mayhem, `curve_progress_pct` 0,05–0,50 (fração 0–1), `tape_reason IS NULL`, `net_sol_flow_60s > 0`,
  `dev_share ≤ 0,10`, `snipers ≥ 21` ([[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] §7), **sem** critério
  de participação. Entrada = primeira barra de 1 min nos 5 min seguintes com `holders ≥ 20`, `unique_buyers ≥ 10`,
  `sells_1m/buys_1m ≤ 0,6`.
- **R simulado**: metodologia literal do [[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]]
  (`r4-q05`/`r8-q01`): alvo 3×, trailing 35 % armado depois de 1,5×, piso −50 %, 30 min, 1,75 % por perna,
  `R = (múltiplo líquido − 1)/0,5`.
- **Duas leituras de cada piso**, e a diferença importa:
  1. **pós-filtro** — a mesma coorte, ficando só com as entradas cuja barra já tinha `buyers ≥ piso` (é a leitura
     comparável, subconjunto puro);
  2. **reentrada** (`r28-q02`) — o piso entra **na escolha da barra**: a moeda que não qualifica no minuto 1 pode entrar
     no minuto 3. **É esta a política de verdade**, e ela não é subconjunto da coorte de 10.
- **IC 95 % por bootstrap de blocos de dia** (5 000 réplicas), como no KB-0112. Cadência = média dos **3 dias cheios**
  (13, 14, 15/09).
- **n = 345** (12/09: 11 · 13/09: 69 · 14/09: 109 · 15/09: 133 · 16/09: **23**). O KB-0112 contou 344 porque rodou mais
  cedo: o dia 16/09 ganhou **uma** entrada desde então. R total +64,86; R médio +0,188; 54 caudas (15,7 %). Os números
  do KB-0112 ficam reproduzidos dentro de 0,002 R.

## 1. Piso de `min_unique_buyers` — pós-filtro sobre as 345

| piso | n | /dia | R médio | R mediano | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % (R médio) |
|---|---|---|---|---|---|---|---|---|
| **≥ 10 (hoje)** | 345 | 103,7 | +0,188 | −0,313 | +64,86 | 54 (15,7 %) | 159 (46,1 %) | [+0,052; +0,252] |
| ≥ 15 | 317 | 95,0 | +0,199 | −0,363 | +62,92 | 52 (16,4 %) | 150 (47,3 %) | [+0,090; +0,232] |
| ≥ 20 | 289 | 86,3 | +0,203 | −0,363 | +58,73 | 49 (17,0 %) | 138 (47,8 %) | [+0,109; +0,231] |
| **≥ 25** | 262 | 77,7 | **+0,234** | −0,419 | +61,32 | 48 (18,3 %) | 127 (48,5 %) | [+0,162; +0,273] |
| ≥ 30 | 228 | 67,3 | +0,215 | −0,532 | +48,93 | 43 (18,9 %) | 116 (50,9 %) | [+0,099; +0,333] |
| ≥ 40 | 181 | 53,3 | +0,248 | −0,660 | +44,97 | 37 (20,4 %) | 97 (53,6 %) | [+0,048; +0,359] |
| ≥ 60 | 101 | 32,7 | **+0,355** | −0,740 | +35,89 | 25 (24,8 %) | 57 (56,4 %) | **[+0,091; +1,489]** |

**A taxa de cauda sobe monotonicamente com o piso** (15,7 % → 24,8 %) e **a de ruína também** (46,1 % → 56,4 %): o piso
é um **seletor de variância**, exatamente como o KB-0112 §4 previu. O **R mediano piora sempre** (−0,31 → −0,74) — quem
ganha é só a cauda. Spearman nesta coorte: `buyers` × R = **−0,094 (p = 0,082)**; `buyers` × (R ≥ +2) = **+0,153
(p = 0,004)** — o mesmo par de sinais de sentido oposto.

**As faixas exclusivas mostram que a escada não é limpa:**

| faixa | n | /dia | R médio | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % |
|---|---|---|---|---|---|---|---|
| 10–15 | 28 | 8,7 | +0,069 | +1,94 | 2 (7,1 %) | 9 (32,1 %) | [−0,391; +0,598] |
| 15–20 | 28 | 8,7 | +0,150 | +4,20 | 3 (10,7 %) | 12 (42,9 %) | [−0,151; +0,226] |
| **20–25** | 27 | 8,7 | **−0,096** | −2,59 | 1 (3,7 %) | 11 (40,7 %) | [−0,522; +0,181] |
| 25–30 | 34 | 10,3 | +0,365 | +12,39 | 5 (14,7 %) | 11 (32,4 %) | [−0,139; +0,732] |
| 30–40 | 47 | 14,0 | +0,084 | +3,96 | 6 (12,8 %) | 19 (40,4 %) | [−0,117; +0,507] |
| 40–60 | 80 | 20,7 | +0,113 | +9,08 | 12 (15,0 %) | 40 (50,0 %) | [−0,258; +0,491] |
| ≥ 60 | 101 | 32,7 | +0,355 | +35,89 | 25 (24,8 %) | 57 (56,4 %) | [+0,091; +1,489] |

Boa parte do ganho de "≥ 25" é **tirar a faixa 20–25** (n = 27, uma única cauda). Com n ≈ 30 por faixa, isso é ruído
possível — é o mesmo tipo de buraco que o KB-0112 §1 achou em volume e tratou como pista.

## 2. A leitura honesta do piso: reentrada (`r28-q02`)

Aplicando `buyers ≥ 25` **na escolha da barra**, 11 moedas que o pós-filtro descartava entram numa barra posterior:

| piso 25 | n (5 dias) | /dia (3 cheios) | R médio | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % |
|---|---|---|---|---|---|---|---|
| pós-filtro | 262 | 77,7 | +0,234 | +61,32 | 48 (18,3 %) | 127 (48,5 %) | [+0,162; +0,273] |
| **reentrada** | **273** | **81,3** | **+0,278** | **+75,86** | 51 (18,7 %) | 128 (46,9 %) | [+0,166; +0,330] |

Δ contra o piso de hoje (bootstrap pareado de dias, 5 000 réplicas):

| comparação | Δ R médio | IC 95 % | P(Δ > 0) |
|---|---|---|---|
| ≥ 25 pós-filtro vs ≥ 10 | +0,046 | [−0,024; +0,156] | 0,89 |
| **≥ 25 reentrada vs ≥ 10** | **+0,090** | **[+0,038; +0,201]** | **1,00** |

Esperar a barra com 25 compradores **não perde a moeda; atrasa a entrada** — e nesta amostra o atraso pagou (+11 R no
total com 21 % menos apostas). **É o resultado mais forte da nota, e é in-sample.**

## 3. Leave-one-day-out — o piso vencedor se sustenta?

R médio recalculado tirando cada dia (pós-filtro):

| piso | todos | sem 12/09 | sem 13/09 | sem 14/09 | sem 15/09 | sem 16/09 |
|---|---|---|---|---|---|---|
| ≥ 10 | +0,188 | +0,204 | +0,201 | +0,194 | +0,129 | +0,195 |
| ≥ 15 | +0,199 | +0,213 | +0,200 | +0,192 | +0,169 | +0,206 |
| ≥ 20 | +0,203 | +0,214 | +0,204 | +0,199 | +0,177 | +0,211 |
| **≥ 25** | +0,234 | +0,244 | **+0,216** | +0,233 | **+0,226** | +0,246 |
| ≥ 30 | +0,215 | +0,225 | +0,163 | +0,217 | +0,233 | +0,235 |
| ≥ 40 | +0,248 | +0,255 | +0,205 | +0,238 | +0,242 | +0,292 |
| **≥ 60** | +0,355 | +0,323 | **+0,212** | **+0,577** | +0,391 | +0,371 |

n e R médio **por dia**:

| piso | 12/09 | 13/09 | 14/09 | 15/09 | 16/09 |
|---|---|---|---|---|---|
| ≥ 10 | 11 / −0,30 | 69 / +0,14 | 109 / +0,18 | 133 / +0,28 | 23 / +0,09 |
| ≥ 25 | 8 / −0,07 | 48 / +0,31 | 85 / +0,24 | 100 / +0,25 | 21 / +0,10 |
| ≥ 40 | 6 / +0,04 | 31 / +0,46 | 57 / +0,27 | 72 / +0,26 | 15 / −0,23 |
| ≥ 60 | **2** / +1,93 | 11 / +1,53 | 45 / +0,08 | 42 / +0,31 | **1** / −1,22 |

**≥ 25 é o único piso alto que se sustenta**: o R médio anda entre +0,216 e +0,246 nas cinco remoções (amplitude 0,030) e
é positivo **nos quatro dias com n ≥ 20**. Na reentrada o mesmo: +0,248 a +0,295.
**≥ 60 tem a maior média e é o mais frágil**: amplitude de +0,212 a +0,577 (2,7×), IC de largura 1,4 R, e **metade do R
vem de 13 apostas em 12–13/09** (R médio +1,5 a +1,9 nesses dias contra +0,08 em 14/09). Com 2 e 1 aposta nos dias
parciais, ≥ 60 é uma aposta em dois dias, não uma régua.

## 4. Redundância com holders (≥ 20) e snipers (≥ 21)

Na coorte da §1 `holders ≥ 20` vale **por construção**, então perguntei fora dela (`r28-q03`): entre **todas** as barras
candidatas do universo (sem filtro de holders e sem o de compradores), qual fração das que têm `buyers ≥ piso` já tem
`holders ≥ 20`?

| piso de compradores | barras 14/09 | já com holders ≥ 20 | barras 15/09 | já com holders ≥ 20 | mediana de holders (15/09) |
|---|---|---|---|---|---|
| ≥ 10 | 199 | 93,5 % | 263 | 91,3 % | 67 |
| ≥ 20 | 158 | 97,5 % | 203 | 95,6 % | 83 |
| **≥ 25** | 147 | **99,3 %** | 173 | **96,5 %** | 89 |
| ≥ 40 | 101 | 100,0 % | 119 | 99,2 % | 127 |
| ≥ 60 | 79 | 100,0 % | 66 | 98,5 % | 148 |

**Sim, há redundância, e ela é quase total a partir de 25:** `buyers ≥ 25` implica `holders ≥ 20` em **96,5–99,3 %** dos
casos, e em 14/09 `buyers ≥ 40` implica em 100 %. Ou seja, **subir o piso de compradores para 25 torna `min_holders = 20`
praticamente inerte** — o que é bom (um critério a menos fazendo trabalho) e é um alerta (não creditar ao piso de
compradores o que já era do de holders).

**Com snipers não há redundância.** Spearman `buyers` × `holders` = **+0,646**; `buyers` × `snipers` = **+0,219**. A
mediana de snipers não se move com o piso (39–40 em ≥ 10 até 45 em ≥ 60) — as duas variáveis medem coisas diferentes, e
se combinam:

| faixa de snipers | `buyers ≥ 10` | `buyers ≥ 25` |
|---|---|---|
| 21–30 | n = 97 · +0,055 | n = 67 · **−0,022** |
| 30–50 | n = 148 · +0,255 | n = 117 · **+0,372** |
| 50–100 | n = 93 · +0,262 | n = 73 · +0,277 |
| ≥ 100 | n = 7 · −0,348 | n = 5 · −0,203 |

O piso de compradores **só paga onde os snipers já são 30–50**; na faixa 21–30 ele não salva (fica em zero). Isso é
consistente com o [[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] e com o KB-0106 §7, e sugere
que a interação (não cada piso sozinho) é o objeto da próxima medida.

## 5. A régua fecha? (n por piso, honesto)

| piso | apostas em 5 dias | /dia (3 cheios) | fecha ≥ 100 apostas em 5 d? |
|---|---|---|---|
| ≥ 25 | 262 (pós-filtro) / **273 (reentrada)** | 77,7 / 81,3 | **sim, com folga** |
| ≥ 30 | 228 | 67,3 | sim |
| ≥ 40 | 181 | 53,3 | sim |
| ≥ 60 | **101** | 32,7 | **no limite — e só olhando 5 dias; nos 3 dias cheios são 98** |

**≥ 25 não é o problema de amostra — ≥ 60 é.** O piso de 25 deixa 273 apostas em 5 dias (81/dia de teto teórico, antes de
TTL/dedup/cooldown, que o KB-0112 já avisou que derrubam esse número). Já **≥ 60 entrega 32,7/dia, 101 em 5 dias, com um
dia de 1 aposta e outro de 2**: para detectar +0,1 R com esse desvio (σ ≈ 1,6 R por aposta) seriam necessárias ~2 000
apostas, ou **~60 dias a 33/dia**. **A régua de ≥ 60 não fecha**, e nenhum número desta nota deve ser usado para subir o
piso além de 25.

## 6. Rascunho de pré-registro — braço `flow_v2/7` (NÃO implantado)

Escrito **antes** de qualquer rodada nova, no formato do
[[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]] (que existe justamente porque um modelo
bonito in-sample morreu no holdout).

- **Mudança única:** `min_unique_buyers` **10 → 25** em `flow_v2/7`, clone exato do conjunto vivo em todo o resto
  (incluindo `max_participation_pct = 1 %`, KB-0112 §5.1, e `min_holders = 20`, que fica no conjunto mesmo virando
  quase inerte — tirar dois critérios de uma vez impede atribuir o efeito). O piso entra **na escolha da barra**
  (reentrada), não como recusa definitiva da moeda.
- **Hipótese (mecanismo):** mais compradores distintos no minuto = mais gente independente descobrindo a moeda ⇒ maior
  variância do desfecho; com alvo 3× e piso −50 %, variância assimétrica a favor. Previsão do mecanismo: **a taxa de
  cauda sobe** (15,7 % → ~18–19 %) **e a de ruína também** (46 % → ~47–49 %); o R médio sobe por conta da cauda, e o R
  **mediano piora**. Se o R médio subir **sem** a cauda subir, o mecanismo está errado mesmo que o número agrade.
- **Previsão numérica (o que eu afirmo agora):** em ≥ 150 propostas do braço, contra o braço de controle no **mesmo
  período**, Δ R médio ∈ **[+0,04; +0,20]**, ponto central **+0,09**; cadência do braço entre **55 % e 85 %** da do
  controle.
- **`descartar` se** (qualquer uma): (i) Δ R médio ≤ 0 com IC 95 % de blocos de dia inteiramente ≤ +0,02 depois de 150
  propostas; (ii) a taxa de cauda do braço **não** ficar acima da do controle (mecanismo falso); (iii) a cadência cair
  abaixo de **45 %** do controle (a régua deixa de fechar em tempo útil); (iv) o resultado depender de **um** dia —
  leave-one-day-out com qualquer remoção levando Δ abaixo de zero.
- **Régua e prazo:** mínimo **150 propostas** do braço **e** 10 dias corridos, o que vier **por último**; leitura única
  no fim (sem espiar para decidir), com LOO obrigatório. Sem re-teste do mesmo piso depois de reprovado — piso reprovado
  volta só com **mecanismo novo**, não com dados novos.
- **Fora do escopo deste braço:** 30, 40 e 60 (n insuficiente, §5) e qualquer mexida em `min_holders`, `min_net_flow` ou
  no teto de participação.

## 7. Recomendação (3 linhas)

1. **`min_unique_buyers` = 25, por pré-registro, em braço próprio** (`flow_v2/7`), com reentrada. É o único piso com
   ganho estável no leave-one-day-out (+0,216 a +0,246), Δ +0,090 R [+0,038; +0,201] contra o piso de hoje, e cadência
   que ainda fecha a régua (81/dia de teto, 273 apostas em 5 dias).
2. **Não passe de 25.** 40 e 60 têm médias maiores e amostra que não sustenta: ≥ 60 vive de 13 apostas em dois dias e
   precisaria de ~60 dias para se provar.
3. **Depois do braço, a próxima pergunta é a interação `snipers` × `buyers`** (§4): o piso só paga com snipers 30–50 e
   não salva a faixa 21–30. E note que a 25 o `min_holders = 20` vira quase inerte (96,5–99,3 % de implicação) — quando
   for simplificar a porta, é esse o critério que está sobrando, não o de compradores.

**Limites:** (i) **tudo é in-sample** — a faixa 20–25 negativa e o próprio 25 saíram de olhar a mesma amostra que os
mede (KB-0092); (ii) entrada no mcap da barra, sem atraso de decisão
([[11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]]); (iii) saída em barras de 1 min, enquanto a
mesa decide a cada 15 s; (iv) sem TTL, dedup nem cooldown — as cadências são teto; (v) 5 dias, 2 parciais, e 12/09 e
16/09 têm 8–23 entradas cada, o que limita o LOO; (vi) `unique_buyers` da série de 1 min não é necessariamente o que o
worker lê no instante da decisão.

## Ligações
[[11-KNOWLEDGE/KB-0112-volume-do-minuto-participacao-e-r]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio]] ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao]] ·
[[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica]] ·
[[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout]] ·
[[11-KNOWLEDGE/KB-0109-top10-e-bundle-onde-o-teto-deveria-estar]]
