---
tags: [knowledge, nota, meme, pumpfun, porta, drawdown, entrada, real-sol, m4]
tema: memecoin / pump.fun / "não entrar depois da queda" — o drawdown recente de `real_sol_reserves` como FILTRO DE ENTRADA
fonte: banco da VPS (meme_features_15s, meme_features_1m, meme_curve_snapshots, meme_tokens), 12–16/09/2026 BRT
fonte_url: https://github.com/aquecerandroi-oss/project-hunter/blob/main/infra/scripts/sql/research/2026-09-16-r42-q01-drawdown-na-entrada-e-r.sql
lido_em: 2026-09-16
evidencia: medição própria (SQL em infra/scripts/sql/research/2026-09-16-r42-q0{1,2,3}-*.sql; 615 entradas da porta atual em 5 dias, 613 com R)
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
veredito: em_curso
proximo_passo: —
classe_de_perda: —
mercado: meme
---

# KB-0118 — Não entrar depois da queda: o drawdown recente como filtro de entrada

**O fato que abriu a nota (R41, 16/09).** A primeira compra real da mesa (TAXCOIN, **21:31:28 BRT**) saiu
**71 s depois de a curva perder 24 dos 29,6 SOL reais** (−82 %); a feature de 15 s de 21:31:19 já dizia
`unique_buyers_60s = 3` e `net_sol_flow_60s = −1,00`; a saída foi `creator_dump` 48 s depois, −0,0098 SOL.
A porta e a admissão **não têm nenhum critério de "queda recente"**. A
[[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] já tinha medido o recuo de 20 % do pico
na série de 15 s como o melhor sinal de morte (precisão 84,3 %, lead 70 s) — mas **só para saída**.
Pergunta desta nota: **como filtro de ENTRADA, "não entrar se a moeda perdeu ≥ X % do pico de
`real_sol_reserves` nos últimos N s" separa R?**

## 0. Método (escrito antes de olhar o resultado)

- **Coorte**: as entradas da **porta atual** reconstruída sobre a série de 15 s (idade 30–300 s,
  progresso 0,05–0,50 **fração**, fita presente, fluxo > 0, dev ≤ 0,10, **snipers ≥ 21**
  ([[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]]), holders ≥ 20,
  compradores únicos ≥ 10, `sells_60s ≤ 0,6 × buys_60s`, pedigree, não-Mayhem
  (`mayhem_enabled = false` **e** `mayhem_mode IS NULL`)). Entrada = **primeira** foto que passa tudo.
- **R**: reuso literal do motor da [[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]]
  (`r4-q05`) — alvo 3×, trailing 35 % depois de 1,5×, piso −50 %, taxa 1,75 % por perna, fill pessimista no
  mcap observado, `R = (múltiplo líquido − 1)/0,5`. **Duas mudanças declaradas**: horizonte **30 min** (o do
  conjunto vivo, [[05-EXPERIMENTS/EXP-M10-compradores-25|EXP-M10]]) e o piso de snipers no lugar do teto.
- **Drawdown**: `real_sol_reserves` **não existe** em `meme_features_15s`; vem de `meme_curve_snapshots`
  (a cadeia — [[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115]]). Pico = `max` em
  `[t0 − 300 s, t0]`; atual = última foto de curva ≤ `t0`; `dd = 1 − atual/pico`; `t_pico` = `t0` − hora do pico.
  A defasagem entre a foto de curva e `t0` é **mediana 12 s, p90 14 s, máx 16 s** — o filtro lê algo **mais
  fresco** que a janela de 60 s da fita, e é aí que mora o mecanismo.
- **Cobertura**: 12–16/09 BRT, **615 entradas** (16, 118, 174, 232, 75 por dia), 613 com R e **todas** com
  `dd` — nenhuma perda por falta de foto de curva. IC 95 % por **bootstrap de blocos de dia** (5 blocos).

## 1. Onde o R está, por faixa de drawdown × recência do pico (613 entradas, 5 dias)

| faixa `dd` | recência do pico | n | R médio | R mediano | ≥ +2 R | ≤ −0,5 R | R total |
|---|---|---:|---:|---:|---:|---:|---:|
| **0–5 %** | **total** | **255** | **−0,007** | −0,875 | 15,3 % | 62,7 % | −1,9 |
| | ≤ 60 s | 252 | −0,001 | −0,875 | 15,5 % | 62,7 % | −0,2 |
| **5–20 %** | **total** | **105** | **−0,022** | −0,605 | 10,5 % | 53,3 % | −2,3 |
| | ≤ 60 s | 96 | −0,014 | −0,600 | 10,4 % | 53,1 % | −1,3 |
| **20–50 %** | **total** | **158** | **+0,012** | −0,670 | 12,0 % | 55,7 % | +1,9 |
| | ≤ 60 s | 124 | +0,026 | −0,719 | 12,9 % | 60,5 % | +3,2 |
| | 60–180 s | 24 | −0,017 | −0,163 | 8,3 % | 33,3 % | −0,4 |
| **> 50 %** | **total** | **95** | **−0,120** | −0,481 | 6,3 % | 45,3 % | **−11,4** |
| | **≤ 60 s** | **73** | **−0,305** | −0,565 | **4,1 %** | 54,8 % | **−22,3** |
| | 60–180 s | 17 | **+0,566** | −0,069 | 17,6 % | 17,6 % | +9,6 |
| | > 180 s | 5 | +0,253 | +0,371 | 0 % | 0 % | +1,3 |

IC 95 % do R médio por faixa (blocos de dia): 0–5 % [−0,239; +0,083] · 5–20 % [−0,248; +0,195] ·
20–50 % [−0,107; +0,066] · > 50 % [−0,247; +0,002]. Por dia, o R médio da faixa > 50 % é
−0,35 / −0,28 / +0,07 / −0,13 / −0,10 (12 → 16/09).

**Três leituras:**

1. **Drawdown moderado não é veneno.** As faixas 0–5 %, 5–20 % e 20–50 % têm R médio dentro de ±0,03 uma da
   outra e IC que se sobrepõem inteiramente. **A faixa 20–50 % é a melhor das três.** Metade das entradas da
   porta já acontece com `dd` mediano de **13,4 %** (q75 = 35,2 %) — comprar "no vermelho recente" é o **normal**
   deste funil, não a exceção.
2. **O veneno é a queda grande E fresca.** `dd > 50 %` com pico a **≤ 60 s** é a única célula claramente ruim:
   **−0,305 R** em 73 apostas, com a taxa de cauda desabando de ~13 % para **4,1 %** (2 alvos de 3× em 73) e
   78 % das saídas por tempo — a moeda não morre, ela **apaga**. É negativa nos **5 dias**
   (−0,35 / −0,46 / −0,07 / −0,40 / −0,23).
3. **A mesma queda, se já é velha, é boa.** `dd > 50 %` com pico a 60–180 s dá **+0,566 R** (n = 17) e ruína de
   17,6 %. Isso é o retrato do reset: quem já caiu **e parou de cair** é a compra barata. O filtro só pode
   olhar para a queda **em curso**; com n = 17 isso é indício, não achado.

## 2. As nove variantes: "recusar se `dd ≥ X` com pico nos últimos N s"

Δ contra a coorte inteira (R médio **−0,022** sem filtro; 613 apostas; 122,6/dia de teto in-sample):

| X | N | fica | cadência | R médio | **Δ R** | IC 95 % (blocos de dia) | P(Δ > 0) | LOO (Δ mínimo) | coorte cortada |
|---|---|---:|---:|---:|---:|---|---:|---|---|
| 20 % | 60 s | 416 (67,9 %) | 83/dia | +0,013 | +0,035 | [−0,002; +0,074] | 0,97 | +0,020 | n=197, −0,097 R |
| **35 %** | **60 s** | **499 (81,4 %)** | **100/dia** | **+0,023** | **+0,045** | **[+0,036; +0,064]** | **1,00** | **+0,041** | n=114, **−0,220 R** |
| **50 %** | **60 s** | **540 (88,1 %)** | **108/dia** | **+0,016** | **+0,038** | **[+0,022; +0,054]** | **1,00** | **+0,031** | n=73, **−0,305 R** |
| 35 % | 120 s | 478 (78,0 %) | 96/dia | −0,003 | +0,019 | [−0,002; +0,055] | 0,95 | +0,011 | n=135, −0,089 R |
| 50 % | 120 s | 529 (86,3 %) | 106/dia | +0,001 | +0,024 | [+0,011; +0,033] | 1,00 | +0,020 | n=84, −0,171 R |
| 20 % | 120 s | 389 (63,5 %) | 78/dia | −0,017 | +0,005 | — | — | — | n=224, −0,030 R |
| 20 % | 300 s | 360 (58,7 %) | 72/dia | −0,011 | +0,011 | — | — | — | n=253, −0,037 R |
| 35 % | 300 s | 458 (74,7 %) | 92/dia | −0,008 | +0,014 | — | — | — | n=155, −0,063 R |
| 50 % | 300 s | 518 (84,5 %) | 104/dia | −0,004 | +0,018 | [+0,001; +0,033] | 0,99 | +0,013 | n=95, −0,120 R |

**O que a tabela diz, sem enfeite:**

- **N manda mais que X.** Toda variante com **N = 60 s** ganha das suas irmãs de 120 s e 300 s com o mesmo X.
  Alargar a janela do pico **não** corta mais lixo: corta as moedas que já caíram e se estabilizaram — exatamente
  a célula de +0,566 R do §1. `N = 300 s` com `X = 20 %` chega a jogar fora **41 %** da cadência por **+0,011 R**.
- **X = 35 % e X = 50 % com N = 60 s empatam na prática** (+0,045 e +0,038, IC sobrepostos). O X = 50 % corta
  **metade** das moedas (73 × 114) para quase o mesmo Δ — é o mais **cirúrgico** (coorte cortada a −0,305 R) e
  o que menos mexe na cadência (−11,9 %). O X = 35 % pega mais lixo, com menos densidade por aposta cortada
  (coorte cortada negativa nos 5 dias também: −0,52 / −0,25 / −0,17 / −0,15 / −0,29).
- **Nada disso transforma a porta em máquina.** O conjunto sai de **−0,022** para **+0,016 / +0,023 R** por aposta:
  de perdedora para **empatada**. Com 0,05 SOL e `1 R = 0,5` do tamanho, +0,02 R × 100 apostas/dia ≈ **0,05 SOL/dia**.
  Isto é higiene de entrada, **não** é vantagem nova, e não muda uma linha da conta da
  [[11-KNOWLEDGE/KB-0090-a-meta-em-dinheiro|meta de R$ 9 mil/dia]].
- **Honestidade de seleção:** nove variantes medidas na mesma amostra que as escolhe
  ([[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]]). O que sustenta as duas
  finalistas não é o Δ (pequeno): é a **coorte cortada ser negativa nos 5 dias separados** e a taxa de cauda
  cair para 4,1 % nela — dois fatos que não dependem da escolha fina do limiar.

## 3. As quatro da noite de 16/09 (`r42-q03`)

Drawdown na hora da **primeira ordem** de cada moeda (pico nos 300 s anteriores, cadeia):

| moeda | ordem BRT | pico rsol | rsol na ordem | **dd** | **t_pico** | máx nos 30 min | cortada por… |
|---|---|---:|---:|---:|---:|---:|---|
| CELINE | 19:48:43 | 14,343 | 14,001 | **2,4 %** | 33 s | 27,99 (**2,00×**) | **nenhuma variante** (certo) |
| funemployed | 20:45:48 | 26,454 | 14,275 | **46,0 %** | 50 s | 26,43 (1,85×) | X = 20 % e 35 % (erro) |
| PPC | 21:14:13 | 14,421 | 5,648 | **60,8 %** | **218 s** | 10,08 (1,78×) | só N = 300 s (erro) |
| **TAXCOIN** | **21:31:28** | **29,638** | **5,252** | **82,3 %** | **67 s** | 23,14 (4,41×) | **N = 120 s e 300 s** |

**E aqui vem o problema honesto desta nota.** Com `N = 60 s`, o `t_pico` da TAXCOIN é **67 s** — **a variante
finalista não a pegaria, por 7 segundos**. Quem a pega é `X = 50 % / N = 120 s` (Δ +0,024) ou `N = 300 s`
(Δ +0,018), e essas mesmas variantes **também cortam a PPC**, que subiu 1,78×. A cadência da foto de curva
(~12 s) faz 67 s ser praticamente indistinguível de 60 s: qualquer braço escrito **por causa da TAXCOIN**
precisa de **N ≈ 120 s** — e paga a PPC como preço.

As três "ruins" da noite **dobraram o SOL real depois**, e o filtro trata cada uma de um jeito: CELINE passa
limpa em tudo (o erro dela foi `creator_flow_unknown`, não queda), funemployed é **cortada por engano** por
X = 35 %, PPC só é cortada por engano se N ≥ 300 s. **O filtro não conserta a noite de 16/09**: ele corta a
compra que perdeu dinheiro de verdade (com N = 120 s) e, dependendo do X, corta junto uma que dobrou.

## 4. Por que isso não é redundante com o que a porta já tem

Todas as 73 apostas da célula ruim **passaram** `net_sol_flow_60s > 0`, `sells_60s ≤ 0,6 × buys_60s` e
`holders ≥ 20` na mesma foto — por construção, senão não seriam entradas. Não há contradição: as features da
fita agregam **60 s** e chegam com atraso próprio, enquanto a foto de curva tem **12 s** de defasagem mediana.
O filtro não é "mais uma medida de fluxo": é a **mesma informação, mais fresca**, lida direto da cadeia. É a
versão de entrada do que a [[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] achou para a
saída — e, como lá, o que ele entrega é **precisão**, nunca recall.

## 5. Limites declarados

(i) 5 dias, dois parciais (12/09 com 16 entradas; 16/09 medido às 23h BRT); (ii) entrada no mcap da foto, sem
atraso de decisão ([[11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes|KB-0087]]) — e o filtro é
justamente sobre frescor, então o efeito real pode ser **maior** que o medido; (iii) saída em barras de 1 min,
enquanto a mesa decide a cada 15 s; (iv) sem TTL, dedup nem cooldown: 122,6 entradas/dia é **teto**, não
cadência esperada; (v) a célula `dd > 50 %` a 60–180 s (+0,566 R) tem n = 17 e **não** autoriza nenhum braço de
"comprar a queda parada"; (vi) unidades: `real_sol_reserves` em SOL, `curve_progress_pct` fração 0–1,
`mayhem_mode` texto.

## 6. O que vai para pré-registro

[[05-EXPERIMENTS/EXP-M13-sem-entrar-apos-queda|EXP-M13]] com **X = 50 %, N = 60 s** — a variante cirúrgica:
corta 11,9 % da cadência, a coorte cortada é negativa nos 5 dias, e é a que menos arrisca cortar cauda.
Previsão congelada: **`descartar`**. O que **não** vai: N = 300 s (paga cadência por nada), "comprar a queda
velha", e qualquer mudança simultânea em outro critério.

## Ligações

[[11-KNOWLEDGE/KB-0108-anatomia-da-morte-depois-da-porta|KB-0108]] (o mesmo sinal, na saída) ·
[[11-KNOWLEDGE/KB-0099-por-que-a-mesa-nao-propoe-e-quanto-custa-cada-criterio|KB-0099]] §3 (motor de R) ·
[[11-KNOWLEDGE/KB-0102-snipers-pagam-em-R-ou-so-em-graduacao|KB-0102]] · [[11-KNOWLEDGE/KB-0106-snipers-e-graduacao-organica|KB-0106]] ·
[[11-KNOWLEDGE/KB-0115-volta-ao-piso-e-real-ou-artefato|KB-0115]] · [[11-KNOWLEDGE/KB-0092-o-modelo-pre-registrado-que-morreu-no-holdout|KB-0092]] ·
[[03-TRADING/Meme/Candidatas/2026-09-16-21h40-brt|R41]] ·
`infra/scripts/sql/research/2026-09-16-r42-q01-drawdown-na-entrada-e-r.sql` · `…-r42-q02-faixas-de-drawdown-x-recencia.sql` ·
`…-r42-q03-as-quatro-da-noite.sql`
