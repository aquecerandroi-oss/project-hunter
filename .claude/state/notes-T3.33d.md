# notes-T3.33d — `derivatives_v1` (EXP-0011): a pré-checagem matou a candidata antes do módulo

**Data:** 2026-09-08 · **Owner:** quant-engineer · **Base:** `main @ 6e9eaa2`
**Brief:** `.claude/state/brief-T3.33d-derivatives_v1.md` · **Contrato:** `.claude/state/exp-drafts/EXP-0011-derivatives-reversao-de-funding.md`
**Leitura do banco (`read_at`):** 2026-09-08, três rodadas somente-leitura na VPS
(`hunter-strategy-worker-1`, `set transaction isolation level repeatable read read only`).

## STATUS

**BLOCKED — e bloqueado pelo portão que o próprio brief congelou, não por impedimento técnico.**

O brief §13 manda rodar uma consulta somente-leitura **antes de escrever uma linha** e nomeia dois
resultados que matam a candidata ali. Um deles ocorreu:

> "**fewer than ~10 negative settlements in total** across the four markets: the state barely existed
> in the window, K1 will fire, and the module is not worth writing"

Medido: **5** liquidações negativas além do juro em 31 dias × 4 mercados (SOL 3, XRP 2, **ETH 0,
DOGE 0**). Metade do piso, e dois dos quatro mercados sem nenhuma ocorrência.

O segundo modo de morte — `mark_price` nulo — **não** ocorreu: `with_mark_price = settlements` em
100 % das linhas (5 298/5 298 na janela inteira). **Não há bug de dado a reportar** neste eixo, e
`derivatives._resolve_funding` funcionaria pelo caminho durável em toda barra.

**Portanto: `derivatives_v1.py` NÃO foi escrito, e `registry.py`, `constraints.py` e
`seed_reference.py` NÃO foram tocados.** Escrever o módulo depois de o portão pré-registrado
disparar seria exatamente o modo de falha que o portão existe para impedir. Um efeito colateral útil:
**zero risco de colisão** com o agente que implementa `session_orb_v1` em paralelo — não abri nenhum
dos três arquivos compartilhados.

Nada foi commitado. Nada foi ativado. Nenhuma coorte criada. Nenhum container tocado.

## FILES

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0011-derivatives-reversao-de-funding.md` | **acrescentados** o portão C1–C8, o teto de custo e a avaliação datada da pré-checagem; `status: proposto` → `bloqueado-por-precheck`. **Hipótese e Protocolo intactos** (linhas 28–115), como o próprio rascunho exige |
| `C:\dev\project-hunter\.claude\state\notes-T3.33d.md` | este arquivo |

**Não criados, de propósito** (o portão reprovou antes):
`packages/core/hunter_core/strategies/derivatives_v1.py`,
`packages/core/tests/unit/strategies/test_derivatives_v1.py`.

**Não tocados, e é a garantia contra o agente paralelo:**
`packages/core/hunter_core/strategies/registry.py`, `.../constraints.py`,
`infra/scripts/seed_reference.py`, `.../session_orb_v1.py`, os sete módulos do fecho
(`aggregate`, `base`, `canonical`, `envelope`, `indicators`, `numeric`, `schema`),
`momentum_v1.py`, `volume_anomaly_v1.py`, `.env*`, `apps/**`, `services/market-worker/**`,
`services/execution-worker/**`, `obsidian/**`.

Confirmado por `git status --porcelain`: o único arquivo meu modificado em `packages/` é **nenhum**.
As demais linhas modificadas na árvore (`apps/api/tests/...`, `docs/DESIGN.md`,
`packages/core/hunter_core/db/models/agents.py`, `services/strategy-worker/.../replay/run.py`,
`.claude/launch.json`, `brief-T3.15d-owner-dsn.md`) **já estavam lá** e não são minhas.

## PRÉ-CHECAGEM SQL — saída real

Três rodadas, todas dentro de uma transação `repeatable read read only`, via
`ssh hunter-vps 'docker exec -i hunter-strategy-worker-1 python -' < <script>`.
Scripts descartáveis, fora do repositório (scratchpad da sessão).

### Rodada 1 — a consulta literal do brief §13

```
---- Q1 por mercado (janela 2026-08-08..2026-09-08) ----
symbol | settlements | negative_settlements | with_mark_price | most_negative | most_positive
DOGEUSDT | 91 | 0 | 91 | -0.0000354300 | 0.0001000000
ETHUSDT | 91 | 0 | 91 | -0.0000067500 | 0.0001000000
SOLUSDT | 91 | 3 | 91 | -0.0001242100 | 0.0001000000
XRPUSDT | 91 | 2 | 91 | -0.0001893400 | 0.0001000000

---- Q2 total da tabela na janela (todos os mercados) ----
settlements | negative_settlements | with_mark_price | markets | first_ts | last_ts
5298 | 513 | 5298 | 277 | 2026-08-08 16:00:00.002000+00:00 | 2026-09-07 23:00:00.001000+00:00

---- Q3 identidade dos quatro mercados ----
symbol | market_type | is_monitored | rows
DOGEUSDT | spot | True | 0
DOGEUSDT | perpetual | True | 94
ETHUSDT | spot | True | 0
ETHUSDT | perpetual | True | 94
SOLUSDT | spot | True | 0
SOLUSDT | perpetual | True | 94
XRPUSDT | spot | True | 0
XRPUSDT | perpetual | True | 94

---- Q4 por dia (todos os mercados) ----
day | settlements | negative
2026-08-08 | 19 | 0        2026-08-19 | 57 | 7      2026-08-30 | 57 | 2
2026-08-09 | 57 | 2        2026-08-20 | 57 | 4      2026-08-31 | 57 | 1
2026-08-10 | 57 | 0        2026-08-21 | 57 | 0      2026-09-01 | 60 | 0
2026-08-11 | 72 | 21       2026-08-22 | 57 | 0      2026-09-02 | 63 | 0
2026-08-12 | 75 | 23       2026-08-23 | 57 | 0      2026-09-03 | 63 | 0
2026-08-13 | 75 | 23       2026-08-24 | 57 | 0      2026-09-04 | 66 | 3
2026-08-14 | 65 | 7        2026-08-25 | 57 | 1      2026-09-05 | 1155 | 151
2026-08-15 | 57 | 9        2026-08-26 | 57 | 3      2026-09-06 | 1253 | 129
2026-08-16 | 57 | 5        2026-08-27 | 57 | 0      2026-09-07 | 1249 | 111
2026-08-17 | 57 | 5        2026-08-28 | 57 | 0
2026-08-18 | 57 | 6        2026-08-29 | 57 | 0
```

**Veredito literal do brief:** `0 + 0 + 3 + 2 = 5 < ~10`. **Não escreva o módulo.**

O `most_positive = 0.0001000000` exato nos quatro é o componente de juros: a taxa passou o mês
quase inteiro **cravada no teto padrão**, que é o oposto do estado que a hipótese espera.

O salto de 57 → ~1 250 liquidações/dia em 2026-09-05 é a entrada de ~385 mercados novos na coleta.
Antes disso a tabela cobre ~19 mercados.

### Rodada 2 — alargar o universo salva o dia um? Não.

```
---- Q5 perpetuos monitorados com pelo menos uma negativa (top 25) ----
symbol | negative | settlements | most_negative
PROMUSDT | 103 | 241 | -0.0200000000      ZKCUSDT   | 11 | 18 | -0.0005196400
ONGUSDT  |  73 |  73 | -0.0014625900      COTIUSDT  | 11 | 18 | -0.0017589500
SKRUSDT  |  56 |  70 | -0.0012376200      ARBUSDT   | 10 | 91 | -0.0003891700
TUSDT    |  32 |  37 | -0.0064830200      DEXEUSDT  |  8 | 18 | -0.0003313900
ACEUSDT  |  18 |  18 | -0.0093603300      ORCAUSDT  |  8 | 16 | -0.0053751200
LAUSDT   |  18 |  18 | -0.0062392300      CYSUSDT   |  6 | 18 | -0.0014801800
AKEUSDT  |  17 |  18 | -0.0039815000      CFGUSDT   |  5 | 11 | -0.0012675800
ZORAUSDT |  17 |  18 | -0.0009649900      FLOCKUSDT |  5 | 18 | -0.0009905400
TUTUSDT  |  14 |  18 | -0.0005893400      JASMYUSDT |  5 |  9 | -0.0003368300
CAPUSDT  |  14 |  18 | -0.0062016200      TRXUSDT   |  4 |  9 | -0.0001985100
HEMIUSDT |  13 |  18 | -0.0030341900      (+ BICO, RAYSOL, CATI, PRL com 4)

---- Q6 quantos mercados monitorados tiveram alguma negativa ----
markets_with_a_negative
40

---- Q7 mercados com >= 80 liquidacoes antes de 2026-09-05 ----
markets_with_full_month: 16

---- Q8 esses mercados, com as negativas deles ----
symbol | settlements | negative
PROMUSDT   | 223 | 103
ARBUSDT    |  82 |  10
SOLUSDT    |  82 |   3
XRPUSDT    |  82 |   2
UNIUSDT    |  82 |   1
BNBUSDT    |  82 |   0      LINKUSDT   |  82 | 0
BTCUSDT    |  82 |   0      NEARUSDT   |  82 | 0
DASHUSDT   |  82 |   0      SAHARAUSDT | 164 | 0
DOGEUSDT   |  82 |   0      SUIUSDT    |  82 | 0
ETHUSDT    |  82 |   0      TAOUSDT    | 164 | 0
                            ZECUSDT    |  82 | 0

---- Q9 candles 1m na janela ----
candles_1m_in_window | markets
3235725 | 294
```

Os mercados com população farta (ONG 73/73, SKR 56/70, TU 32/37, ACE 18/18, LA 18/18) têm **18
liquidações = 6 dias** de histórico. **Não existe janela de 31 dias para eles.**

**E o único mercado com mês inteiro e população é o ponto cego declarado da versão.** PROMUSDT: 223
liquidações em 28 dias ≈ **8/dia**, não 3 — é o **regime de cadência de 1 h** que a corretora liga
quando a taxa satura (`most_negative = −0,02`, ou seja −2 %). É textualmente a objeção estrutural
nº 2 da KB-0023 que o EXP-0011 **admite não resolver**: a versão lê o nível, não a cadência. Um dia
um sobre PROMUSDT mediria saturação, não extremidade — e produziria um número que ninguém poderia
interpretar.

### Rodada 3 — K1 quantificado, e uma segunda morte independente

```
---- Q10 teto de barras com funding negativo vigente (K1) ----
symbol | negative_settlements | max_bars_15m_with_negative_funding
DOGEUSDT | 0 | 0
ETHUSDT  | 0 | 0
SOLUSDT  | 3 | 95
XRPUSDT  | 2 | 63

---- Q11 amplitude de 15 min vs o piso atr_pct_min = 0.006 ----
symbol | bars_15m | avg_range_pct | p50 | p90 | p99 | % barras >= 0.006
DOGEUSDT | 2961 | 0.004808 | 0.003432 | 0.009541 | 0.022662 | 24.69
ETHUSDT  | 2961 | 0.003356 | 0.002466 | 0.006534 | 0.014676 | 12.23
SOLUSDT  | 2961 | 0.004461 | 0.003317 | 0.008442 | 0.019115 | 21.48
XRPUSDT  | 2961 | 0.005277 | 0.003504 | 0.011027 | 0.026993 | 28.50
```

**Q10 — o teto de decisões.** Cada liquidação governa as barras até a seguinte, limitada por
`funding_max_age_s = 32 400 s`. Total: **158 barras de 15 min em ~11 904 (1,33 %)**, em **2 dos 4
mercados**. Esse é o teto **antes** das outras três condições (queda ≥ 1 ATR%, fechamento acima do
meio, faixa de ATR%). Com qualquer conjunção plausível delas o resultado cai para a casa de
**unidades**. **K1 (`< 20 decisões`) dispara com margem larga** — e agora com número, não com
conjetura.

**Q11 — o piso de ATR% é uma segunda morte, independente da primeira.** `atr_pct_min = 0,006` está
**acima da amplitude média de 15 min dos quatro mercados** (0,0034 a 0,0053). Como o ATR de
Wilder(14) é uma média suavizada de 14 amplitudes, a fração de barras em que **ele** passa do piso é
bem menor que os 12–29 % de barras individuais da última coluna. **Declarado como estimativa:** não
calculei Wilder em SQL; a coluna é limite superior, não medida.

## PORTÃO C1–C8 (`edge-strategy-reviewer`) — aplicado ao EXP-0011 antes do módulo

Tabela completa, critério a critério, na seção nova do EXP-0011.

| C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 80 | **50** | 80 | **40** | 80 | 80 | **50** | **10** |

`confidence_score = 63,5` → **`REVISE`** (não `REJECT`: C1 e C2 não são `fail`; não `PASS`: há um
`fail` e 63,5 < 70).

- **C2 = 50** (o mais baixo das quatro candidatas T3.33): 5 condições → 80, menos 30 de penalidade
  por três limiares com casa decimal (`0,0001`, `0,006`, `0,05`).
- **C4 = 40** — o plano K1–K5 não menciona regime. Corrigível **na avaliação**; com C4 = 80 o escore
  vai a 67,5 e continua `REVISE`.
- **C7 = 50** — sem filtro de volume. **Recusado com motivo:** mudaria a tabela congelada e faria
  esta versão medir o eixo da `volume_anomaly_v1`.
- **C8 = 10** — `invalidations = ()`. **Recusado, e é o desenho:** a tese é que o preço está abaixo
  de onde o posicionamento vai empurrá-lo; sair quando ele cai mais contradiz a tese. Divergência
  declarada, não conserto.

**O portão errou o essencial, e vale registrar.** **C3 devolveu 80 ("amostra adequada")** pela
fórmula de barra diária em ações (252 × 0,8⁵ ≈ 82,6/ano). A pré-checagem mediu o oposto: 158 barras
de teto, população praticamente inexistente. **O portão pontua a forma do rascunho e não substitui a
consulta ao dado** — que é exatamente por que o brief §13 mandou consultar primeiro. Nas T3.33a/b o
C3 também deu 80 e ninguém tinha como saber se era verdade; aqui há a medição ao lado.

## TESTS — saída real

Nenhum teste novo foi escrito (não há módulo). O que rodei é a **prova de que a árvore continua
intacta**, incluindo o teste de aceitação obrigatório do brief §3.

```
$ uv run pytest packages/core/tests/unit/strategies -q
........................................................................ [ 26%]
........................................................................ [ 52%]
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 10.00s

$ uv run pytest packages/core/tests/unit/strategies services/strategy-worker/tests/test_code_ref.py -q -k "strategies or code_ref or digest"
........................................................................ [ 23%]
........................................................................ [ 47%]
........................................................................ [ 71%]
........................................................................ [ 95%]
..............                                                           [100%]
302 passed in 15.36s
```

**Aceitação do brief §3 — os digests das versões vivas não se moveram** (trivialmente, porque não
toquei em `packages/`; medido mesmo assim):

```
$ uv run python -c "from hunter_strategy_worker.code_ref import version_code_ref; ..."
momentum_v1       = hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1 = hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
breakout_v1       = hunter_core.strategies.breakout_v1@sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
mean_reversion_v1 = hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
```

Os dois primeiros são exatamente os exigidos pelo brief §3.

### Aritmética de geometria e teto de custo, reproduzida em `Decimal`

```
$ uv run python /tmp/geom_t333d.py
geometria  ATR%    R_net alvo   R_net stop   equilibrio
2.0/3.0    0.003  1.0592      -1.2112     0.5335
2.0/3.0    0.006  1.2684      -1.1102     0.4667
2.0/3.0    0.01   1.3578      -1.0670     0.4400
1.5/1.5    0.003  0.4893      -1.2736     0.7224
1.5/1.5    0.006  0.7282      -1.1449     0.6112
1.5/1.5    0.01   0.8324      -1.0888     0.5667

teto de custo = 0.0020 / (stop_atr * atr_pct_min)
derivatives_v1       risco% 1.200%   teto 0.1667 R
mean_reversion_v1    risco% 0.600%   teto 0.3333 R
momentum_v1          risco% 0.450%   teto 0.4444 R
```

**A tabela do brief §6 e do EXP-0011 confere dígito a dígito** (0,4667 a 0,006; 0,4400 a 0,01;
0,7224 para o `momentum_v1` no piso). E o **teto de custo desta geometria é 0,1667 R**, o mais baixo
das candidatas da T3.33 — a única coisa que continua a favor dela, e que não a salva: pedágio baixo
sobre população inexistente continua sendo zero evidência.

## CONCERNS

1. **Eu não escrevi o módulo, e essa é a entrega.** O brief pediu "implemente exatamente", e o que o
   brief manda fazer quando a consulta devolve < ~10 é **não escrever o módulo**. Honrar um critério
   pré-registrado quando ele desagrada é o único momento em que pré-registrar tem valor. Se o
   operador quiser o módulo mesmo assim, é uma decisão dele, consciente, e eu escrevo — mas ela
   precisa ficar escrita como "implementado apesar do portão", como a T3.33b fez com o `REVISE`.

2. **O piso `atr_pct_min = 0,006` é um risco compartilhado, e essa é a descoberta que ultrapassa
   esta tarefa.** `breakout_v1` e `mean_reversion_v1` congelaram o mesmo valor, e a amplitude média
   de 15 min de ETH/SOL/XRP/DOGE fica **abaixo** dele. Vale medir a distribuição de ATR% de Wilder
   antes de gastar as corridas de replay das duas — se o piso morder demais, K1 pode disparar nelas
   também, e o diagnóstico seria "o piso", não "a regra". **Não medi Wilder**, medi
   `(high−low)/close`: é indicação forte, não prova.

3. **Assunção numérica declarada — a projeção de K1.** O "cai para a casa de unidades" é meu
   raciocínio, não medição: 158 barras × P(queda ≥ 1 ATR%) × P(fecha acima do meio) × P(ATR% na
   faixa). Só o primeiro fator saiu de dado. O que **é** medido e basta sozinho: o teto de 158 barras
   em 2 dos 4 mercados.

4. **Assunção numérica declarada — a janela.** Usei exatamente a do brief
   (`2026-08-08 <= funding_time < 2026-09-08`). O `last_ts` da tabela é `2026-09-07 23:00`, então o
   último dia está parcialmente coberto; isso não muda nada, porque o problema é a ausência de
   negativas no mês inteiro, não a borda.

5. **`is_monitored` é o de hoje, não o da janela.** Q5/Q6 filtram por `markets.is_monitored` lido
   agora; o schema não tem histórico de pertencimento por barra. É a mesma limitação declarada do
   replay (PIPELINE §6c) e ela **infla** a contagem de mercados com negativas, nunca a reduz — o que
   torna o veredito mais conservador, não menos.

6. **Nada foi ativado e nenhuma coorte existe.** A linha `derivatives / v1` continua `draft` no
   catálogo da VPS, com o `code_ref` placeholder que `seed.py` escreve. Não rodei
   `activate_strategy_version.py` nem `replay.run`. **Não rode a sequência do brief §13** enquanto
   este bloqueio não for resolvido: ativar congela `code_ref` e é irreversível, e hoje não há módulo
   para congelar.

7. **A descrição do catálogo continua a antiga** ("Funding, open interest and liquidation setups.").
   O brief §4 mandava trocá-la por "Long after a settled negative funding rate and a stabilising 15 m
   bar."; **não troquei**, porque descreveria código que não existe. Fica como pendência acoplada ao
   módulo, e é também o que garante que não colidi com o agente do `session_orb_v1` em
   `seed_reference.py`.

## O QUE EU FARIA A SEGUIR

Em ordem de custo, e o primeiro é quase de graça:

1. **Reexecutar esta mesma consulta a partir de ~2026-10-06**, quando os ~385 mercados que entraram
   em 2026-09-05 tiverem 31 dias. A rodada 2 mostra que a população existe (40 mercados monitorados
   com alguma negativa; ONG, SKR, TU, ACE com 6 dias e taxas de −0,001 a −0,009): **falta histórico,
   não falta fenômeno.** A hipótese continua viva e não testada.
2. **Medir a distribuição de ATR% de Wilder(14) em 15 min** nos mercados de replay antes de gastar as
   corridas de `breakout_v1` e `mean_reversion_v1` (concern 2).
3. **Só então** decidir entre escrever `derivatives_v1` como está, ou especificar uma `v2` que leia a
   **cadência** de liquidação além do nível — que é o que separaria saturação de extremidade e é a
   objeção que a KB-0023 levantou e esta versão admitiu não resolver. PROMUSDT é a prova viva de que
   a distinção não é teórica.
