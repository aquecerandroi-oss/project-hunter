---
tags: [experimento, mean-reversion, custo, piso-de-atr, populacao]
updated: 2026-09-08
status: em-andamento
owner: quant-engineer
exp: EXP-0019
strategy: "mean_reversion"
version: "mean_reversion v8 (novo braço) + v1 (braço por identidade)"
result: negativo
evaluable: 70
days: 11
last_eval: "2026-09-08"
---

# EXP-0019 — o piso de ATR%: comprar população de volta com o porteiro e pagar o pedágio com a largura do stop

> Rascunho para a Sexta-feira arquivar em `obsidian/05-EXPERIMENTS/`. O número **EXP-0019** é a
> próxima vaga livre lida em 2026-09-08T23:55Z; se outra tarefa tomar o número antes, renumerar.
> Nada aqui é dinheiro real (`ENABLE_LIVE_TRADING=false`). 1 R = **48,33 USDT** (conversão declarada
> do Lab, [[KB-0076]]).

## Hipótese (congelada antes de derivar)

Escrita na notes-T3.47 §15 e no brief T3.47b, **antes** de qualquer corrida:

> O piso de ATR% da `mean_reversion_v1` (`atr_pct_min`) foi **subido** duas vezes (0,006 → 0,008 na
> `v2`, → 0,010 na `v3`) para comprar teto de pedágio, e o preço foi a população: 17 e 11 decisões
> em 31 dias, K1 disparando em todas as variantes. **O stop largo já entrega o teto de pedágio que
> o piso comprava** (a `v6`, piso 0,008 com stop 1,5, paga 0,1075 R contra 0,1452 R da `v3` com piso
> 0,010 e stop 1,0). Então **baixar o piso de volta para 0,006 e pagar o pedágio com o stop largo
> deve devolver a população sem devolver o custo.** Teto de pedágio previsto:
> `0,0020 / (1,5 × 0,006) = 0,222 R`, melhor que os 0,2263 R que a `v1` paga hoje com piso 0,006 e
> stop 1 ATR, **com cerca de três vezes mais decisões** que a `v6`.

**O que a hipótese explicitamente não promete, e o experimento tem de separar:** ATR% é a **medida da
volatilidade que a versão exige para entrar**. Baixar o piso admite barras de mercado mais parado —
e não há nenhuma razão aritmética para que a vantagem por operação seja a mesma nessas barras. A
hipótese **presume** que as decisões que o piso recusava são iguais às que ele admitia, só mais
baratas de acessar. **É essa presunção, e só ela, que o EXP mede.**

**Escala da mudança:** `atr_pct_min` 0,008 → 0,006 (o valor original da `v1`, não um número novo), e
o stop com a escada inteira multiplicada por 1,5 — a mesma escala já congelada como braço B1 do
[[EXP-0018]]. Nenhum outro parâmetro muda: teto de ATR%, horizonte, atraso máximo de entrada, custos
assumidos e invalidação ficam **idênticos ao pai**.

## Braços (dois; um derivado, um por identidade)

| braço | versão | pai / origem | `atr_pct_min` | `stop_atr` | escada | `params_hash` |
|---|---|---|---|---|---|---|
| **D1** | `mean_reversion v8` | `mean_reversion v2` | 0,008 → **0,006** | 1 → **1,5** | 2,25 / 3,75 | `b64c4d0e4d4c` |
| **D2** | `mean_reversion v1` | **já existia** (a avó da linhagem) | **0,006** | **1** | 1,5 / 2,5 | `8918b39b73fb` |

**O braço D2 não foi derivado, e não podia ser.** O brief pedia "`atr_pct_min → 0,006` com
`stop_atr 1,0`, só o piso"; `derive_variant.py` recusou, com razão:

```
RECUSADO: mean_reversion v1 já tem exatamente esses parâmetros neste code_ref (params_hash 8918b39b73fb): seria o mesmo experimento contado duas vezes
(system_events, warning, 2026-09-08T23:35:18,231279Z = 20:35:18 Brasília)
```

A `v2` **nasceu** da `v1` subindo o piso; descê-lo de volta reconstrói a `v1`. O braço "só o piso"
portanto **já estava medido**, no mesmo protocolo (mesma janela em duas fatias contíguas, mesmos
quatro mercados, `decision_lag_s = 2`, `workers = 3`, `errors = 0`), na coorte
`replay:d0f77894-1e04-454e-a49f-d9a98d894968`. Uma recusa registrada economizou uma execução e uma
versão no roster.

**Com isso o desenho fecha um fatorial 2×2** (piso × largura do stop), usando duas células já
medidas pelo [[EXP-0014]]/[[EXP-0018]]:

| | `stop_atr = 1` | `stop_atr = 1,5` |
|---|---|---|
| **piso 0,006** | **D2** `v1` (37 decisões) | **D1** `v8` (33 decisões) |
| **piso 0,008** | controle `v2` (17) | controle `v6` (15) |

## Portão de desenho (C1–C8) — congelado

Nenhum código novo: `mean_reversion_v1`
(`sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f`) congelada, com um a
quatro parâmetros movidos.

| # | Critério | Veredito | Justificativa |
|---|---|---|---|
| C1 | Plausibilidade da vantagem | **REJECT** | O mecanismo de **população** é aritmético e foi conferido barra a barra no livro-razão (o piso 0,006 admite 64 das 219 barras que chegam ao porteiro contra 30 do piso 0,008). O mecanismo de **vantagem** nunca teve argumento: a hipótese presume que as barras de ATR% entre 0,6 % e 0,8 % rendem como as acima de 0,8 %. **Medido: rendem −0,0817 R (stop 1,5) e −0,0814 R (stop 1,0), contra +0,2861 e +0,2998 das que já existiam.** A presunção é falsa nas duas colunas |
| C2 | Risco de sobreajuste | **PASS** | Nenhum limiar novo foi garimpado: 0,006 é o valor **original** do código congelado, e 1,5 é a escala já pré-registrada no [[EXP-0018]] B1. Zero graus de liberdade escolhidos depois de ver o dado. A alternativa 0,004 **não** foi testada, e está pré-declarada abaixo em vez de tentada |
| C3 | Adequação da amostra | **PASS — o primeiro PASS da família** | D1: **33 decisões avaliáveis em 11 dias**; D2: **37 em 11 dias**. K1 (< 20) **não dispara em nenhum dos dois** — é a primeira vez em toda a linhagem `mean_reversion` que o estresse aceita dar veredito em vez de `amostra_insuficiente`. Continua abaixo dos 30 dias distintos que K3 exige |
| C4 | Dependência de regime | **REJECT, e é o achado do EXP** | Os quatro dias que só existem com o piso baixo (2026-08-24, 08-28, 09-03, 09-06) somam **−6,40 R** na D1 (os quatro negativos) e −4,88 R na D2 (três dos quatro negativos). **O piso de ATR% estava operando como filtro de regime não declarado, e o que ele filtrava eram dias ruins.** Além disso a segunda metade da janela afunda os dois braços (−0,4551 R com n=6 e −0,5568 R com n=7) |
| C5 | Calibração das saídas | **PASS — e é a única métrica que melhora** | A banda de stop do `paper_v1` é `[0,003; 0,03]` do preço (`packages/risk-core/hunter_risk/limits.py:151-152`). A `v6` põe **20,0 %** das decisões acima do teto; a **D1 põe 9,1 %**, e as **18 decisões novas contribuem com zero** (stop pequeno porque o ATR% é pequeno; `risco%_p50` 0,01090 contra 0,01631). O piso baixo e o stop largo puxam o C5 em direções opostas |
| C6 | Concentração de risco | **PASS** | `research_only`, sem linha em `agents`, sem carteira, `shadow_outbox` zerada para a coorte de replay. K6 não dispara: maior mercado 33,3 % (DOGEUSDT) na D1 e 32,4 % na D2 — **melhor** que os 40–41 % dos controles |
| C7 | Realismo de execução | **PASS, com a ressalva de sempre** | Mesmos custos assumidos e mesmo `max_entry_delay_s = 120 s` do pai. `entrada_mais_1_barra` vale −0,0199 R (D1) e +0,0039 R (D2), IC contendo zero nos dois. **Ressalva:** o `stop_atr` **efetivo** (risco ÷ (ATR% × preço)) vai de **1,1136 a 1,9149** num `stop_atr` declarado de 1,5, e por isso o teto de pedágio de 0,222 R prometido pela hipótese **foi furado em 2 das 33 decisões** (máximo medido 0,2632 R). Teto de pedágio é média, não garantia |
| C8 | Qualidade da invalidação | **PASS por ausência** | A `mean_reversion_v1` **não tem invalidação estrutural** (0 `invalidated` em todas as oito coortes da linhagem), então o eixo do piso não interage com o vício que o [[EXP-0018]] C8 documentou na `momentum`. O livro tem três modos de morrer: alvo, stop e horizonte. O piso baixo desloca o mix de 80 % horizonte (`v6`) para 54,5 % horizonte / 27,3 % stop / 18,2 % alvo |

**Veredito do portão:** `REJECT` — C1 e C4 registrados; C3 e C5 melhoram e não compensam.
2026-09-08, quant-engineer.

## Protocolo (congelado na ativação)

- **Strategies / versions:** `mean_reversion v8` (D1), `mean_reversion v1` (D2, preexistente)
- **code_ref:** `hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f`
  nos dois braços e nos dois controles — **idêntico ao do pai**, conferido no banco
  (`code_ref_igual_ao_pai = t`)
- **params_format:** `1`; `params_hash` na tabela de braços acima
- **Parâmetros alterados na D1 (e só eles):** `atr_pct_min` 0,008 → 0,006, `stop_atr` 1 → 1,5,
  `target_atr` 1,5 → 2,25, `target2_atr` 2,5 → 3,75. `atr_pct_max = 0,05`, `horizon_s = 14400`,
  `max_entry_delay_s = 120`, `assumed_spread_bps = 2`, `slippage_bps = 5`, `fee_bps = 4`,
  `base_confidence = 0.5` **iguais ao pai**
- **Timeframe de decisão / de outcome:** 15 min / 1 min, UTC
- **Agregação e ATR:** 1 m → 15 m só com barras UTC contíguas e finais; ATR = Wilder(14) de 15 min,
  97 barras
- **Entrada:** open da primeira barra de 1 min estritamente posterior a `decision_at`, com
  `entry_bar_open − source_bar_close <= 120 s`
- **Saída:** gap na abertura primeiro, depois toques intrabar; stop e alvo na mesma barra → **stop**;
  horizonte de 4 h contado da entrada
- **Custos assumidos (hipóteses, não tarifas verificadas):** spread total 2 bps, slippage 5 bps por
  lado, taxa 4 bps por lado; funding assinado
- **Política de reentrada:** um acompanhamento `pending_entry|active` por
  `(strategy_version_id, market_id, cohort)` — é ela que explica 64 barras disparadas → 33 decisões
- **Cohort (retrospectiva) D1:** `replay:8ac79cca-916b-4f7f-bd83-01b068b9f811`
- **Cohort (retrospectiva) D2:** `replay:d0f77894-1e04-454e-a49f-d9a98d894968`
- **Cohort (prospectiva) D1, aberta em:** **2026-09-08T23:37:33,252307Z** (**20:37:33** Brasília)
- **Controles predeclarados:** `replay:9d99748b-21b9-44a7-8980-32c37b931e6e` (`mean_reversion v6`,
  piso 0,008 + stop 1,5) para a D1 e `replay:d570b19a-f6e2-4312-86ed-9394b16ac81a`
  (`mean_reversion v2`, piso 0,008 + stop 1,0) para a D2
- **Estimando:** Δ de `expectancy_net` em R entre a variante (população inteira) e o pai (subconjunto
  com `atr_pct >= 0,008`), com **IC 95 % por bootstrap de blocos de dia** (10 000 reamostragens,
  semente 20260908, `.claude/state/exp-drafts/t342-blocos/blocos.py`, `sha256 b2946bca…`, **sem uma
  linha alterada** desde a T3.42). O instrumento é o de contraste **população contra população**
  porque a variante é **superconjunto exato** do pai — medido, não presumido (ver abaixo)
- **Estimando secundário (pré-registrado):** `expectancy_net` da faixa `[0,006; 0,008)` isolada —
  as decisões que o piso baixo compra
- **Universo elegível:** `markets.is_monitored` **de hoje** (limitação declarada do motor,
  `docs/PIPELINE.md` §6c)
- **Markets:** binance ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT (replay); universo monitorado inteiro
  (prospectiva)
- **Janela de replay:** 2026-08-08 → 2026-09-08, em duas fatias contíguas

### O aninhamento, medido antes de escolher o instrumento

| grupo | n | `expectancy_net` | soma R | ATR% mín | ATR% máx |
|---|---:|---:|---:|---:|---:|
| D1 ∩ `v6` (nas duas) | **15** | **+0,2861** | +4,29 | 0,00815 | 0,03565 |
| só na D1 (piso 0,006) | 18 | −0,0817 | −1,47 | 0,00603 | 0,00775 |
| decisões da `v6` ausentes na D1 | **0** | — | — | — | — |
| D2 ∩ `v2` (nas duas) | **17** | **+0,2998** | +5,10 | 0,00815 | 0,03565 |
| só na D2 (piso 0,006) | 20 | −0,0814 | −1,63 | 0,00603 | 0,00775 |
| decisões da `v2` ausentes na D2 | **0** | — | — | — | — |

**As 15 decisões da `v6` estão todas na D1 e as 17 da `v2` estão todas na D2**, mercado a mercado,
barra a barra, com o mesmo `r_net` — a ocupação de slot **não interferiu** em 31 dias × 4 mercados.
O piso é um filtro puro, e por isso o contraste correto é população-contra-população, não pareado.

## Critérios de morte (K1–K6, régua do [[EXP-0017]]) — escritos antes da leitura

| # | Regra | Consequência |
|---|---|---|
| K1 | < 20 decisões na janela | ausência de população: **deprecar**; mais 30 dias não a criam |
| K2 | > 1 500 decisões | é um relógio, não uma condição |
| K3 | >= 100 avaliáveis **E** >= 30 dias distintos **E** expectancy **bruta** < 0 | **deprecar** |
| K4 | `unavailable` > 40 % das barras | bug de janela, não resultado |
| K5 | cobertura de `R_net` < 70 % | não mata; rebaixa o relato |
| K6 | >= 60 % das decisões num único mercado | não mata; obriga a decomposição por mercado |

## Avaliação de 2026-09-08 — **REPLAY** (retrospectiva) — `read_at = 2026-09-08T23:44:06Z`

> **Rótulo obrigatório: REPLAY.** Mesma janela que gerou a hipótese ([[KB-0010]]). Não é evidência
> prospectiva e não decide ativação nenhuma sozinha.

**SQL usado:** `2026-09-09-t347b-q10-populacoes.sql`, `-q11-faixa-nova.sql`, `-q12-dump-blocos.sql`,
`-q13-recibos-iso-roster.sql`, `-q14-dias-e-mercados.sql`, `-q15-teto-de-pedagio.sql` em
`infra/scripts/sql/research/`. Livro-razão: dois arquivos `--explain-ledger` com `bars = lines`
(5 760 + 6 144 = 11 904 linhas).

### O porteiro de ATR%, barra a barra (a medição que o EXP existe para fazer)

Barras que **chegam** ao portão de ATR% (depois de `no_uptrend_1h`, `not_stretched` e
`close_below_mid`, nenhum dos quais depende do piso): **219**, idêntico nas três variantes.

| piso | admite | recusa | % recusada do que chega ao portão | decisões (após slot) |
|---|---:|---:|---:|---:|
| 0,010 (`v4`) | 19 | 200 | 91,3 % | 10 |
| 0,008 (`v6`) | 30 | 189 | 86,3 % | 15 |
| **0,006 (D1)** | **64** | **155** | **70,8 %** | **33** |

Faixas das recusas: **115** barras abaixo de 0,004, **40** em `[0,004; 0,006)`, **34** em
`[0,006; 0,008)`, **11** em `[0,008; 0,010)`. **O teto `atr_pct_max = 0,05` nunca recusou uma barra**
(0 em 219 avaliações): metade do parâmetro é letra morta nestes mercados.

### Cobertura

| coorte | emitidos | pendentes | entradas | ativos | alvo | stop | expirado | invalidado | sem funding | **avaliáveis** | dias |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| D1 `mean_reversion v8` | 33 | 0 | 33 | 0 | 6 | 9 | 18 | 0 | 0 | **33** | 11 |
| D2 `mean_reversion v1` | 37 | 0 | 37 | 0 | 15 | 16 | 6 | 0 | 0 | **37** | 11 |
| controle `v6` | 15 | 0 | 15 | 0 | 1 | 2 | 12 | 0 | 0 | **15** | 7 |
| controle `v2` | 17 | 0 | 17 | 0 | 7 | 6 | 4 | 0 | 0 | **17** | 7 |

**Cobertura de `R_net` = 100 % nas quatro.**

### Métricas e o contraste pré-registrado

| braço | decisões pai → variante | pedágio pai → variante | bruto pai → variante | **líquido pai → variante** | Δ (variante − pai) | **IC 95 % por bloco de dia** |
|---|---|---|---|---|---|---|
| **D1** (`v6` → `v8`) | 15 → **33** | 0,1075 → **0,1510** | 0,3953 → 0,2383 | +0,2861 → **+0,0855** | **−0,2006** | **[−0,8083; +0,1032]** |
| **D2** (`v2` → `v1`) | 17 → **37** | 0,1685 → **0,2263** | 0,4686 → 0,3210 | +0,2998 → **+0,0938** | **−0,2060** | **[−0,7276; +0,1089]** |
| D1 vs `v4` (piso 0,010) | 10 → 33 | 0,0897 → 0,1510 | 0,4251 → 0,2383 | +0,3337 → +0,0855 | −0,2482 | [−1,5808; +0,1327] |
| D2 vs `v3` (piso 0,010) | 11 → 37 | 0,1452 → 0,2263 | 0,6587 → 0,3210 | +0,5131 → +0,0938 | −0,4193 | [−1,7829; +0,0072] |

**Os quatro intervalos contêm zero** — com 11 dias de bloco, nada é estatisticamente distinguível.
**Mas os quatro pontos estimados são negativos**, e o mais estreito quase exclui zero pelo lado
errado. Quatro contrastes pré-declarados apontando para o mesmo lado valem mais que cada um.

### O estimando secundário — as decisões que o piso baixo compra

| faixa | n | bruto | pedágio | **líquido** | soma R | PF |
|---|---:|---:|---:|---:|---:|---:|
| D2 `[0,006; 0,008)` (stop 1,0) | 20 | +0,1956 | 0,2753 | **−0,0814** | −1,63 | 0,863 |
| D1 `[0,006; 0,008)` (stop 1,5) | 18 | +0,1074 | 0,1873 | **−0,0817** | −1,47 | 0,839 |
| **diferença (o efeito do stop largo sobre a faixa nova)** | | **−0,0882** | **−0,0880** | **−0,0003** | | |

**O stop largo cortou o pedágio da faixa nova por 1,47 (a identidade prevê 1,5) e devolveu no bruto
0,0882 R contra 0,0880 R economizados.** Sobrevive **0,0003 R** — zero para qualquer instrumento.
Em dinheiro: **−3,94 USDT por decisão nova, −71 USDT em 31 dias.**

### Estresse (`replay.stress`, `READ ONLY`)

| braço | `base` | `custos_x2` (Δ) | `stop_x0.75` | `entrada_mais_1_barra` | 1ª metade | 2ª metade | **veredito** |
|---|---:|---:|---:|---:|---:|---:|---|
| controle `v6` (piso 0,008) | +0,2861 (PF 2,282) | **+0,1716** (−0,1145) | +0,1842 | −0,0235 | +0,2587 (14) | +0,6692 (1) | `amostra_insuficiente` (15/30) |
| **D1** `v8` (piso 0,006) | +0,0855 (PF 1,226) | **−0,0628** (−0,1482) | −0,0017 | −0,0199 | +0,2056 (27) | −0,4551 (6) | **`frágil a custos`** |
| **D2** `v1` (piso 0,006) | +0,0938 (PF 1,186) | **−0,1213** (−0,2150) | +0,0812 | +0,0039 | +0,2456 (30) | −0,5568 (7) | **`frágil a custos`** |

**A leitura mais dura do EXP está aqui:** com o piso 0,008 a versão aguentava o custo dobrado e
continuava positiva; com o piso 0,006 ela **vira negativa nas duas larguras de stop**. **O piso de
ATR% era a margem de segurança de custo da versão.** O eixo do stop largo cumpre o que promete
também aqui — o Δ de `custos_x2` cai de −0,2150 (stop 1,0) para −0,1482 (stop 1,5), ÷1,45, quase o
1/k da identidade — mas a base cai junto. A D1 acumula **quatro** bandeiras (custo, parâmetro, um
mercado, uma metade) contra duas da D2.

### K1–K6 aplicados

- **K1 NÃO dispara em nenhum dos dois braços** (33 e 37 decisões) — o primeiro PASS da família
  `mean_reversion`, e a razão de o estresse ter dado veredito em vez de `amostra_insuficiente`.
- K2 não dispara; K4 não dispara (`unavailable` 448/11 904 = **3,8 %**); K5 não dispara (cobertura
  **100 %**); K6 não dispara (maior mercado **33,3 %** na D1 e 32,4 % na D2).
- K3 não é avaliável: **11 dias distintos < 30** — e o bruto dos dois é positivo (+0,2383 e +0,3210).

## Veredito

**Formal: `negativo` nos dois braços** — os quatro contrastes pré-declarados são negativos, o
estimando secundário (a faixa comprada) é negativo nas duas larguras de stop, e o estresse recusa
os dois por fragilidade a custo. Nenhum IC exclui zero, então a régua prospectiva do [[SHADOW-LAB]]
§9 continua a valer: **isto é REPLAY e não ativa nada sozinho.**

**Recomendação por braço:**

| braço | recomendação | razão de uma linha |
|---|---|---|
| **D1** `mean_reversion v8` | **manter em pesquisa — pela mensurabilidade, não pelo mérito** | é a única versão da família com população que a régua julga em 30 dias (33 decisões), e a coorte dela **contém** a da `v6` decisão a decisão: uma execução mede as duas hipóteses. Mas as 18 decisões que ela acrescenta perdem −0,0817 R cada e o custo dobrado a vira negativa |
| **D2** `mean_reversion v1` | **manter em pesquisa** (nada muda; já estava ativa) | Δ −0,2060 R contra a filha `v2`; é a prova independente de que o efeito do piso não depende da largura do stop |

**O que isto faz com o [[EXP-0018]] B1 (`mean_reversion v6`):** a recomendação daquele EXP era
"melhor candidata do eixo, mas K1 dispara (15 decisões)", e a proposta era baixar o piso para
resolver o K1. **A proposta foi executada e a resposta é não.** O K1 da `v6` não é piso mal
calibrado: é **ausência de população boa**. Baixar o piso resolve o sintoma (n) e destrói o que se
queria medir. A leitura correta do K1 da `v6` volta a ser a da régua original: **esperar mais meses.**

**O que muda o veredito:** a coorte `prospective` da D1, aberta em 2026-09-08T23:37:33Z
(**20:37:33** Brasília), reavaliada em **2026-10-08** contra a `v6` na mesma janela e sobre o
universo inteiro — e, principalmente, **o custo real medido contra o livro da corretora**. Todo este
eixo é linear na hipótese de 20 bps ida e volta: **se o custo real for metade do assumido, a faixa
`[0,006; 0,008)` passa de −0,08 R para perto de +0,06 R e o veredito deste EXP inverte.** Essa
medição não existe desde a [[KB-0076]] e vale mais do que qualquer variante nova.

## O que ficou pré-declarado e NÃO foi tentado

Para que o próximo passo não seja garimpo: a faixa `[0,004; 0,006)` tem **40 barras** esperando no
livro-razão (contra as 34 que a faixa `[0,006; 0,008)` tinha), e um piso de 0,004 levaria as barras
admitidas de 64 para 104. **Não derivei essa variante**, porque o resultado desta tarefa é a previsão
de que ela seria pior — o ATR% dela é ainda menor, logo o pedágio por R é ainda maior. **Se alguém
quiser medi-la, este parágrafo é o pré-registro:** hipótese direcional **negativa**, teto de pedágio
previsto `0,0020/(1,5 × 0,004) = 0,333 R`, controle `mean_reversion v8`, estimando idêntico ao deste
EXP.

## A frase honesta para levar adiante

**O piso de ATR% não escondia decisões boas: escondia dias ruins.** Dos quatro dias que só existem
com o piso em 0,006 — 24 e 28 de agosto, 3 e 6 de setembro —, **os quatro são negativos**. Um
porteiro que ninguém tinha declarado como filtro de regime estava funcionando exatamente como um, e
afrouxá-lo é comprar 18 operações a −3,94 USDT cada. Somado ao [[EXP-0013]] (alvo) e ao
[[EXP-0018]] (stop), fecham-se **três eixos de geometria medidos, e nenhum fabricou vantagem**: os
três mexem no pedágio, e a vantagem na entrada continua sendo o que falta.
