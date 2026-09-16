---
tags: [knowledge, nota, meme, pumpfun, saida, drawdown, R, backtest, m5]
kb: KB-0110
tema: a saida por recuo de 20 % do pico na serie de 15 s (E20) paga em R nas entradas da porta atual?
data: 2026-09-16
janela_medida: 12/09 00:00 - 16/09 ~17:00 BRT
fonte: banco da VPS (meme_features_15s, meme_features_1m, meme_tokens), SELECT-only
sql: infra/scripts/sql/research/2026-09-16-r20-q01-entradas-porta-atual.sql, ...-r20-q02-serie-15s-pos-entrada.sql
script: infra/scripts/research/2026-09-16-r20-sim-saidas-15s.py
evidencia: medicao propria, 322 entradas (291 com serie de 15 s), 5 dias (12 e 16/09 parciais)
hipotese_testavel: sim
astra: nao consultada (pesquisa quant)
confiança: backtest do autor
lido_em: 2026-09-16
owner: astra-quant
status: vivo
updated: 2026-09-16
---

# KB-0110 — Saída por drawdown de 20 % na série de 15 s: R simulado das 4 variantes

A [[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] mediu o **dd20** (mcap da série de 15 s
≤ 80 % do pico corrente) como o melhor **detector** de morte: precisão 84 %, recall 35 %, lead 70 s — e
**3–4× o lead da linha de tendência** (19 s). Detector bom não é saída boa. Esta página responde à pergunta
seguinte: **armar E20 muda o R das entradas da porta atual?**

> **Unidades.** `curve_progress_pct` é fração 0–1; `mayhem_mode` é texto (não-Mayhem = `mayhem_enabled = false`
> **e** `mayhem_mode IS NULL`). Horários BRT. R = `(múltiplo líquido − 1) / 0,5`, taxa **1,75 % por perna**,
> unidade de risco = o piso de −50 % (metodologia literal do
> [[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] §3 / `r4-q05`).

## 1. Como foi medido

### 1a. Universo, entrada e as cinco saídas

- **Porta atual** (KB-0099 `operator/5` + piso de snipers da
  [[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] §3): foto de 15 s com `age_s` 30–300 s,
  curva viva, não-Mayhem, `curve_progress_pct` **0,05–0,50**, fita presente (`tape_reason IS NULL`),
  `net_sol_flow_60s > 0`, `dev_share ≤ 0,10`, pedigree do KB-0099, **`snipers ≥ 21`**. `t0` = a **primeira foto que
  passa** a porta (convenção do `r4-q05`: a mesa avalia toda foto, não só a primeira do dia).
- **Entrada** = a primeira **barra de 1 min** depois de `t0` (até 5 min) com `holders ≥ 20`, `unique_buyers ≥ 10`,
  `sells_1m/buys_1m ≤ 0,6`. **Fill no mcap observado** da barra (`base`).
- **Saída simulada na série de 15 s** (não na de 1 min), horizonte 30 min, stop preenchido no **mcap observado**
  da foto, pico sempre calculado **até a foto anterior** (causal — nenhuma regra lê a própria foto de saída):

| braço | regra |
|---|---|
| **S0** (atual) | alvo 3×; trailing 35 % armado depois de 1,5×; piso −50 %; tempo 30 min |
| **S1** | S0 + **E20 desde a entrada** |
| **S2** | S0 + E20 **armado só depois de +30 %** (pico ≥ 1,3× base) |
| **S3** | S0 + E20 **só se `sells_60s > 0,6 × buys_60s`** na mesma foto (o combinado de 95,7 % de precisão da KB-0108) |
| **S4** | S0 com o trailing 35 % **substituído por E20 depois de 1,5×** |

**322 entradas** em 5 dias (12/09: 11 · 13/09: 65 · 14/09: 79 · 15/09: 121 · 16/09: 15 — 12 e 16/09 parciais);
**31 sem nenhuma foto de 15 s depois da entrada** ficam de fora; **n = 291** em todas as variantes (mesma coorte,
comparação pareada).

### 1b. A limitação que domina tudo (leia antes de olhar a tabela)

Cobertura da série de 15 s **depois da entrada**: p25 **90 s**, mediana **162 s**, p75 **206 s**; só **10 de 291**
chegam a 5 min e **nenhuma** a 30 min. Ou seja: **"tempo 30 min" é, na prática, "até a série acabar" — 2,7 minutos
medianos**, e 226 das 291 apostas de S0 fecham assim. É o mesmo buraco da KB-0108 §1b, agravado por medir
**depois da entrada** e não depois da porta. Consequências honestas:

1. O nível absoluto de R (todas as variantes entre −0,00 e +0,02 médio) **não é o R da mesa** — é o R de uma
   janela de ~2,7 min com saída a mercado no fim.
2. E20 é o **único** braço que tem tempo de disparar nessa janela; o trailing 35 % e o alvo 3× quase não têm.
   O teste é, portanto, **favorável ao E20 por construção**. Ele ainda assim não ganha de forma significativa.

## 2. As cinco variantes, 12–16/09 (n = 291 em todas)

| var | n | R médio | R mediano | **R total** | ≥ +2 R | ≤ −0,5 R | tempo médio (s) | saídas por E20 | IC 95 % do R médio |
|---|---|---|---|---|---|---|---|---|---|
| **S0** (atual) | 291 | +0,010 | −0,098 | **+2,9** | 4,8 % | 31,6 % | 143 | 0 (0,0 %) | [−0,05; +0,07] |
| **S1** (E20 desde a entrada) | 291 | +0,004 | **−0,157** | +1,1 | 4,5 % | **28,2 %** | 103 | **161 (55,3 %)** | [−0,06; +0,05] |
| **S2** (E20 após +30 %) | 291 | −0,000 | −0,070 | −0,1 | 4,5 % | 30,9 % | 133 | 52 (17,9 %) | [−0,08; +0,08] |
| **S3** (E20 + razão > 0,6) | 291 | +0,010 | −0,123 | +2,9 | 4,5 % | 31,6 % | 120 | 96 (33,0 %) | [−0,01; +0,04] |
| **S4** (E20 após 1,5×, sem trailing) | 291 | **+0,021** | **−0,069** | **+6,2** | 4,8 % | 31,3 % | 139 | 33 (11,3 %) | [−0,03; +0,08] |

Diferença **pareada** contra S0 (bootstrap de blocos de dia, 5 blocos, 10 mil reamostragens):

| var − S0 | delta médio | IC 95 % | melhora | piora | igual |
|---|---|---|---|---|---|
| S1 − S0 | **−0,0061 R** | [−0,064; +0,031] | 66 | 44 | 181 |
| S2 − S0 | −0,0102 R | [−0,071; +0,040] | 17 | 18 | 256 |
| S3 − S0 | +0,0002 R | [−0,032; +0,043] | 43 | 31 | 217 |
| **S4 − S0** | **+0,0115 R** | **[−0,003; +0,027]** | 11 | 10 | 270 |

**Nenhum IC exclui o zero.** O único que chega perto é **S4**, e o preço disso é tocar só 21 das 291 apostas.

Motivos de saída em S0: 226 `tempo` · 59 `stop` · 6 `alvo_3x`. A qualidade do gatilho E20 quando ele dispara:

| var | saídas por regra (não por fim de série) | delas por E20 | **R médio das saídas por E20** |
|---|---|---|---|
| S1 | 166 | 161 | **−0,453** |
| S2 | 92 | 52 | −0,016 |
| S3 | 133 | 96 | −0,423 |
| **S4** | 81 | 33 | **+0,359** |

Esta é a tabela que explica todo o resto: **E20 armado cedo corta no vermelho** (−0,45 R médio em S1 e S3) e
**E20 armado depois de 1,5× corta no verde** (+0,36 R em S4). O dd20 é um detector de morte, mas **na entrada a
morte é indistinguível do ruído de −20 %** — 20 % de recuo a partir do próprio preço de entrada é menos que a
largura de uma vela de 15 s nesta coorte.

## 3. A cauda perdida: as 10 melhores de S0 sob cada variante

| moeda | dia | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|---|
| TA | 12/09 | +3,79 | +3,79 | +3,79 | +3,79 | +3,79 |
| DOPPLER | 13/09 | +3,79 | +3,79 | +3,79 | +3,79 | +3,79 |
| MIMETICS | 15/09 | +3,79 | +3,79 | +3,79 | +3,79 | +3,79 |
| XMONKEY | 15/09 | +3,79 | +3,79 | +3,79 | +3,79 | +3,79 |
| SILKROAD | 15/09 | +3,79 | +3,79 | +3,79 | +3,79 | +3,79 |
| **HOM** | 16/09 | **+3,79** | **−0,02** | **−0,02** | **+3,79** | **+3,79** |
| EULER | 14/09 | +2,99 | +2,99 | +2,99 | +2,99 | +2,99 |
| superdark | 15/09 | +2,73 | +2,73 | +2,73 | +2,73 | +2,73 |
| ElonMusk | 14/09 | +2,58 | +2,58 | +2,58 | +2,58 | +2,58 |
| solhouse | 14/09 | +2,57 | +2,57 | +2,57 | +2,57 | +2,57 |
| **soma top-10** | | **+33,62** | **+29,81** | **+29,81** | **+33,62** | **+33,62** |

**Sim, existe perda de cauda, e ela é KITE-like.** HOM (16/09) faz +3,79 R em S0 e **−0,02 R** em S1 e S2: o E20
disparou num recuo intermediário e entregou o resto da subida. Uma moeda em 291 vale **3,81 R** — mais que o
**R total inteiro** de S0 (+2,9) e mais de metade do de S4 (+6,2). É o mesmo desenho que a
[[03-TRADING/Meme/Apostas-tracadas/Leitura-2026-09-16|leitura de 16/09]] viu no `line_broken` cortando KITE a
+0,38 R quando o alvo pagava +8,96 R: **saída rápida é barata em mediana e cara na cauda.**

**S3 e S4 não perdem nada da cauda** (+33,62, idêntico a S0): exigir razão de vendas > 0,6 (S3) ou 1,5× de ganho
prévio (S4) é exatamente o que impede o gatilho de morder a moeda que ainda está subindo.

## 4. R total por dia (o mesmo n por dia nas cinco variantes)

| dia | n | S0 | S1 | S2 | S3 | S4 |
|---|---|---|---|---|---|---|
| 12/09 (parcial) | 11 | −2,72 | −0,43 | −0,49 | −0,72 | −1,88 |
| 13/09 | 65 | +0,95 | −1,41 | −0,92 | −0,91 | +0,82 |
| 14/09 | 79 | +6,25 | +6,13 | +8,87 | +3,14 | +8,35 |
| 15/09 | 121 | −2,77 | −1,01 | −4,45 | −0,09 | −1,70 |
| 16/09 (parcial) | 15 | +1,17 | −2,17 | −3,10 | +1,52 | +0,65 |

S4 fica ≥ S0 em **quatro** dos cinco dias (perde só em 12/09, n = 11); S1 perde em três, S2 em três. Nenhuma
variante é positiva em mais de três dias — é o mesmo regime de *R total dominado por um punhado de apostas* da
KB-0102.

## 5. Resposta direta

- **Quem ganha em R total E em mediana: S4** (+6,2 R total e −0,069 mediano, contra +2,9 e −0,098 de S0) — e é a
  **única** das quatro que ganha nos dois critérios ao mesmo tempo. Mas o IC pareado **[−0,003; +0,027] inclui o
  zero**: é um sinal, não uma prova.
- **Quem perde a cauda (KITE-like): S1 e S2** — as duas transformam HOM de +3,79 R em −0,02 R, **−3,81 R de cauda**
  (−11 % do top-10) para comprar uma redução de 3,4 pp em `≤ −0,5 R` (S1). Não compensa.
- **S3 é neutro** (+0,0002 R pareado): a precisão de 95,7 % da KB-0108 §3 é precisão **de detectar a morte**, não
  de melhorar o R — quando a razão já passou de 0,6 com dd20, o preço em que se sai é aproximadamente o mesmo em
  que o piso de −50 % sairia poucos segundos depois, dentro da janela de 2,7 min que a série cobre.
- **E20 desde a entrada não serve como stop inicial.** Ele fecha 55 % das apostas a **−0,45 R médio**: −20 % do
  preço de entrada é ruído, não morte.

## 6. Recomendação — 4 linhas

1. **Registrar `dd20_after_15x` (o braço S4) como conjunto de saída novo e versionado**, nunca como ajuste do
   conjunto vivo: alvo 3×, piso −50 %, tempo, e **E20 no lugar do trailing 35 % depois de 1,5×**. É o único braço
   que melhora R total (+6,2 × +2,9) e mediana (−0,069 × −0,098) **sem tocar na cauda** (+33,62 intacto).
2. **Não armar E20 desde a entrada nem após +30 % (S1/S2): reprovados aqui** — −0,006 e −0,010 R pareados e
   **−3,81 R de cauda** cada um (HOM de +3,79 para −0,02), a repetição exata do erro do `line_broken` em KITE.
3. **S3 (dd20 + razão > 0,6) fica como telemetria, não como braço**: R pareado +0,0002 — registrar o disparo no
   traçamento para medir o lead em produção, sem autorizar venda por ele.
4. **Nada disto é ligado à mão.** A janela medida cobre **162 s medianos** depois da entrada (10 de 291 chegam a
   5 min, nenhuma a 30 min): S4 entra no protocolo de validação em um dia (replay de 90 d + estresse + replicação,
   prospectiva em paralelo) e **só depois** de a retenção da série de 15 s cobrir os 30 min do horizonte — sem
   isso, o teste do trailing contra o E20 é literalmente não observado.

## Ligações

[[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108 (dd20 como detector)]] ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099 (metodologia de R)]] ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102 (piso de snipers ≥ 21)]] ·
[[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] ·
[[11-KNOWLEDGE/KB-0107-celula-lenta-como-porta-da-mesa|KB-0107]] ·
[[03-TRADING/Meme/Apostas-tracadas/Leitura-2026-09-16|Traçamentos 16/09 (line_broken cortou KITE)]] ·
`infra/scripts/sql/research/2026-09-16-r20-q0{1,2}-*.sql` · `infra/scripts/research/2026-09-16-r20-sim-saidas-15s.py`
