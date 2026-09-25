---
tags: [knowledge, nota, meme, pumpfun, top10, bundle, admissao, risco, teto, m5]
tema: memecoin / pump.fun / onde o teto de top10_share (25 %) e o de bundled_share (20 %) deveriam estar para o estagio 1
fonte: banco da VPS (meme_features_15s, meme_features_1m, meme_risk_snapshots, meme_tokens, meme_live_orders), 12-16/09/2026 BRT
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r19-q01-top10-por-moeda-e-r.sql
lido_em: 2026-09-16
evidencia: medicao propria (SQL em infra/scripts/sql/research/2026-09-16-r19-q0{1,2}-*.sql; 344 moedas na porta da mesa, 5 dias, 39 saidas em 3x)
hipotese_testavel: sim
astra: nao consultada nesta nota (pesquisa quant, 16/09 ~23h BRT)
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

# KB-0109 — Top-10 e bundle: onde o teto deveria estar

**O fato que abriu a nota (16/09):** das 16 ordens reais do dia, **4 bateram em `top10_share_above_cap`** e duas delas por
margem mínima — **25,33 %** e **25,76 %** contra o teto de **25,00 %** (`MEME_PAPER_V0.max_top10_share_pct`,
`docs/RISK_ENGINE_MEME.md` §3.1/§4 check 12). O teto é **política do dono**; esta nota só entrega o número que falta para
ele decidir: **quanto custa cada nível em propostas/dia e em R**, e **onde o R vira negativo**.

## 0. Método (escrito antes de olhar o resultado)

- **Universo = a porta atual da mesa**, reconstruída sobre a série de 15 s + a de 1 min: primeira foto com `age_s` 30–300 s,
  curva viva, **não-Mayhem** (`mayhem_enabled` false **e** `mayhem_mode` nulo), `curve_progress_pct` **0,05–0,50**
  (fração 0–1), fita presente (`tape_reason IS NULL`), fluxo líquido 60 s > 0, `dev_share ≤ 0,10`, **`snipers ≥ 21`**
  (a recomendação do [[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] §7). **Entrada** = a primeira barra de
  1 min nos 5 min seguintes com `holders ≥ 20`, `unique_buyers ≥ 10`, `sells/buys ≤ 0,6` — **o `top10_share` é lido nessa
  barra**, que é o número que o executor veria. Pedigree **não** entra (não está na porta do brief).
- **R simulado**: metodologia literal do [[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]]
  (reuso do `r4-q05`/`r8-q01`) nas barras de 1 min — alvo 3×, trailing 35 % armado depois de 1,5×, piso −50 %, tempo
  **30 min**, taxa **1,75 % por perna**, stop preenchido no mcap **observado** da barra; `R = (múltiplo líquido − 1)/0,5`.
- **Graduação orgânica** = definição do [[11-KNOWLEDGE/KB-0104-taxas-base-sem-as-nascidas-cheias|KB-0104]]/KB-0106
  (`completed_at` não nulo, vida > 60 s e ao menos uma foto de 15 s com progresso < 0,9 antes da graduação).
- **IC 95 %** por **bootstrap de dias** (blocos): reamostra os 5 dias com reposição, 5 000 réplicas — é o intervalo honesto
  quando a variância entre dias é maior que a variância entre moedas (KB-0099 §3).
- **Unidades conferidas nesta sessão:** `meme_features_1m.top10_share` é **fração 0–1** (CHECK `top10_share_is_a_fraction`;
  o `t10` do site chega como percentual e é convertido uma única vez em `board_models.py`). Na população relevante (barras
  com `holders ≥ 20`, idade ≤ 6 min) a moda está em 0,1–0,3, como se espera. `meme_risk_snapshots.top10_share` também é
  fração, **mas tem máximo 1,124 em 15/09** — denominador sem exclusão completa de curva/pool/burn; é a mesma preocupação do
  `holder_denominator_invalid` do check 12, e por isso as bandas desta nota usam a leitura de `meme_features_1m`.
- **n = 344 moedas** (12/09: 11 · 13/09: 69 · 14/09: 109 · 15/09: 133 · 16/09: 22). 12/09 e 16/09 são **dias parciais**.

## 1. `top10_share` na barra de entrada — n, cadência, graduação e R

| Faixa `top10_share` | n | props/dia | grad. orgânica | R médio | R mediana | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % (dia) |
|---|---|---|---|---|---|---|---|---|---|
| ≤ 15 % | 65 | 13,0 | **0 (0,0 %)** | +0,179 | −0,445 | +11,65 | 12 (18,5 %) | 31 (47,7 %) | [−0,39; +0,28] |
| 15–20 % | 75 | 15,0 | 7 (9,3 %) | **+0,365** | −0,403 | +27,39 | 16 (21,3 %) | 36 (48,0 %) | [−0,01; +0,58] |
| 20–25 % | 122 | 24,4 | 10 (8,2 %) | +0,185 | −0,157 | +22,57 | 16 (13,1 %) | 49 (40,2 %) | [+0,09; +0,32] |
| **25–30 %** | **63** | **12,6** | **11 (17,5 %)** | **+0,106** | −0,558 | **+6,68** | 9 (14,3 %) | 32 (50,8 %) | [−0,31; +0,30] |
| 30–40 % | 18 | 3,6 | 4 (22,2 %) | **−0,174** | −0,690 | **−3,13** | 1 (5,6 %) | 10 (55,6 %) | [−0,72; +0,33] |
| > 40 % | 1 | 0,2 | 1 (100 %) | +0,366 | +0,366 | +0,37 | 0 | 0 | — |

**Onde o R vira negativo: acima de 30 %.** A faixa 30–40 % é a **única** com R médio negativo (−0,174), a única com **zero**
saídas no alvo 3× em 18 moedas, e a de maior taxa de ruína (55,6 % com ≤ −0,5 R). A faixa **25–30 %, que o teto de hoje
recusa, ainda é positiva** (+0,106 R; 5 saídas em 3× somando +19,0 R contra −12,3 R do resto da faixa).

**Nada disso é significativo isolado.** 25–30 % contra ≤ 25 %: diferença **−0,129 R**, IC 95 % [−0,55; +0,30]. Acima de 30 %
contra ≤ 30 %: **−0,355 R**, IC 95 % [−0,90; +0,24]. O que a medida sustenta é **"o ponto estimado cai e a cauda some acima
de 30 %"**, não "acima de 25 % é pior" — isso o dado **não** diz.

**A tensão que a tabela revela e que ninguém tinha escrito:** a **graduação orgânica sobe monotonamente com o top-10**
(0,0 % → 9,3 % → 8,2 % → **17,5 %** → **22,2 %**) enquanto o R de 30 min cai. Concentração alta é **melhor prognóstico de
graduação** e **pior prognóstico de 3× em 30 minutos**. O teto de top-10, do jeito que está, filtra **justamente** a coorte
que gradua — e o que ele compra em troca é a cauda de 3× rápida, que é onde o R desta perna de saída vive.

## 2. O custo de cada teto, em propostas/dia e em R/dia

| Teto | n (5 d) | **propostas/dia** | por dia (12→16/09) | R médio | **R/dia** | ≥ +2 R |
|---|---|---|---|---|---|---|
| 20 % | 140 | 28,0 | 5 · 19 · 56 · 53 · 7 | +0,279 | +7,81 | 28 |
| **25 % (hoje)** | **262** | **52,4** | 8 · 49 · 90 · 101 · 14 | **+0,235** | **+12,32** | 44 |
| **30 %** | **325** | **65,0** | 9 · 63 · 105 · 127 · 21 | +0,210 | **+13,66** | 53 |
| 35 % | 339 | 67,8 | 11 · 66 · 109 · 131 · 22 | +0,197 | +13,36 | 54 |
| sem teto | 344 | 68,8 | 11 · 69 · 109 · 133 · 22 | +0,190 | +13,10 | 54 |

- **25 → 30 %:** **+12,6 propostas/dia (+24 %)** e **+1,34 R/dia**; o R médio por aposta cai de +0,235 para +0,210
  (diluição, não prejuízo). É o único degrau que paga.
- **30 → 35 %:** **+2,8 propostas/dia** que somam **−1,47 R em 5 dias** (−0,105 R médio, **zero** 3×). Compra ruído.
- **25 → 20 %:** perde **24,4 propostas/dia** e **−4,5 R/dia**. Apertar o teto é a pior das opções medidas.

## 3. `bundled_share` — o teto de 20 % **não é testável hoje**, e não é o teto que morde

| Faixa (1.º retrato de risco do mint) | n | props/dia | grad. orgânica | R médio | R mediana | R total | ≥ +2 R | ≤ −0,5 R | IC 95 % (dia) |
|---|---|---|---|---|---|---|---|---|---|
| ≤ 15 % | 40 | 8,0 | 8 (20,0 %) | +1,789 | +2,107 | +71,55 | 21 (52,5 %) | 6 (15,0 %) | [+1,07; +2,45] |
| 15–20 % | 19 | 3,8 | 5 (26,3 %) | +2,089 | +3,291 | +39,69 | 10 (52,6 %) | 3 (15,8 %) | [+1,17; +2,41] |
| 20–25 % | 12 | 2,4 | 4 (33,3 %) | +1,935 | +2,418 | +23,21 | 7 (58,3 %) | 2 (16,7 %) | [+1,09; +2,55] |
| 25–30 % | 18 | 3,6 | 3 (16,7 %) | +0,906 | +0,757 | +16,30 | 3 (16,7 %) | 3 (16,7 %) | [+0,20; +2,55] |
| 30–40 % | 17 | 3,4 | 6 (35,3 %) | +1,319 | +0,882 | +22,43 | 6 (35,3 %) | 3 (17,6 %) | [+0,76; +1,53] |
| > 40 % | 12 | 2,4 | 6 (50,0 %) | +1,499 | +1,796 | +17,99 | 6 (50,0 %) | 3 (25,0 %) | [+0,46; +3,05] |
| **sem retrato** | **226** | 45,2 | 1 (0,4 %) | **−0,556** | −0,816 | −125,64 | 1 (0,4 %) | 138 (61,1 %) | [−0,67; −0,53] |

**A linha que invalida a tabela acima como evidência de teto:** ter retrato de risco **é** o sinal. Moedas com
`bundled_share` medido rendem **+1,62 R** contra **−0,556 R** das sem retrato, e **32 das 33 graduações orgânicas** da
amostra estão do lado medido. O retrato chega porque a moeda **entrou na lista** do indexador — viés de seleção de primeira
ordem, não uma propriedade do bundle. Dentro das medidas, **≤ 20 % rende +1,885 e > 20 % rende +1,355**: diferença
**+0,530 R**, IC 95 % **[−0,14; +1,21]** — **não separa**. E o teto de 20 % cortaria **59 das 118 medidas (50 %)**.

**Pior:** só **26 das 344** (7,6 %) têm retrato com `observed_at ≤ barra de entrada`, e **20 desses 26 estão acima de 20 %**.
Sem look-ahead, a banda honesta tem n = 4/2/5/5/5/5 por faixa — **nada é decidível**. Isso confirma a §4 do contrato pelo
outro lado: **hoje o custo do check 11 é `bundled_share_unmeasurable` (13 das 16 ordens reais), não `above_cap` (1 ordem)**.
O teto de 20 % não é o problema; a **latência do retrato** (mediana +103 s depois da decisão, R5) é.

## 4. As duas recusas de fronteira de hoje — eram moedas boas?

| BRT | mint | `top10_share` | progresso | holders | snipers | múltiplo máx. 30 min | saída | **R** | graduou |
|---|---|---|---|---|---|---|---|---|---|
| 14:05 (×2) | `7uwn4T` | 0,4999 | 0,649 | 25 | 1 | 0,305 | stop | **−1,412** | não |
| 14:08 | `FLHSaT` | **0,2533** | 0,666 | 115 | 5 | 1,537 | tempo | **+0,443** | não |
| 15:33 | `Cfsb4v` | **0,2576** | 0,262 | 23 | 1 | 0,798 | tempo | **−0,704** | não |

**Resposta: não eram moedas boas — e, mais importante, nenhuma delas passaria a porta desta nota.** As duas de fronteira
somam **−0,26 R**, nenhuma graduou, nenhuma chegou perto de 3×, e ambas têm **snipers 5 e 1** (contra `≥ 21`); a `FLHSaT`
ainda tinha **progresso 0,666**, fora da janela 0,05–0,50. O `top10_share` foi a recusa **visível**, não a recusa **certa**:
a porta de estratégia já as teria descartado antes. Afrouxar o teto de top-10 **não** teria comprado essas duas — teria
comprado outras 12,6 por dia, de perfil diferente.

## 5. Recomendação (4 linhas)

1. **Subir `max_top10_share_pct` de 0,25 para 0,30.** É o único degrau que paga: **+12,6 propostas/dia (+24 %)** e
   **+1,34 R/dia**, com o R médio por aposta praticamente intacto (+0,235 → +0,210).
2. **Não passar de 0,30.** Acima de 30 % o R médio é **negativo** (−0,174), são **zero** 3× em 18 moedas, e os
   2,8 candidatos/dia entre 30 e 35 % somam **−1,47 R** em 5 dias. 30 % é teto de decisão, não de risco.
3. **Manter `max_bundled_share_pct = 0,20` como está** — não porque esteja provado, mas porque **não é testável**: 7,6 % das
   moedas têm retrato antes da entrada, e entre as medidas ≤ 20 % × > 20 % não se separa (IC cruza zero). Reabrir a pergunta
   só depois de o §3.5 do contrato (leitor cobrindo as propostas) dar ≥ 200 retratos pré-entrada.
4. **O ganho maior não está em nenhum dos dois tetos.** A recusa que custa hoje é `bundled_share_unmeasurable` (13 de 16
   ordens); consertar a latência do retrato vale mais que qualquer ajuste de limiar. **O teto é política do dono — esta nota
   só entrega o número.**

## 6. O que fica em aberto

- **5 dias, 2 parciais, 344 moedas, 39 saídas em 3×.** Coorte, não holdout; nenhuma diferença entre faixas de top-10 passa
  de uma sigma isolada. A recomendação de 0,30 apoia-se na **forma** (monotonia do ponto estimado + desaparecimento da cauda
  acima de 30 %) e no custo de oportunidade, não em significância.
- **Só uma perna de saída foi testada** (3× / trailing 35 % / 30 min). A tensão do §1 — concentração alta gradua mais e dá
  menos 3× rápido — sugere que um horizonte mais longo inverteria o sinal do teto. **Não medido.**
- `top10_share` é o `t10` do site, cuja regra de agregação não é documentada (docstring de `meme_features.py`); o check 12
  exige exclusão de curva/pool/burn e o `meme_risk_snapshots` chega a **1,124**. A banda de 25–30 % pode estar deslocada por
  causa disso — **a mesma incerteza vale para o teto de 25 % que está em produção**.
- Cadência é **contagem de moedas que passariam a porta**, não propostas emitidas: `max_open_positions = 3` e a reserva de
  5 s cortam esse número no executor real.

## Ligações
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] (metodologia de R) ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] ·
[[11-KNOWLEDGE/KB-0104-taxas-base-sem-as-nascidas-cheias|KB-0104]] ·
[[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] (porta `snipers ≥ 21`) ·
[[03-TRADING/Meme/Estudo-2026-09-16-admissao-real-o-que-recusa|R5 — admissão real]] ·
`docs/RISK_ENGINE_MEME.md` §3.1/§4 · `infra/scripts/sql/research/2026-09-16-r19-q0{1,2}-*.sql`
