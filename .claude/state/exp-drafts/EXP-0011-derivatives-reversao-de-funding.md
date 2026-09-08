---
tags: [experimento, derivativos, funding, shadow-lab]
updated: 2026-09-08
status: bloqueado-por-precheck
owner: sexta-feira
exp: EXP-0011
strategy: derivatives
version: v1
result: inconclusivo
evaluable: 0
days: 0
last_eval: —
---

# EXP-0011 — comprar depois de funding liquidado negativo (`derivatives_v1`)

> **RASCUNHO do quant-engineer (T3.33, 2026-09-08).** Para a Sexta-feira arquivar em
> `obsidian/05-EXPERIMENTS/EXP-0011-derivatives-reversao-de-funding.md` e ligar a partir de
> [[Strategy Backlog]], [[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]],
> [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]],
> [[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]],
> [[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] e [[Experiments Index]].
> Não editei `obsidian/**`.
>
> **Nada foi rodado. Nada foi ativado.** "Hipótese" e "Protocolo" **congelados**; avaliações
> **acrescentadas** abaixo, datadas. Brief: `.claude/state/brief-T3.33d-derivatives_v1.md`.

## Hipótese (congelada)

Num perpétuo USDT, depois de uma **taxa de funding liquidada negativa além do componente de juros**
(`funding_rate ≤ −0,0001`, isto é, ≤ −0,01 % no intervalo de 8 h), precedida de uma **queda real**
nas últimas 2 h (retorno de 8 barras de 15 min ≤ −1 × ATR%) e numa barra de 15 min que **fecha acima
do próprio meio**, o retorno seguinte tem expectancy líquida hipotética maior que zero, com stop a
2,0 ATR e alvo a 3,0 ATR da referência e horizonte de 8 h.

**O que a hipótese é, em uma frase:** o teste, com método, da afirmação mais repetida e menos testada
do mercado — *funding negativo = vendidos aglomerados = fundo local* —, na única metade que nos é
implementável (comprada, execução SPOT, long-only por decisão do Everton).

**A divergência com a nossa própria base, declarada.**
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] recomenda **não gastar braço de sombra
com funding**. Estou indo contra, e o motivo é que a recomendação dela é sobre *funding como filtro
direcional acoplado ao momentum*, com prior desfavorável vindo de um estudo que mede a **variação**
semanal da taxa no **BTC**. Esta é outra pergunta: o **nível** da taxa liquidada como estado de
posicionamento, com gatilho de preço próprio e grupo de controle no próprio replay.
[[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] diz textualmente que **nenhum
teste com método foi localizado** nas fontes consultadas. O custo de descobrir é uma corrida de
replay, e o desenho abaixo faz a candidata morrer barato se o estado não existir.

**O que a hipótese não é.** Não é "funding prevê preço". Não é *cash-and-carry* — as estratégias de
carry com Sharpe alto da literatura são duas pernas, dois mercados e exposição direcional zero; nós
temos uma perna, um mercado e exposição direcional total, e nenhum daqueles números se transfere.

## Protocolo (congelado na primeira ativação — nunca editar)

- **Strategy:** `strategies.key = derivatives`, versão `v1`, `purpose = research_only`.
  Módulo `packages/core/hunter_core/strategies/derivatives_v1.py`.
- **`code_ref`:** digest por versão; os digests de `momentum_v1` (`…ab2e0398…`) e
  `volume_anomaly_v1` (`…9b8c14ab…`) **não se movem** com esta entrega (teste).
- **O que a estratégia lê de derivativos, e só:** `ctx.funding` — **uma** observação, não série.
  **Não** lê open interest (num replay `ctx.open_interest` é sempre `None`: o `ts` durável é um balde
  de rodada de poll e nunca prova `<= cut`), **não** lê `index_price` (nunca é preenchido em
  `NormalizedFunding`, nem pelo caminho durável nem pelo hot state), **não** lê liquidações (não
  existem no contexto).
- **Instrumento declarado:** num replay a leitura vem de `funding_rates` — funding **liquidado**
  (`funding_kind = "realized"`, `ts` = o instante da liquidação), com até ~8 h de idade. A versão
  recusa uma leitura com mais de `funding_max_age_s = 32 400 s` como **`UNAVAILABLE / funding_stale`**,
  nunca como "condição falsa": um mercado cujas liquidações pararam de chegar não prova nada sobre a
  hipótese e não pode rearmar o slot.
- **Timeframe de decisão / de outcome:** 15 min (fechamentos distintos, UTC) / 1 min.
- **Regra de entrada (exata), na ordem:** elegibilidade → disponibilidade e idade do funding →
  janela de sinal 15 m → janela de ATR (Wilder 14 × 15 m, 97 barras, `rolling_window_v1`) →
  `funding_rate ≤ −0,0001` → **houve queda** (`return_8×15m ≤ −1 × ATR%`) → **estabilização**
  (`close ≥ (high+low)/2`) → `0,006 ≤ ATR% ≤ 0,05`.
- **Geometria:** `stop = C − 2,0·ATR`, `alvo1 = C + 3,0·ATR`, alvo informativo `C + 5,0·ATR`.
- **Invalidação (exata): NENHUMA.** A tese é que o preço está temporariamente abaixo de onde o
  posicionamento vai empurrá-lo; uma regra que sai quando o preço cai mais contradiz a tese.
- **Horizonte:** 8 h (28 800 s) = um ciclo de funding.
- **Custos assumidos:** spread total 2 bps, slippage 5 bps/lado, taxa 4 bps/lado,
  `max_entry_delay_s = 120`. Entrada/saída pelo perfil congelado do SHADOW-LAB §3.
- **Parâmetros congelados:** a tabela de `.claude/state/brief-T3.33d-derivatives_v1.md` §7, 18 chaves.
- **Universo:** replay de abertura em ETHUSDT, SOLUSDT, XRPUSDT, DOGEUSDT; `prospective` no universo
  elegível inteiro.

### Geometria — por que o stop é largo

Uma tese de squeeze com stop apertado é um gerador de ruído: a entrada acontece logo depois de uma
queda, na parte mais volátil do movimento. Equilíbrio sob o custo assumido:

| geometria | ATR% | R_net no alvo | R_net no stop | acerto de equilíbrio |
|---|---:|---:|---:|---:|
| 1,5/1,5 (`momentum_v1`, referência) | 0,003 | 0,4893 | −1,2736 | 0,7224 |
| **2,0/3,0 (esta)** | 0,006 | 1,2684 | −1,1102 | **0,4667** |
| **2,0/3,0** | 0,010 | 1,3578 | −1,0670 | 0,4400 |

### O único número que não é chute

`funding_min_abs = 0,0001` é **0,01 %**, que é exatamente o **componente de juros** da fórmula de
funding da Binance por intervalo de 8 h ([[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]]). "Mais
negativo que o componente de juros" é uma linha **mecanicamente significativa** — quer dizer que o
componente de prêmio virou negativo —, não um limiar ajustado. Todo o resto (`drop_bars = 8`,
`drop_min_atr = 1`, `funding_max_age_s = 32 400`) é convenção declarada.

### As duas objeções estruturais que esta versão **não** resolve (KB-0023)

1. **Funding é variável limitada.** Teto e piso são fixados pela corretora; um mercado no limite
   **não fica mais extremo**, e a escala satura exatamente onde o sinal deveria ser mais forte.
2. **Ao saturar, o que muda é a cadência.** A corretora comprime o intervalo para 1 h; **quem lê só a
   taxa não enxerga o regime de cadência**, e confundir os dois produz leitura errada em qualquer
   direção.

Esta versão lê **o nível, e só**. Por isso a primeira avaliação é obrigada a publicar, por decisão,
`funding_rate`, `funding_kind`, a idade da leitura e a distribuição da taxa — para que uma versão
futura consiga separar saturação de extremidade.

## O que falsifica esta hipótese

- **Pré-checagem, antes de escrever o módulo** (uma consulta, no brief §13): quantas liquidações
  negativas além do juro existiram na janela nos quatro mercados, e quantas linhas de
  `funding_rates` têm `mark_price` não nulo. Menos de ~10 negativas no total → **K1 vai disparar**,
  não escreva o módulo. `mark_price` majoritariamente nulo → `_resolve_funding` não consegue montar
  a observação e a versão responderia `funding_unavailable` em toda barra: isso é **bug de dado a
  reportar**, não resultado de estratégia.
- **K1/K2/K3/K4/K5** de `.claude/state/notes-T3.33.md` §5.1. **K5 morde com força aqui:** um
  horizonte de 8 h quase sempre atravessa uma liquidação de funding, então espere cobertura de
  `R_net` bem menor que a das outras três, com `meta.r_ex_funding` como métrica separada e cobertura
  própria ([[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]]).
- **Grupo de controle obrigatório.** Sem contraste, "60 % de acerto" só descreve a deriva do mercado
  no período. A primeira avaliação compara, sobre as mesmas barras e mercados, as decisões com
  funding negativo contra as barras em que **todas as outras condições** valiam e só o funding não —
  o pareamento que a [[KB-0011-volume-magnitude-e-a-ponte-para-direcao]] impôs como padrão.
- **Refutação limitada ao que ela pode negar:** ausência de separação entre os dois grupos, dentro de
  uma margem declarada antes, refuta **esta especificação** (este limiar, esta cadência, este
  horizonte) — não a ideia de posicionamento aglomerado.

## O que este experimento **não** prova

- **Não testa "funding extremo"**, testa **funding negativo além do juro**: a saturação está fora do
  alcance do instrumento.
- **Não testa a metade vendida** do folclore, que é a metade em que a maioria das anedotas se apoia.
  A decisão do Everton (SPOT, long-only) a exclui, e `Decision.direction` é `Literal[LONG]`.
- **Multiplicidade:** uma de quatro versões abertas no mesmo dia
  ([[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]]), e aberta **contra** a
  recomendação explícita de [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] — o que
  aumenta, não diminui, o dever de reportar o resultado seja ele qual for.
- **O replay de abertura não confirma nada**; sai rotulado **REPLAY**.

## Portão C1–C8 (`edge-strategy-reviewer`) — aplicado em 2026-09-08, antes do módulo

Acrescentado pela T3.33d. **Não altera Hipótese nem Protocolo** (congelados acima): registra o
veredito do portão sobre o rascunho como ele está, com a nota de cada critério e a fórmula de
`.claude/skills/edge-strategy-reviewer/references/review_criteria.md`.

| # | Critério (peso) | Leitura sobre este EXP | Sev. | Nota |
|---|---|---|---|---|
| C1 | Edge Plausibility (20) | mecanismo causal nomeado e não genérico — vendidos aglomerados pagam funding, houve queda, a barra estabiliza, o posicionamento desfaz; termos de domínio presentes (`reversion`, `funding`) | pass | 80 |
| C2 | Overfitting Risk (20) | 5 condições (nível de funding, idade da leitura, queda prévia, estabilização, faixa de ATR%) + 0 filtro de tendência = 5 ≤ 10 → 80; penalidade −10 por limiar com casa decimal: `0,0001`, `0,006`, `0,05` → −30 | pass | **50** |
| C3 | Sample Adequacy (15) | fórmula: 252 × 0,8⁵ ≈ 82,6/ano ≥ 30 → 80. **Este 80 está empiricamente refutado** pela pré-checagem abaixo (teto real de 158 barras em 11 904, em 2 dos 4 mercados) — ver "Limite do próprio portão" | pass | 80 |
| C4 | Regime Dependency (10) | o plano de validação congelado (K1–K5) **não** menciona regime | **warn** | 40 |
| C5 | Exit Calibration (10) | `stop_loss_pct = stop_atr × atr_pct_max = 2,0 × 0,05 = 0,10 ≤ 0,15`; `take_profit_rr = 3,0/2,0 = 1,5`, que **não** é `< 1,5` | pass | 80 |
| C6 | Risk Concentration (10) | não aplicável por construção (`research_only`, sem carteira); o perfil que existiria é `PAPER_V1`: `risk_per_trade_pct = 0,0025 ≤ 0,015` e `max_concurrent_positions = 5 ≤ 10` | pass | 80 |
| C7 | Execution Realism (10) | **não há filtro de volume nas condições**; `export_ready_v1` não se aplica | **warn** | 50 |
| C8 | Invalidation Quality (5) | `invalidations = ()` — vazio | **fail** | 10 |

`confidence_score = (80·20 + 50·20 + 80·15 + 40·10 + 80·10 + 80·10 + 50·10 + 10·5)/100 =` **63,5**.

**Veredito: `REVISE`** — não é `REJECT` (C1 e C2 não são `fail`) e não é `PASS` (há um `fail` e
63,5 < 70). As três instruções de revisão, e o que foi feito com cada uma:

1. **C4 — plano de validação sem regime.** Aceita, e ficaria corrigida **na avaliação**: o dia um
   publicaria a decomposição por regime de BTC e por decil de ATR%. Com C4 = 80 o escore vai a
   **67,5** e continua `REVISE`, porque um `fail` sozinho já impede o `PASS`.
2. **C7 — sem filtro de volume.** **Recusada, com motivo.** Um portão de volume mudaria a tabela de
   parâmetros congelada e faria esta versão medir o eixo da `volume_anomaly_v1`. A mitigação
   existente é outra e é declarada: o universo elegível (`markets.is_monitored`) e o piso de ATR%.
3. **C8 — sem invalidação.** **Recusada, e é o desenho.** A tese é que o preço está temporariamente
   abaixo de onde o posicionamento vai empurrá-lo; uma regra que sai quando o preço cai mais
   contradiz a tese. O portão está calibrado para estratégias que **têm** invalidação e pontua a
   ausência como defeito; aqui a ausência é a hipótese. **Divergência declarada, não conserto.**

**Limite do próprio portão, declarado, e desta vez ele erra o essencial:** C3 estima oportunidades
com a base 252 de barra diária em ações e devolveu **80 (amostra adequada)**. A pré-checagem mediu o
oposto — a população mal existe. É a demonstração de que o portão pontua a **forma** do rascunho e
não substitui a consulta ao dado; foi por isso que o brief §13 mandou rodar a consulta primeiro.

### O teto de custo desta geometria (confirmação pedida pela `notes-T3.32.md`)

A T3.32 mediu, em dez populações, que `custo_R × risco%_do_preço = 0,0020` **constante**
(desvio ≤ 1,9×10⁻⁵) — aritmética de 20 bps de ida e volta, não estatística. Para esta geometria
(`stop = 2,0 ATR`, portanto `risco% = 2 × ATR%`), reproduzido em `Decimal` nesta tarefa:

| versão | risco% no piso de ATR% | **teto de custo** |
|---|---:|---:|
| **`derivatives_v1`** (`stop_atr` 2,0, `atr_pct_min` 0,006) | 1,200 % | **0,1667 R** |
| `mean_reversion_v1` (`stop_atr` 1,0, `atr_pct_min` 0,006) | 0,600 % | 0,3333 R |
| `momentum_v1` (`stop_atr` 1,5, `atr_pct_min` 0,003) | 0,450 % | 0,4444 R |
| `volume_anomaly v2` — **medido** no replay | 0,552 % | 0,6152 R |

**O teto de custo desta versão é 0,1667 R por operação**, o mais baixo das candidatas da T3.33 — e é
a única coisa que continua a favor dela. O stop largo em ATR é o que compra isso. Não salva a
candidata: um pedágio baixo sobre uma população que não existe continua sendo zero evidência.

## Avaliações (acrescentadas, nunca reescritas)

### Avaliação de 2026-09-08 — pré-checagem de funding: **a candidata morre aqui**

Consultas **somente-leitura** na VPS (`hunter-strategy-worker-1`, transação
`repeatable read read only`), janela `2026-08-08 <= funding_time < 2026-09-08`. Nenhuma escrita,
nenhuma coorte criada, nenhum container tocado. **Nenhum replay foi executado e o módulo
`derivatives_v1.py` não foi escrito** — o brief §13 congelou esta consulta como portão anterior ao
módulo, e ela reprovou.

**(1) O estado que a versão espera, nos quatro mercados de referência:**

```
symbol   | settlements | negative_settlements | with_mark_price | most_negative  | most_positive
DOGEUSDT |          91 |                    0 |              91 | -0.0000354300  | 0.0001000000
ETHUSDT  |          91 |                    0 |              91 | -0.0000067500  | 0.0001000000
SOLUSDT  |          91 |                    3 |              91 | -0.0001242100  | 0.0001000000
XRPUSDT  |          91 |                    2 |              91 | -0.0001893400  | 0.0001000000
```

**Cinco** liquidações negativas além do juro em 31 dias × 4 mercados. O brief §13 congelou o piso em
**~10** ("o estado mal existiu na janela, K1 vai disparar, e o módulo não vale a pena ser escrito").
Dois dos quatro mercados — **ETHUSDT e DOGEUSDT — não tiveram nenhuma**: a taxa deles nunca saiu do
componente de juros para baixo no mês inteiro.

**(2) `mark_price`: o bug de dado NÃO existe.** `with_mark_price = settlements = 91` nos quatro
(e 5 298/5 298 na tabela inteira). `derivatives._resolve_funding` conseguiria montar a observação
pelo caminho durável em toda barra. Este ramo da pré-checagem **passa** e é a única boa notícia.

**(3) Teto de decisões, medido — K1 quantificado, não conjeturado.** Cada liquidação governa as
barras até a seguinte, limitada por `funding_max_age_s = 32 400 s`:

```
symbol   | negative_settlements | max_bars_15m_with_negative_funding
DOGEUSDT |                    0 |                                 0
ETHUSDT  |                    0 |                                 0
SOLUSDT  |                    3 |                                95
XRPUSDT  |                    2 |                                63
```

**158 barras** de 15 min, de ~11 904 na janela (**1,33 %**), em **2 dos 4 mercados**. E isso é o
**teto antes** das outras três condições (queda ≥ 1 ATR%, fechamento acima do meio, faixa de ATR%).
Com qualquer conjunção plausível delas o número cai para a casa de **unidades**. K1 (`< 20 decisões`)
dispara com margem larga.

**(4) Uma segunda morte, independente: o piso `atr_pct_min = 0,006` está acima da amplitude média de
15 min destes mercados.** Amplitude `(high − low)/close` por barra de 15 min, mesma janela:

```
symbol   | bars_15m | avg_range_pct | p50      | p90      | p99      | % barras >= 0.006
DOGEUSDT |     2961 |      0.004808 | 0.003432 | 0.009541 | 0.022662 |             24.69
ETHUSDT  |     2961 |      0.003356 | 0.002466 | 0.006534 | 0.014676 |             12.23
SOLUSDT  |     2961 |      0.004461 | 0.003317 | 0.008442 | 0.019115 |             21.48
XRPUSDT  |     2961 |      0.005277 | 0.003504 | 0.011027 | 0.026993 |             28.50
```

A **média** fica abaixo de 0,006 nos quatro. O ATR de Wilder(14) é uma média suavizada de 14
amplitudes, então a fração de barras em que **ele** passa do piso é bem menor que os 12–29 % de
barras individuais acima — a coluna é um limite superior, não a medida. Declarado como estimativa:
não calculei Wilder em SQL.

**Consequência que ultrapassa esta candidata:** `breakout_v1` e `mean_reversion_v1` congelaram o
**mesmo** `atr_pct_min = 0,006`. A mesma tabela sugere que o piso delas também morde forte nestes
quatro mercados. Isso é medição a fazer no replay delas, não conclusão desta página.

**(5) Alargar o universo não salva o dia um.** Só **16** mercados têm ≥ 80 liquidações antes de
2026-09-05 (histórico de mês inteiro); destes, apenas cinco têm alguma negativa:

```
symbol     | settlements | negative
PROMUSDT   |         223 |      103
ARBUSDT    |          82 |       10
SOLUSDT    |          82 |        3
XRPUSDT    |          82 |        2
UNIUSDT    |          82 |        1
(BNB, BTC, DASH, DOGE, ETH, LINK, NEAR, SAHARA, SUI, TAO, ZEC: 0)
```

Os mercados com população de verdade (ONGUSDT 73/73, SKRUSDT 56/70, TUSDT 32/37, ACEUSDT 18/18) têm
**18 liquidações = 6 dias** de histórico: entraram na coleta em ~2026-09-05, quando a tabela salta de
57 para ~1 250 liquidações/dia. Não há janela de 31 dias para eles.

**E o único mercado com população farta é justamente o ponto cego declarado desta versão.**
PROMUSDT: 223 liquidações em 28 dias ≈ **8 por dia**, não 3 — isto é o **regime de cadência de 1 h**
que a corretora liga quando a taxa satura, com `most_negative = −0,02`. É exatamente a objeção
estrutural nº 2 da KB-0023 que esta versão **admite não resolver** (lê o nível, não a cadência).
Rodar o dia um sobre PROMUSDT mediria saturação, não extremidade.

**Result: `inconclusivo`** — nada foi medido sobre a hipótese. **A hipótese não foi testada nem
refutada**; o que foi refutado é a **viabilidade do protocolo de dia um** com o dado que existe.

**Next Action:** não escrever o módulo agora. Três caminhos, em ordem de custo, para o operador:

1. **Esperar dado.** Reexecutar esta mesma consulta quando os ~385 mercados que entraram em
   2026-09-05 tiverem ≥ 31 dias (ou seja, a partir de ~2026-10-06) e um universo de replay com
   população real existir. Custo: uma consulta.
2. **Reespecificar o universo do dia um**, mantendo Hipótese e Protocolo congelados: trocar
   ETH/SOL/XRP/DOGE por mercados com população, **excluindo** os de cadência comprimida — o que
   exige antes uma versão que saiba ler a cadência, e isso é `derivatives_v2`, não esta.
3. **Deprecar `derivatives v1`** e gastar a vaga de sombra numa das candidatas cujo estado existe.
   É o que [[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] já recomendava; a
   divergência declarada na Hipótese perdeu, nesta janela, o argumento que a sustentava.

### Avaliação de <segunda data> — replay de abertura

<não executado: depende de o caminho 1 ou 2 acima produzir um universo com população. A preencher:
coorte, janela, mercados, recibos, comandos exatos, cobertura completa **com a tabela de funding**
(`R_net` conhecido / só `r_ex_funding` / nenhum, com motivos), métricas com denominador,
distribuição de `funding_rate` e `funding_kind` na decisão, contraste contra o grupo de controle,
`Result`, `Next Action`>

## Variantes tentadas

| Variante | Quando | Por quê | Onde ficou registrada |
|---|---|---|---|
| funding positivo extremo → vender | 2026-09-08 | descartada **antes** de rodar: SPOT e long-only por decisão do Everton; `Decision.direction` é `Literal[LONG]` | esta página |
| prêmio contra o índice (`mark − index`) | 2026-09-08 | descartada: `index_price` nunca é preenchido em `NormalizedFunding` | `.claude/state/notes-T3.33.md` §1.4 |
| quadrantes de open interest | 2026-09-08 | descartada: num replay `ctx.open_interest` é sempre `None` | `.claude/state/notes-T3.33.md` §1.3 |

## Relacionadas

[[Experiments Index]] · [[Strategy Backlog]] ·
[[KB-0023-funding-extremo-como-contrarian-a-afirmacao-mais-repetida]] ·
[[KB-0022-funding-preve-retorno-a-evidencia-direta-e-fraca]] ·
[[KB-0021-funding-como-preco-de-posicionamento-nao-como-previsao]] ·
[[KB-0019-o-que-a-nossa-funding-rate-mede-de-fato]] ·
[[KB-0026-funding-num-horizonte-de-4h-e-o-vies-de-exclusao]] ·
[[KB-0008-custos-em-perpetuos-e-o-r-que-sobra]] ·
[[KB-0010-overfitting-de-backtest-e-o-preco-de-cada-variante]] · [[Registro de Tentativas]]

## Fontes

`.claude/state/notes-T3.33.md` · `.claude/state/brief-T3.33d-derivatives_v1.md` ·
`services/strategy-worker/hunter_strategy_worker/derivatives.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/environment.py` ·
`infra/scripts/activate_strategy_version.py` ·
`services/strategy-worker/hunter_strategy_worker/replay/run.py`
