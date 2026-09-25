---
tags: [meme, pumpfun, kb, saida, risco, m4]
kb: KB-0108
data: 2026-09-16
janela_medida: 15/09 00:00 BRT – 16/09 16:30 BRT
fonte: banco da VPS (meme_features_15s, meme_features_1m, meme_trades, meme_tokens)
sql: infra/scripts/sql/research/2026-09-16-r17-q01..q07
owner: astra/quant
status: vivo
confiança: backtest do autor
lido_em: 2026-09-16
updated: 2026-09-16
tipo: leitura
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

# KB-0108 — Anatomia da morte depois da porta: o que acontece nos 5 minutos antes

Pergunta que originou a página: a [[03-TRADING/Meme/Candidatas/2026-09-16-17h|R14]] mostrou **BLUECHIP**
(116 holders, 92 compradores, 11 snipers — passa a porta inteira) terminando em **0,4 % com 25 holders**,
e a **CC** caindo de 45,6 % para 0,1 %. "Passar a porta não protegeu." Então: **dá para ver a morte chegando?**

> **Unidades e convenções.** `curve_progress_pct` é fração 0–1. Não-Mayhem = `meme_tokens.mayhem_mode IS NULL`.
> Horários BRT. "Porta calibrada" = `operator/5` em vigor: idade 30–300 s, progresso 0,05–0,50, holders ≥ 20,
> compradores ≥ 10, `sells_60s ≤ 0,6 × buys_60s`, `net_sol_flow_60s > 0`, `tape_reason IS NULL`, não-Mayhem.

## 1. O universo e o que dá para medir

### 1a. Quem passou a porta e o que aconteceu

Primeira linha de 15 s em que cada moeda satisfaz a porta = `t_porta`. Pico = maior `mcap_sol` observado
em `[t_porta, t_porta + 30 min]` (união de `meme_features_15s` e `meme_features_1m`). **Morte** = existe
observação depois do pico com `mcap_sol ≤ 50 % do pico`.

| dia | passaram a porta | **morte** | **sobrevivente** (≥ 180 s observados depois do pico, sem queda) | censurada (série acaba antes) |
|---|---|---|---|---|
| **15/09** | **879** | **317 (36,1 %)** | 279 (31,7 %) | 283 (32,2 %) |
| 16/09 (parcial, até 16:30) | 175 | 64 (36,6 %) | 64 (36,6 %) | 47 (26,9 %) |

A taxa de morte é **estável nos dois dias: ~36 %** das que passam a porta perdem metade do mcap. E entre as
que não morrem, quase nenhuma gradua (a R14 já tinha medido 0/5 na hora dela).

### 1b. A limitação honesta: a série morre antes da moeda

Depois de `t_porta`, o pareamento 15 s + 1 min cobre (15/09):

| cobertura pós-porta | moedas |
|---|---|
| mediana do intervalo observado | **291 s (~4,9 min)** |
| ≥ 5 min | 391 de 879 (44 %) |
| ≥ 10 min | 91 (10 %) |
| ≥ 25 min | 18 (2 %) |

**"Queda de 50 % em 30 min" é, na prática, "queda de 50 % dentro de ~5 min observados".** As 283 censuradas
não são sobreviventes — são moedas que saíram da fotografia. Todo número abaixo é condicionado a isso;
o viés provável é **subestimar** a mortalidade, não superestimar.

### 1c. A morte é rápida — mais rápida que a janela de 5 min do título

Segundos de `t_porta` até a morte (15/09, n = 317):

| p25 | mediana | p75 |
|---|---|---|
| **53 s** | **110 s** | 187 s |

Metade das mortes acontece em **menos de dois minutos** depois de a moeda passar a porta. Nos
sobreviventes, o pico chega ainda antes (mediana **17 s** depois da porta). Isso significa que, na prática,
**a "janela de 5 minutos antes da morte" começa antes da compra** para metade dos casos — o horizonte
utilizável para uma saída é de dezenas de segundos, não de minutos.

## 2. A trajetória: mortes versus sobreviventes na janela [−5 min, 0]

Medianas por moeda nas linhas de 15 s (t0 = morte para as mortes, pico para as sobreviventes).
15/09: 309 mortes e 262 sobreviventes têm linha de 15 s na janela.

| medida | **mortes (15/09)** | **sobreviventes (15/09)** | mortes (16/09) | sobrev. (16/09) |
|---|---|---|---|---|
| holders em t0 − 5 min | 17 | 9 | 13 | 9 |
| **holders em t0 − 60 s** | **49** | 20 | **47** | 20 |
| **holders em t0** | **17** | **30** | **24** | **29** |
| snipers (mediana) | 34 | 17 | — | — |
| compras / 60 s em [−120, −60] s | 59,3 | 23,7 | — | — |
| vendas / 60 s em [−120, −60] s | 30,5 | 12,0 | — | — |
| **fluxo líquido SOL em [−120, −60] s** | **+7,65** | +4,62 | +6,21 | +4,14 |
| **fluxo líquido SOL no último minuto** | **+3,69** | **+7,10** | +3,93 | **+11,75** |

Três leituras, e nenhuma delas é confortável:

1. **A moeda que morre é a moeda mais quente.** Um minuto antes de morrer ela tem **mais holders (49 × 20),
   mais compras (59 × 24) e mais fluxo líquido (+7,65 × +4,62 SOL)** que a sobrevivente no mesmo ponto.
   Não existe "sinal de fraqueza" a −60 s: existe sinal de **euforia**.
2. **O colapso de holders é simultâneo, não anterior.** 49 → 17 holders acontece dentro dos **últimos 60 s**,
   na mesma janela em que o mcap cai 50 %. É o bundle sendo desfeito — a assinatura da CC e da BLUECHIP.
   Como sinal de saída, chega junto com o preço; não adianta.
3. **A separação real é a derivada do fluxo.** Sobreviventes **aceleram** no último minuto (+4,62 → +7,10
   em 15/09; +4,14 → +11,75 em 16/09); mortes **desaceleram** (+7,65 → +3,69). Mas isso também só é
   mensurável na janela em que o preço já está caindo.

## 3. Os sinais, com precisão, recall e lead time

Regra de leitura: o sinal "vale" se dispara em alguma linha de 15 s dentro de `[t0 − 300 s, t0 − 60 s]`
— ou seja, **com pelo menos 60 s de antecedência**. Nas sobreviventes, o mesmo teste é feito contra o
**pico**: disparar ali é uma saída falsa, que teria cortado a moeda boa. Base 15/09: 309 mortes, 262 sobreviventes.

| sinal (a ≥ 60 s de t0) | mortes | **recall** | sobrev. | **taxa falsa** | **precisão** | lead mediano |
|---|---|---|---|---|---|---|
| `holders_rising = false` | 260 | **84,1 %** | 150 | 57,3 % | 63,4 % | 69 s |
| holders ≤ 90 % do máximo | 133 | 43,0 % | 89 | 34,0 % | 59,9 % | 71 s |
| `sells_60s > 0,6 × buys_60s` (quebra a própria porta) | 118 | 38,2 % | 58 | 22,1 % | 67,0 % | 69 s |
| **mcap ≤ 85 % do pico corrente (dd15)** | 128 | 41,4 % | 37 | 14,1 % | 77,6 % | **70 s** |
| **mcap ≤ 80 % do pico corrente (dd20)** | **107** | **34,6 %** | **20** | **7,6 %** | **84,3 %** | **70 s** |
| mcap ≤ 70 % do pico corrente (dd30) | 69 | 22,3 % | 10 | 3,8 % | 87,3 % | 69 s |
| compras/60 s ≤ 50 % do máximo | 83 | 26,9 % | 38 | 14,5 % | 68,6 % | 69 s |
| `net_sol_flow_60s < 0` | 78 | 25,2 % | 28 | 10,7 % | 73,6 % | 70 s |
| `creator_net_seller = true` | **5** | **1,6 %** | 1 | 0,4 % | 83,3 % | 66 s |
| **dd20 E razão > 0,6** (combinado) | 66 | 21,4 % | **3** | **1,1 %** | **95,7 %** | 70 s |
| união dd20 **ou** fluxo < 0 | 124 | 40,1 % | 41 | 15,6 % | 75,2 % | 70 s |
| união dd20 **ou** fluxo < 0 **ou** razão > 0,6 | 148 | **47,9 %** | 67 | **25,6 %** | 68,8 % | 68 s |

**Resposta direta à pergunta do brief: nenhum sinal atinge o alvo de "> 50 % das mortes e < 25 % das
sobreviventes" com 60 s de antecedência.** O mais perto é a **união dos três** (47,9 % / 25,6 %) — e ela
falha nos dois lados ao mesmo tempo. O que existe de aproveitável não é recall, é **precisão**:

- **dd20** (recuo de 20 % do pico corrente, na série de 15 s): pega **1 morte em 3** com **7,6 %** de falso
  positivo e **70 s** de lead. Precisão 84 %.
- **dd20 + razão de vendas acima de 0,6**: precisão **95,7 %** (66 mortes contra 3 sobreviventes), mas só
  1 morte em 5.

Replicação no dia seguinte (16/09, n = 64 / 64): **dd20 = 43,8 % das mortes contra 9,4 % das sobreviventes**,
lead mediano **95 s**; dd20 + razão = 14 contra 2. Mesma ordem de grandeza, mesmo sinal ganhador.

### 3a. O criador não é o assassino

`creator_net_seller` dispara antes da morte em **5 de 309 mortes (1,6 %)**. Nas apostas do dia, a saída
`creator_dump` fechou **9 de 110** com média −0,40 R ([[03-TRADING/Meme/Apostas-tracadas/Leitura-2026-09-16|Leitura 16/09]]).
As duas medidas concordam: **o dump de criador é um modo de morte raro** — e, quando dispara, dispara
tarde. A morte típica desta amostra não tem criador vendendo.

### 3b. A fita: não há uma baleia, há debandada

Amostra com cobertura de `meme_trades` na janela (só **36 de 200** mortes e 51 de 200 sobreviventes têm fita —
a cobertura da fita é o gargalo, o mesmo buraco do `swap-api.pump.fun` da R14):

| medida na janela [−5 min, 0] | mortes (n=36) | sobreviventes (n=51) |
|---|---|---|
| vendas (SOL, mediana) | 26,63 | 23,37 |
| compras (SOL, mediana) | 36,30 | 33,53 |
| vendedores distintos | 51 | 38 |
| **fatia dos 3 maiores vendedores** | **29,7 %** | 36,3 % |
| fatia dos 3 maiores vendedores até −60 s | 39,6 % | 44,2 % |
| razão venda/compra até −60 s | 0,739 | 0,614 |

**A concentração de venda é MENOR nas mortes que nas sobreviventes** (29,7 % × 36,3 %). Isto refuta a
hipótese "3 carteiras despejam e matam": a morte é **51 vendedores distintos saindo ao mesmo tempo** —
uma debandada, não um despejo. É coerente com a KB-0103, que já tinha medido o maior *comprador* em 8–11 %
nas moedas da R14: a compra era dispersa de verdade, e a venda também é.

## 4. Contra a linha de tendência (`line_broken`) medida hoje

A saída por linha usa `meme_features_1m.distance_to_support_pct < 0` com `line_reason IS NULL`. Medida
contra os mesmos t0 (15/09):

| | mortes (317) | sobreviventes (279) |
|---|---|---|
| têm linha utilizável na janela | 162 (51 %) | 80 (29 %) |
| a linha rompe na janela | 113 (35,6 %) | 48 (17,2 %) |
| **lead mediano do rompimento** | **19 s** | 47 s |
| rompe com **≥ 60 s** de antecedência | **18 (5,7 %)** | 21 (7,5 %) |

**A linha sai depois.** Lead mediano de **19 s** contra os **70 s** do dd20; e ela só consegue avisar com
≥ 60 s em **5,7 %** das mortes, contra 34,6 % do dd20. Dois motivos estruturais, e os dois são de relógio:
a linha vive na série de **1 minuto** (não pode ter lead melhor que a grade de 60 s) e ela exige suporte
formado (`line_reason IS NULL` em apenas metade das mortes). Isso é exatamente o que a
[[03-TRADING/Meme/Apostas-tracadas/Leitura-2026-09-16|leitura dos traçamentos]] viu pelo outro lado:
`line_broken` fechou 49 de 110 apostas com R **mediano +0,088** — ela não é ruim, ela é **tardia e morna**;
as 6 que ficaram ≤ −0,50 R (ALICE, −0,90 R) são precisamente os buracos em que 19 s de aviso não bastam.

**Ordem medida:** `dd20 (−70 s)` → `razão de vendas > 0,6 (−69 s)` → `colapso de holders (−0 a −60 s)` →
`linha rompida (−19 s)` → morte.

## 5. Recomendação para as saídas do estágio 1 (0,05 SOL) — 4 linhas

1. **Registrar um braço de saída `dd20_15s`**: vender tudo quando `mcap_sol` da série de 15 s recuar **20 %
   do máximo desde a entrada** — 34,6 % (15/09) e 43,8 % (16/09) das mortes pegas, **7,6–9,4 %** de saída
   falsa, **70–95 s** antes da queda de 50 %, e **três a quatro vezes o lead da linha de tendência**.
2. **Segundo braço, mais duro, para o resto: `dd20 + sells_60s > 0,6 × buys_60s`** — precisão **95,7 %**
   (66 mortes × 3 sobreviventes); use-o como gatilho de saída **imediata e integral**, sem esperar a linha.
3. **Encurtar o `time_stop` do estágio 1 para ~180 s**: a mediana de porta→morte é **110 s** e o p75 é 187 s;
   segurar além disso é ficar exposto ao regime em que 36 % das aprovadas perdem metade do mcap.
4. **Não gastar braço em criador nem em concentração de fita**: `creator_net_seller` avisa em 1,6 % das
   mortes e os 3 maiores vendedores são **menos** concentrados nas mortes (29,7 %) que nas sobreviventes
   (36,3 %) — a morte é debandada de ~50 carteiras, não despejo de baleia.

> **Nada aqui é ligado à mão.** Esta página é insumo para um **braço de saída pré-registrado** (conjunto
> novo com versão própria, replay dos 90 d e prospectiva em paralelo, conforme o protocolo de validação em
> um dia). Os números de §3 são medidos com a série que existe — e a §1b diz que ela dura ~5 min.

## Ligações

[[03-TRADING/Meme/Candidatas/2026-09-16-17h|Candidatas R14 (BLUECHIP, CC)]] ·
[[03-TRADING/Meme/Apostas-tracadas/Leitura-2026-09-16|Traçamentos 16/09 (line_broken, max_loss)]] ·
[[11-KNOWLEDGE/KB-0101-snipers-e-graduacao-a-medida-com-n-grande|KB-0101 (snipers)]] ·
[[11-KNOWLEDGE/KB-0103-clones-fundo-com-preco-forjado-assinatura-e-custo|KB-0103 (forjada, concentração)]] ·
`infra/scripts/sql/research/2026-09-16-r17-q01..q07`
