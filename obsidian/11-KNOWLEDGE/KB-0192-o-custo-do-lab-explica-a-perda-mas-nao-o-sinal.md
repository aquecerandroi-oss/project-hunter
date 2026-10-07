---
tags: [knowledge, cripto, custo, lab, momentum, mean-reversion, volume-anomaly, diagnostico, binance, pesquisa, retrospectiva]
tema: "varredura de custo sobre TODOS os desfechos terminais do Lab de cripto (17 979; prospectivo e replay): R bruto, R do Lab, custo de ida-e-volta que zera a média (k*) e R sob custos Binance realistas — o custo assumido explica ~78 % da perda da momentum v3, mas o bruto já é ≤ 0; volume_anomaly tem bruto ≈ 0; só a família mean_reversion é bruto-positiva, com IC por dia contendo zero (diagnóstico, não hipótese; desfechos EXPOSTOS)"
fonte: "lab-cost-sweep (`.claude/state/lab-cost-sweep/`): extração somente-leitura da VPS em 2026-10-07 06:07Z (`q_out.sql`, `q_spot.sql`, sha256 em `extract_sha256.txt`), recomposição em `sweep.py`, relatório `results.txt`, extras `extra.txt`, fidelidade `check.txt`; pedido a partir do Defensor da H-033 na Fila de Hipóteses"
fonte_url: —
lido_em: 2026-10-07
evidencia: "medição própria, diagnóstico retrospectivo sobre desfechos já lidos por H-023/H-027/H-033 — 17 979 desfechos terminais long da Binance (16 272 com funding estabelecido), 86 grupos estratégia × versão × tipo × coorte; R reprecificado dos insumos gravados, condicionado às entradas e saídas observadas (máx |dif| 7e-11 contra o r_ex_funding gravado); bootstrap de clusters por dia UTC e por mercado (2 000 réplicas); 15 testes sintéticos"
hipotese_testavel: sim
astra: "revisão do método e das candidatas: núcleo aritmético correto (U fixo, k* como razão de somas, bootstrap da razão por cluster); 6 must-fix aceitos — reprecificação condicionada (a admissão depende do custo), populações todos × com funding separadas, horizonte ≠ custo, custo efetivo ponderado em vez de mediana, poder qualificado, redação de momentum/volume_anomaly; ranking trocado (instrumento de custo primeiro)"
status: vivo
owner: sexta-feira
updated: 2026-10-07
confiança: "?"
tipo: pesquisa
hipotese: —
variavel: "custo de ida-e-volta (bp) aplicado aos desfechos gravados do Lab; k* = custo que zera a média do R"
populacao: "desfechos terminais long, Binance, de todo o Lab de cripto até 07/10/2026 06:07Z — prospectivo (06/09–07/10) e replays (12/06–09/09); principal: momentum v3 1 673 em 30 dias e 229 mercados; família mean_reversion v1–v14 213–377 por versão em 23–27 dias"
efeito: "momentum v3 bruto −0,046 R (k* −5,5 bp); mean_reversion v14 bruto +0,083 R (k* +16,1 bp); volume_anomaly v1 bruto +0,009 R (k* +0,6 bp)"
ic: "momentum v3 IC dia [−0,090; +0,006], mercado [−0,082; −0,012]; mean_reversion v14 IC dia [−0,093; +0,287]"
veredito: —
proximo_passo: "nenhuma mudança de estratégia/parâmetro; direções para pré-registro em coorte FUTURA na seção 'Direções para o próximo pré-registro' — estes desfechos não confirmam nada, só orientam"
classe_de_perda: —
mercado: cripto
---

# KB-0192 — O custo do Lab explica a perda, mas não o sinal

> **Diagnóstico, não hipótese.** Nenhum rótulo `CONFIRMA`/`REFUTA`/`NÃO CONFIRMA` sai daqui (vocabulário de
> `docs/RESEARCH.md`): não houve pré-registro, a população é **toda** a que existe, e os desfechos já tinham sido
> lidos pela H-023, H-027 e H-033.
>
> **Os desfechos usados aqui estão EXPOSTOS.** Qualquer estratégia/versão que pareça promissora nesta nota **só pode
> ser confirmada mais tarde, numa coorte futura (sinais emitidos depois de 07/10/2026 06:07Z), com pré-registro novo**
> feito antes de ler esses desfechos. Reler estes mesmos 17 979 desfechos com outro corte, outra versão ou outra
> janela não é evidência nova (regra 4 da casa; [[KB-0149-o-que-a-mesa-real-ensinou]] §5 itens 25–26).

## O que afirma

1. **O Defensor da H-033 estava certo no tamanho:** na `momentum v3` (linha paper, 1 673 desfechos), o custo assumido
   do Lab (20 bp de ida-e-volta) vale **0,169 R por trade**, ou **78 %** do R líquido de −0,216 R. A 10 bp (taker
   Binance 5 bp/perna) a média fica em **−0,131 R**, o mesmo "~−0,13 R" que o Defensor estimou.
2. **Mas o custo não explica o sinal:** o R **bruto** (sem custo e sem funding) da `momentum v3` é **−0,046 R**
   (IC por dia [−0,090; +0,006], por mercado [−0,082; −0,012]); o custo de equilíbrio é **k* = −5,5 bp**: a
   estimativa pontual fica negativa em **todos** os cenários examinados, até com rebate de maker (−0,038 R). O IC
   por dia do bruto **contém zero** (+0,006 no topo) — não é prova de vantagem bruta negativa, é ausência de
   vantagem bruta positiva. As outras versões prospectivas da `momentum` (v1, v2, v4, v6, v8, v10) também têm
   bruto pontual negativo. **Baratear não torna a `momentum` rentável nos cenários examinados.**
3. **`volume_anomaly` tem bruto ≈ 0** (v1 +0,009 R, IC por mercado [−0,039; +0,058], 2 079 desfechos; v2 +0,005 R),
   k* ≈ +0,5 bp, em só 3 e 2 dias de vida. O custo do Lab come **0,33 R** por trade porque os stops são curtos
   (duração mediana 11 min): o custo explica praticamente toda a perda, e a vantagem bruta é pequena e incerta,
   consumida por qualquer custo positivo examinado. Maker 0 e rebate dão médias pontuais positivas (+0,010 e
   +0,027 R), incertas e supondo preenchimento.
4. **Só a família `mean_reversion` é bruto-positiva no prospectivo:** v1–v14, bruto **+0,045 a +0,087 R**,
   k* **+6 a +19 bp**. Com taker Binance (10 bp de ida-e-volta, só taxa), as versões com custo em R menor
   (v6, v7, v10, v14: 0,076–0,103 R de custo do Lab, contra 0,135–0,175 R nas v1–v3) ficam em **+0,02 a +0,04 R**;
   para a v14, +0,031 R [−0,143; +0,231] e, com mais 2 bp adversos por perna, +0,011 R [−0,162; +0,209] — custos
   assumidos, não medidos. A diferença de custo em R entre versões vem da unidade de risco (a v1 já tem horizonte de
   4 h e stop de 1 ATR; a v14 tem 1,5 ATR; a v7, 2 ATR), não do prazo. **Todos os IC por dia contêm zero**, as versões
   compartilham **48–100 % das mesmas entradas** (par a par) (é um único conjunto de entradas com saídas diferentes, não
   estratégias independentes), e **todas** viram negativas em outubro (1 a 5 dias, n 4–30 por versão).
5. **A mesa real (10 trades) não ajuda a decidir:** nos 10 sinais da `mean_reversion v14` executados na `spot/1`
   (Jupiter, dinheiro real), o real deu **−0,440 R**, a sombra do Lab no mesmo sinal **−0,388 R** e o bruto da sombra
   **−0,289 R**. É comparação descritiva pareada por sinal, com dez trades: não diz nada sobre vantagem, e a
   diferença (≈ −0,15 R contra o bruto) **não identifica custo** — praça (Jupiter × Binance perp), trajetória de
   execução e unidade de risco diferem entre a mesa e a sombra.

## Onde foi mostrado

**Fonte.** Banco da VPS, `BEGIN READ ONLY` com `default_transaction_read_only=on` (`q.sh`), extração em
2026-10-07 06:07Z: `signal_outcomes` × `agent_signals` × `strategy_versions` × `markets`, `tracking_state = 'terminal'`,
long, Binance (`q_out.sql`, 17 979 linhas, sha256 `2a2c1e6c…`), e `spot_positions` fechadas (`q_spot.sql`, 10 linhas,
sha256 `a92e1038…`). Cache comprimido em `cache/out.csv.gz` (1,8 MB). Inventário sem desfechos em `q_survey.sql`.

**Como o R foi reprecificado** (`sweep.py`, a partir de `pricing.py`/`settle.py` do `strategy-worker`). O Lab grava a
abertura **com** o custo adverso (`progress.entry`), a base da saída **sem** custo (`progress.exit_base`), o stop, os
custos assumidos (todas as 17 979 linhas: spread 2 bp, slippage 5 bp, taxa 4 bp por perna) e o funding por unidade.
Daí: abertura limpa `O = entry/(1 + 6 bp)`; unidade de risco **`U = entry − stop`** (a que o Lab gravou);
bruto `G = (B − O)/U`; cenário `R = (B(1−σ) − O(1+σ) − φ·(nocional das duas pernas) − funding)/U`;
`k* = 2·Σ(G − Φ)/Σ((O+B)/U) × 10⁴` em bp. Todos os cenários usam o **mesmo** `U`, então trocar de cenário muda só o
numerador. Conferência (`check.txt`): o R sem funding recomposto bate com o `r_ex_funding` gravado em **todas** as
17 979 linhas (máx |dif| 7e-11); com funding, 16 272 linhas, máx |dif| 7,5e-6 (5 linhas acima de 1e-6).
A Astra recalculou as 5 com `Decimal` e o `exit_price` persistido e todas caíram abaixo de 5e-11 R (compatível com
o recálculo de funding usar `virtual_entry`/`exit_price`; não reproduzido por mim). Funding não estabelecido (1 574
perpétuos) fica **fora** das colunas com funding, nunca vira zero, e isso **não** torna a ausência aleatória: por
isso o relatório publica duas populações, cada uma com as próprias contagens — **todos** os terminais (bruto e
cenário sem funding) e os **com funding** (R do Lab, Φ, k*, cenários com funding). Em spot o `r_multiple` é nulo e o
"R do Lab" é o R líquido **reconstruído** sem funding. Bootstrap de clusters por dia UTC (exige ≥ 5 dias) e por
mercado (exige ≥ 10 mercados), 2 000 réplicas, semente 20261007, IC percentil 95 % — dia e mercado são duas
sensibilidades de dependência, não uma proteção conjunta; o export lê só terminais (pendentes, censurados e
`no_entry` estão no inventário `q_survey.sql`, não nestas médias).

**É uma reprecificação condicionada, não um contrafactual de execução.** Os cenários mantêm a abertura e a base de
saída que o Lab observou e trocam só custo e funding. A saída é testada em preço de mercado, mas a **admissão**
depende do custo: o `walker` recusa a geometria se não valer `stop < entry_price(open, custos) < alvo1`
(`walker.py`, `_enter`) — com a abertura sobre o stop, o Lab admite por causa dos 6 bp adversos e outro custo
recusaria. Maker e rebate supõem preenchimento; o "spot taker 10" é sensibilidade sem funding sobre preços de
perpétuo, não backtest spot. Os números estão em **R do Lab** (unidade `U`).

### Tabela 1 — prospectivo (perpétuos; grupos com IC)

| estratégia/versão | n | dias | merc. | R do Lab | custo do Lab em R | bruto G [IC dia] [IC merc.] | k* bp [IC dia] [IC merc.] | duração p50 (p10–p90), todos | trades/dia ativo, todos |
|---|---|---|---|---|---|---|---|---|---|
| momentum v3 (paper) | 1 673 | 30 | 229 | −0,216 | 0,169 | **−0,046** [−0,090; +0,006] [−0,082; −0,012] | **−5,5** [−10,8; +0,7] [−10,0; −1,5] | 29 (9–104) min | 56,3 |
| momentum v1 | 929 | 3 | 230 | −0,190 | 0,151 | −0,040 [—] [−0,093; +0,012] | −5,3 [—] [−12,1; +1,7] | 23 (7–78) | 315,7 |
| momentum v2 | 476 | 2 | 190 | −0,220 | 0,146 | −0,074 [—] [−0,155; +0,009] | −10,2 [—] [−21,2; +1,2] | 29 (9–93) | 240,0 |
| momentum v4 | 204 | 2 | 107 | −0,166 | 0,103 | −0,063 [—] [−0,174; +0,047] | −12,2 [—] [−33,8; +9,0] | 28 (13–95) | 104,0 |
| momentum v6 | 161 | 2 | 109 | −0,298 | 0,144 | −0,156 [—] [−0,304; −0,008] | −21,5 [—] [−41,8; −0,8] | 42 (13–184) | 82,0 |
| momentum v8 | 165 | 2 | 103 | −0,193 | 0,069 | −0,125 [—] [−0,229; −0,012] | −35,9 [—] [−65,3; −3,2] | 59 (13–240) | 83,0 |
| momentum v10 | 94 | 1 | 76 | −0,147 | 0,042 | −0,105 [—] [−0,165; −0,044] | −49,6 [—] [−78,5; −22,0] | 74 (14–240) | 94,0 |
| volume_anomaly v1 | 2 079 | 3 | 237 | −0,330 | 0,340 | +0,009 [—] [−0,039; +0,058] | +0,6 [—] [−2,4; +3,4] | 11 (3–59) | 699,0 |
| volume_anomaly v2 | 1 216 | 2 | 222 | −0,311 | 0,315 | +0,005 [—] [−0,063; +0,072] | +0,3 [—] [−4,2; +4,3] | 11 (3–60) | 613,0 |
| mean_reversion v1 | 377 | 27 | 112 | −0,123 | 0,175 | +0,053 [−0,117; +0,202] [−0,058; +0,171] | +5,9 [−13,6; +22,4] [−6,6; +19,6] | 67 (12–225) | 14,3 |
| mean_reversion v2 | 282 | 26 | 82 | −0,109 | 0,153 | +0,045 [−0,117; +0,221] [−0,081; +0,170] | +5,8 [−15,4; +27,8] [−10,6; +22,7] | 68 (14–225) | 11,0 |
| mean_reversion v3 | 211 | 23 | 69 | −0,084 | 0,135 | +0,051 [−0,134; +0,287] [−0,116; +0,220] | +7,5 [−19,9; +40,4] [−17,5; +32,7] | 70 (15–222) | 9,3 |
| mean_reversion v6 | 257 | 26 | 79 | −0,015 | 0,102 | +0,087 [−0,053; +0,284] [−0,028; +0,193] | +17,0 [−11,0; +52,8] [−5,5; +38,7] | 150 (34–240) | 9,9 |
| mean_reversion v7 | 245 | 26 | 79 | −0,005 | 0,077 | +0,073 [−0,053; +0,270] [−0,044; +0,168] | +18,8 [−13,5; +65,9] [−11,4; +44,1] | 240 (65–240) | 9,5 |
| mean_reversion v8 | 314 | 27 | 88 | −0,071 | 0,118 | +0,047 [−0,099; +0,206] [−0,070; +0,138] | +7,9 [−17,2; +33,0] [−11,8; +23,6] | 140 (31–240) | 11,7 |
| mean_reversion v10 | 338 | 27 | 87 | −0,018 | 0,076 | +0,058 [−0,056; +0,193] [−0,020; +0,141] | +15,2 [−14,9; +50,6] [−5,7; +37,1] | 240 (124–240) | 12,7 |
| mean_reversion v14 (paper; sinal da `spot/1`) | 213 | 25 | 53 | −0,020 | 0,103 | +0,083 [−0,093; +0,287] [−0,058; +0,192] | +16,1 [−18,4; +53,0] [−11,4; +37,5] | 147 (33–240) | 8,5 |
| mean_reversion_h1 v1 | 104 | 19 | 24 | −0,307 | 0,126 | −0,179 [−0,470; +0,167] [−0,377; −0,017] | −28,7 [−73,7; +26,0] [−56,8; −3,3] | 226 (49–726) | 5,5 |
| session_orb v1 | 36 | 1 | 31 | −0,117 | 0,095 | −0,021 [—] [−0,381; +0,344] | −4,6 | 110 (42–240) | 38,0 |
| trendline_breakout v1 | 70 | 2 | 56 | −0,411 | 0,101 | −0,310 [—] [−0,486; −0,137] | −61,3 | 75 (14–240) | 35,0 |

`n`, dias e mercados = população com funding estabelecido; duração e trades/dia = todos os terminais. No prospectivo essa população é quase toda (diferença ≤ 18 por versão) e o
bruto de **todos** difere ≤ 0,016 R do pareado nas linhas acima, exceto `session_orb` (−0,060 todos × −0,021, 38 × 36)
— as duas colunas estão em `results.txt` §1. "[—]" = menos de 5 dias, sem IC por dia (o IC por mercado com 1–3 dias
**não** cobre o choque comum do dia e é otimista). Grupos com n < 20 (mean_reversion v4/v5/v11, momentum v5/v7,
sweep_reclaim, os poucos sinais spot do Lab) estão só em `results.txt`.

### Tabela 2 — cenários de custo (R médio por trade [IC 95 %]; funding como gravado)

| estratégia/versão | IC por | Lab (20 bp) | taker 5/perna (10 bp) | taker 5 + slip 2 (14 bp) | maker 2 (4 bp) | maker 0 | rebate −0,5 (−1 bp) | spot taker 10 (20 bp, sem funding; **todos**) |
|---|---|---|---|---|---|---|---|---|
| momentum v3 | dia | −0,216 [−0,262; −0,175] | **−0,131** [−0,175; −0,084] | −0,165 [−0,210; −0,121] | −0,080 [−0,123; −0,030] | −0,046 [−0,090; +0,006] | −0,038 [−0,081; +0,015] | −0,214 [−0,260; −0,173] |
| volume_anomaly v1 | mercado | −0,330 [−0,404; −0,261] | −0,160 [−0,213; −0,107] | −0,228 | −0,058 [−0,106; −0,010] | +0,010 [−0,039; +0,058] | +0,027 [−0,023; +0,075] | −0,329 [−0,402; −0,262] |
| mean_reversion v1 | dia | −0,123 [−0,294; +0,022] | −0,036 [−0,204; +0,112] | −0,071 | +0,017 [−0,152; +0,165] | +0,052 | +0,061 | −0,127 [−0,294; +0,019] |
| mean_reversion v6 | dia | −0,015 [−0,154; +0,178] | +0,036 [−0,104; +0,230] | +0,015 | +0,067 [−0,073; +0,262] | +0,087 | +0,092 | −0,019 [−0,157; +0,176] |
| mean_reversion v7 | dia | −0,005 [−0,132; +0,186] | +0,034 [−0,093; +0,226] | +0,018 | +0,057 [−0,070; +0,252] | +0,073 | +0,076 | −0,010 [−0,141; +0,187] |
| mean_reversion v10 | dia | −0,018 [−0,134; +0,116] | +0,020 [−0,095; +0,154] | +0,004 | +0,042 [−0,072; +0,177] | +0,058 | +0,061 | −0,021 [−0,137; +0,113] |
| mean_reversion v14 | dia | −0,020 [−0,193; +0,177] | +0,031 [−0,143; +0,231] | +0,011 | +0,062 [−0,113; +0,264] | +0,083 | +0,088 | −0,020 [−0,193; +0,178] |

**Distância até o lucro** (margem = k* − ida-e-volta do cenário, em bp; o funding já está dentro de k*):
`momentum v3` −15,5 (taker) · −9,5 (maker 2) · −5,5 (maker 0) · −4,5 (rebate); `volume_anomaly v1` −9,4 · −3,4 ·
+0,6 · +1,6; `mean_reversion v14` +6,1 · +12,1 · +16,1 · +17,1; v10 +5,2 · +11,2; v7 +8,8 · +14,8; v6 +7,0 · +13,0;
v1/v2 −4,1/−4,2 (taker) · +1,9/+1,8 (maker 2). Os cenários maker supõem execução no preço do sinal, que é o
**limite superior** (ordem passiva pode não executar, e a que executa tende a ser a pior — seleção adversa).
O spot taker 10 bp/perna (20 bp) é o próprio custo do Lab sem funding, sobre preços de perpétuo (base spot/perp não
modelada), calculado sobre **todos** os terminais. Tabela completa, com taker + slippage de todos os grupos, em `results.txt` §2.

### Por mês (prospectivo)

| versão | setembro: n · bruto · k* | outubro: n · dias · bruto · k* |
|---|---|---|
| momentum v3 | 1 543 · −0,037 · −4,5 | 130 · 7 · −0,158 · −14,2 |
| mean_reversion v1 | 351 · +0,069 · +8,0 | 26 · 4 · −0,160 · −13,8 |
| mean_reversion v6 | 246 · +0,102 · +20,3 | 11 · 4 · −0,244 · −35,8 |
| mean_reversion v7 | 235 · +0,091 · +24,0 | 10 · 4 · −0,364 · −70,1 |
| mean_reversion v10 | 308 · +0,087 · +23,1 | 30 · 5 · −0,235 · −53,6 |
| mean_reversion v14 | 202 · +0,101 · +20,0 | 11 · 4 · −0,244 · −35,8 |

Outubro tem 4–7 dias: não separa regime de ruído, mas impede ler setembro como "a" vantagem.

### Replays (histórico reprocessado de 12/06 a 09/09; não é coorte prospectiva)

A família `mean_reversion` é mais positiva no replay: nas v1–v10 com n ≥ 30, o bruto de **todos** os desfechos vai
de **+0,07 a +0,32 R** (k* sem funding +12 a +59 bp; nas v15–v19, −0,06 a +0,15 R no subconjunto com funding), com
vários IC por dia acima de zero (v2 `99fdba70` +0,235 [+0,046; +0,416], todos; v10 `d82356d9` +0,197 [+0,016;
+0,381], todos). Três motivos para não usar isto como evidência: (i) as versões foram desenhadas olhando esse
histórico; (ii) nos replays longos o funding só existe na parte final e o subconjunto com funding é **mais
favorável** que o todo — v10 `c7d138eb`: todos 798 desfechos em 89 dias, bruto +0,073 [−0,029; +0,178]; com funding
300 em 33 dias, +0,193; v1 `fa005985`: 542/83 dias +0,127 × 253/27 dias +0,225; v2 `da706026`: 302/68 +0,133 ×
175/25 +0,231 (o par de números de cada linha só vale com a sua contagem); (iii) o prospectivo, fora da amostra do
desenho, ficou em +0,04 a +0,09 R, abaixo do replay — o encolhimento clássico. Replays da `momentum` (v2–v13, n ≥ 20, todos os desfechos) têm bruto de −0,13 a +0,20 R (o
subconjunto com funding do replay v2 `7598d6c4`, 23 desfechos em 3 dias, chega a −0,28); na v11 `70f55430` (1 163
desfechos com funding) o bruto é −0,03 em junho e julho, +0,17 em agosto e +0,07 em setembro (líquido de setembro
−0,04): dependência de período, não vantagem.

### Atividade e duração

Trades por dia ativo: `momentum v3` 56; `mean_reversion` 8–14 por versão; `volume_anomaly` 600–700 (só 2–3 dias de
vida). Duração mediana: `volume_anomaly` 11 min, `momentum` 23–74 min, `mean_reversion` 67–240 min (as versões de saída
longa expiram em 240 min e a mediana encosta no teto). O custo do Lab em R acompanha a unidade de risco, não o horizonte: 0,175 R na `mean_reversion v1` (stop 1 ATR, horizonte de 4 h) contra 0,077 R na v7 (stop 2 ATR, mesmo horizonte) e 0,33 R na `volume_anomaly` (stops curtos).

### Poder para uma coorte futura (`extra.txt`)

O EP do R médio agrupado por dia (taker 5/perna) é **0,064 R** na `mean_reversion v10` (27 dias), **0,095 R** na v14
(25 dias) e **0,022 R** na `momentum v3` (30 dias); o dp por trade fica em 0,75–1,04 R. Escalando o EP por 1/√dias,
para **rejeitar média = 0 quando a média verdadeira é +0,10 R** (80 %, bilateral 5 %, aproximação normal) seriam
precisos ≈ **86 dias com trades** (v10), ≈ 123 (v7), ≈ **178** (v14); para +0,05 R, 344–711 dias. Isto **não** é o
poder de provar média > +0,10 R, supõe frequência, variância e dependência iguais às observadas e **não** inclui
paradas intermediárias: é uma referência condicional, potencialmente otimista (incerteza do custo e mudança de
regime aumentam a necessidade), não um prazo garantido. O choque comum do dia domina o EP.

## Direções para o próximo pré-registro (coorte futura)

Ordenadas por valor esperado, já com a ordem que a Astra propôs (instrumento antes da aposta; 1 e 2 podem coletar
juntos depois de congelado o protocolo). Nenhuma é estratégia nova, nenhuma muda parâmetro, e todas valem **só**
para sinais emitidos depois do registro.

1. **Instrumento de custo: medir o custo real da Binance nos instantes e mercados do Lab.** Por quê: nos grupos
   prospectivos com IC o k* fica entre −61 e +19 bp, e a decisão na família `mean_reversion` depende de a
   ida-e-volta real ficar perto de 10 bp ou passar de ~16 bp (o k* da v14). O "0,02–0,10 %" da
   [[KB-0149-o-que-a-mesa-real-ensinou]] item 23 é um intervalo de praça, não a medição nos instantes do Lab. É
   medição, não aposta: spread e livro na entrada **e** na saída (a ida-e-volta não se mede só no instante do
   sinal), preenchimento hipotético contra a abertura do minuto seguinte, em todas as versões ativas, e o custo de
   cada trade convertido em R e somado ao líquido pareado. A régua de decisão é o **custo efetivo ponderado**
   `Σ h·k / Σ h` (`sweep.effective_cost_bp`, com `h` = nocional das duas pernas por unidade de risco), comparado
   com o k*; mediana e caudas são auxiliares (51 % dos trades a 10 bp e 49 % a 30 bp dão mediana 10 e custo
   efetivo 19,8). Mata a via taker: custo efetivo medido acima do k* da linha em teste. Um teto operacional de
   15 bp pode existir como orçamento conservador, não como equivalência estatística.
2. **`mean_reversion v14` em coorte futura, com o custo medido no item 1.** Por quê: é a única família bruto-positiva
   no prospectivo e a v14 é a linha paper desde **09/09**, antes destes desfechos; escolher agora a v7 ou a v10
   "porque o k* é maior" seria escolher a melhor de ~9 saídas sobre as mesmas entradas. Ressalva: a escolha da v14
   para a `spot/1` (19/09, [[09-OPERATIONS/Diario/2026-09-19|Diário 19/09]]) já usou os seus primeiros 23 sinais
   (Σ R +14,9), que estão dentro desta coorte exposta — são duas decisões distintas, e nenhuma faz da v14 a
   "vencedora" desta varredura. Métrica primária: R médio por trade em R do Lab, com o custo medido e o funding
   gravado, IC por dia. O pré-registro tem de fixar antes: estimando, calendário de consultas (uma leitura
   intermediária em data fixa, não "a qualquer momento"), regra de futilidade e o poder do procedimento completo
   (com +0,10 R, a referência condicional é ~178 dias com trades). Mata: IC superior por dia < 0 na parada, ou a
   futilidade pré-registrada na leitura intermediária.
3. **`mean_reversion` com geometria nova fixada antes.** Por quê: o custo em R cai mecanicamente quando a unidade de
   risco cresce (v7, stop de 2 ATR: 0,077 R de custo do Lab; v1, 1 ATR: 0,175 R) — mas o stop mais largo muda
   também o bruto, e prolongar só o prazo, mantendo abertura e unidade de risco, **não** reduz o pedágio (pode até
   somar funding). A justificativa tem de ser uma **hipótese de trajetória/preço**, não economia de custo, e o padrão
   vem de comparar versões já vistas (caminho bifurcado): rank baixo, só com geometria nova e coorte futura. Mata:
   bruto ≤ 0, ou k* abaixo do custo efetivo medido no item 1.

*(07/10/2026: direções 1 e 2 executadas — instrumento medido em [[KB-0193-o-custo-binance-medido-nos-instantes-do-lab]] (custo efetivo da v14 exposta 11,6 bp todo a mercado, abaixo do k* de 16,1 bp, margem dentro do ruído) e coorte futura pré-registrada em [[Fila de Hipoteses#H-036 — `mean_reversion v14` em coorte futura, ao custo Binance medido (a v14 tem vantagem fora da amostra?)|H-036]].)*

**O que esta nota tira da mesa:** baratear não demonstra uma estratégia rentável — a `momentum` permanece negativa
em todos os cenários examinados (com IC do bruto por dia tocando zero) e a `volume_anomaly` tem vantagem bruta
pequena e incerta, consumida pelos custos positivos examinados. A H-033r e a H-035 propostas pelo Defensor seguem
válidas como medições de OI e volatilidade, mas não como caminho de lucro da `momentum` atual.

## Por que pode falhar (e o que não concluir)

- **Não concluir "a `mean_reversion` lucra com custo real".** Os cenários reprecificam entradas e saídas fixadas pelo
  Lab, em R do Lab; não demonstram preenchimento nem lucro executável na Binance. Os custos dos cenários são
  assumidos, não medidos nesta coorte. Os IC por dia contêm zero em todas as versões; outubro é negativo em todas;
  as versões sobrepostas e os replays não são replicações independentes; e a única execução real (10 trades na
  `spot/1`) ficou em −0,44 R.
- **A população admitida depende do custo.** A saída é testada em preço de mercado, mas a admissão exige
  `stop < entry_price(open, custos) < alvo1`: com outro custo, algumas entradas seriam recusadas por geometria (e
  outras aceitas). Uma ordem limite mudaria ainda quais entradas executam (seleção adversa não modelada).
- **Cenários de taxa sem spread.** "Taker 5" é só a taxa; o spread e o slippage reais entram na sensibilidade
  "taker 5 + slip 2" (2 bp/perna é **suposição**, não medição — daí a direção 2).
- **Denominador.** Todos os cenários usam a unidade de risco gravada pelo Lab (com 6 bp de entrada adversa). Usar o
  risco sem custo `O − S` explodia em 15 trades da `volume_anomaly` cuja abertura caiu a menos de 10 % do risco
  acima do stop (−4e9 R): por isso não. A diferença de escala entre as duas escolhas é de poucos pontos-base no
  denominador fora desses casos.
- **Funding.** Só 1 574 perpétuos sem funding estabelecido (fora das colunas com funding); nos prospectivos o funding
  médio fica em |Φ| ≤ 0,0022 R e não muda nenhuma conclusão.

## Segunda opinião (Astra)

Revisão do método e das candidatas em [[06-DECISIONS/Revisoes-Astra/lab-cost-sweep|lab-cost-sweep]] (fonte bruta
`.claude/state/astra-review-lab-cost-sweep.md`). Ela rodou os 14 testes, o `check.py` e o `extra.py` e reproduziu os
números. **Concorda** com a unidade de risco fixa, o k* como razão de somas, o bootstrap da razão por cluster,
funding ausente nunca zero e a coorte futura reservada. **Seis must-fix, todos aceitos e já nesta nota:** (1)
reprecificação condicionada, não contrafactual (a admissão depende do custo); (2) duas populações com as próprias
contagens — o replay v10 `c7d138eb` aparecia com +0,193 R e "89 dias", quando +0,193 é de 300 desfechos em 33 dias
(todos: +0,073); (3) a queda do custo em R vem da unidade de risco, não do horizonte (a v1 já tinha 4 h); (4) custo
efetivo ponderado `Σ h·k / Σ h`, não mediana, para a régua do instrumento (teste novo em `test_sweep.py`); (5) poder
qualificado (rejeitar zero, dias com trades, sem paradas, potencialmente otimista); (6) "não é problema de custo"
trocado por "baratear não demonstra uma estratégia rentável", com o IC do bruto da `momentum` por dia tocando zero.
Ranking trocado por sugestão dela (instrumento antes da v14). Nada rejeitado. **Rodada 2** (só leitura): 1, 4, 5 e 6 fechados; 2 e 3 ainda tinham resíduo — mercados da Tabela 1 vindos de todos os terminais com `n` da população com funding, cenário sem funding suprimido quando o subconjunto com funding não tinha IC (replay v2 `7598d6c4`), e uma frase "custo cai com o horizonte" que sobrou — mais quatro números (sobreposição 48–100 %, outubro 1–5 dias, meses da v11, ×10⁴ na fórmula de k*). Tudo corrigido nesta versão.

## Relacionados

[[KB-0149-o-que-a-mesa-real-ensinou]] (item 23, custo por praça; §5 itens 25–28) ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] (o modelo de custo do Lab e o diagnóstico em duas etapas que ela
pedia) · [[EXP-0005-momentum-paper]] · [[KB-0170-tendencia-diaria-nao-separa-os-sinais-do-lab]] ·
[[KB-0191-oi-acima-da-semana-nao-separa-os-sinais-do-lab]] (o Defensor que pediu esta varredura) ·
[[KB-0171-custo-real-da-spot-1]] · [[KB-0193-o-custo-binance-medido-nos-instantes-do-lab]] · [[Fila de Hipoteses]] · [[Mapa de Estrategias]] · [[Proximas Hipoteses]] ·
[[06-DECISIONS/Revisoes-Astra/lab-cost-sweep|revisão da Astra]] · [[11-KNOWLEDGE/Index|Conhecimento]]
