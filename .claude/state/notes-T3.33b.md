# notes-T3.33b — `mean_reversion_v1`: recuo comprado dentro de uma tendência de 1 h

**Data:** 2026-09-08 · **Owner:** quant-engineer · **Base:** `main @ 9f1f624`
**Brief:** `.claude/state/brief-T3.33b-mean_reversion_v1.md` · **Contrato congelado:** `EXP-0009`
**Nada foi commitado. Nada foi ativado. Nenhum replay foi rodado** (o porquê está em RECIBO).

## STATUS

**DONE_WITH_CONCERNS.**

O módulo, os testes, as três linhas de catálogo e o portão C1–C8 estão entregues, com os dois
digests vivos provados imóveis. Três coisas puxam o status para baixo e nenhuma delas é opinável:

1. o portão C1–C8 devolve **`REVISE`, não `PASS`** (escore 65,5), e o motivo dominante é o C8 —
   `invalidations = ()` —, que é exatamente o desenho declarado da versão. Está tudo escrito no EXP;
2. com os parâmetros congelados, **`trend_warmup` e `trend_gap` são ramos mortos**: a janela de ATR
   (1455 min) começa antes da janela de tendência (1305 min no pior caso), então o `atr_*`
   correspondente sempre aparece primeiro. O brief §7 manda "reportar `trend_gap` separado de `gap`"
   no replay do dia um — **ele vai vir zerado**, e isso não é cobertura boa, é um ramo que só uma
   variante acorda. Há teste para as duas metades disso;
3. o replay do dia um **não foi executado**, porque ele exige a versão ativada e a ativação está
   fora do meu escopo por ordem explícita.

## FILES

Escritos por esta tarefa:

| arquivo | o quê |
|---|---|
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\mean_reversion_v1.py` | **novo** — a versão congelada, 338 linhas (orçamento 350) |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_mean_reversion_v1.py` | **novo** — 35 testes, séries sintéticas com valor esperado escrito à mão |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\registry.py` | +1 import, +1 nome no `DEFAULT_REGISTRY` (só a minha linha) |
| `C:\dev\project-hunter\packages\core\hunter_core\strategies\constraints.py` | +1 entrada `"mean_reversion_v1"` (só a minha) |
| `C:\dev\project-hunter\infra\scripts\seed_reference.py` | descrição da linha `mean_reversion` (era "Fade of stretched moves in low volatility", que não é esta regra) |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_no_lookahead.py` | +5 testes anti-antecipação no arquivo **compartilhado**, no fim, sem tocar no que já existia |
| `C:\dev\project-hunter\packages\core\tests\unit\strategies\test_registry.py` | +1 linha no roster, +1 contexto, +1 `params_hash` pinado |
| `C:\dev\project-hunter\services\strategy-worker\tests\test_constraints_outside_freeze.py` | inverteu o sentido de **uma** asserção de cobertura (justificativa abaixo) |
| `C:\dev\project-hunter\.claude\state\exp-drafts\EXP-0009-mean-reversion-pullback-em-tendencia.md` | **acrescentada** a seção do portão C1–C8 e o teto de custo; Hipótese e Protocolo intactos |
| `C:\dev\project-hunter\.claude\state\notes-T3.33b.md` | este arquivo |

**Não tocados** (confirmado por leitura antes de cada edição):
`base.py`, `momentum_v1.py`, `volume_anomaly_v1.py`, `schema.py`, `envelope.py`, `indicators.py`,
`numeric.py`, `canonical.py`, `aggregate.py` — os nove do fecho —, `breakout_v1.py` e
`test_breakout_v1.py` (do agente em paralelo), `.env*`, `apps/**`, `services/market-worker/**`,
`services/execution-worker/**`, `obsidian/**`, `hunter_core/strategies/__init__.py`.

**A única mudança fora da minha lista de arquivos**, e por que ela é obrigatória:
`test_constraints_outside_freeze.py::test_every_registered_strategy_is_covered` afirmava
`{módulos registrados} == set(FROZEN_DIGESTS)`. Registrar qualquer versão nova a quebra. Inverti
para `set(FROZEN_DIGESTS) <= {módulos registrados}` e renomeei para
`test_every_frozen_digest_still_belongs_to_a_registered_strategy`, porque é isso que o teste
protege de verdade: `FROZEN_DIGESTS` são os digests que as **linhas já ativadas na VPS** carregam, e
uma versão registrada e ainda não ativada não tem digest a proteger. A metade em ferro — nenhum
digest congelado pode perder o código dele — continua valendo.

## O que a versão faz, em três linhas

LONG num fechamento de 15 min quando a **última hora completa** fecha acima da SMA das 20 horas
anteriores (a hora em formação nunca entra), o fechamento de 15 min está a **≥ 1 desvio populacional
abaixo** da média dos 20 últimos fechamentos (barra atual incluída), a barra **fecha acima do
próprio meio**, e `0,006 ≤ ATR% ≤ 0,05`. `stop = C − 1,0 ATR`, `alvo = C + 1,5 ATR`, alvo
informativo `C + 2,5 ATR`, horizonte 4 h, **`invalidations = ()`**.

O helper de z-score (`_dispersion`) mora **dentro** do módulo, nunca em `indicators.py` — é a regra
de projeto do §2 do brief e é o que mantém os dois digests vivos parados.

## TESTS — saída real

```
$ uv run pytest packages/core/tests/unit/strategies/test_mean_reversion_v1.py -q
...................................                                      [100%]
35 passed in 17.59s

$ uv run pytest packages/core/tests/unit/strategies -q -k "strategies or code_ref"
........................................................................ [ 78%]
............................................................             [100%]
276 passed in 24.61s

$ uv run ruff check packages/core/hunter_core/strategies/mean_reversion_v1.py \
    packages/core/tests/unit/strategies/test_mean_reversion_v1.py \
    packages/core/hunter_core/strategies/registry.py \
    packages/core/hunter_core/strategies/constraints.py infra/scripts/seed_reference.py
All checks passed!

$ uv run pyright packages/core/hunter_core/strategies/mean_reversion_v1.py
0 errors, 0 warnings, 0 informations
```

`uv run mypy` **não existe neste repositório** (`error: Failed to spawn: mypy — program not found`):
o checador de tipos do projeto é o `pyright`, e é ele que está acima. O brief §12 pede mypy; é uma
divergência do brief contra a árvore, não uma etapa pulada.

```
$ uv run pytest packages/core/tests/unit -q
850 passed in 70.50s

$ uv run python infra/scripts/check_file_size.py
error   369 > 350  packages/core/hunter_core/strategies/breakout_v1.py
scanned 545 files; 1 over budget, 0 grandfathered
```

O único arquivo acima do orçamento é o `breakout_v1.py` do agente em paralelo (T3.33a, em voo).
O meu tem **338 linhas**.

### Isolamento do digest — a asserção obrigatória do §2

```
$ uv run python -c "from hunter_strategy_worker.code_ref import module_closure, version_code_ref; ..."
momentum_v1        hunter_core.strategies.momentum_v1@sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
volume_anomaly_v1  hunter_core.strategies.volume_anomaly_v1@sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
mean_reversion_v1  hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
closure(mean_reversion_v1) = ('aggregate','base','canonical','envelope','indicators','mean_reversion_v1','numeric','schema')
registry_key('mean_reversion','v1') -> mean_reversion_v1 -> resolvido: mean_reversion_v1 v1 15m
roster: ['breakout_v1', 'mean_reversion_v1', 'momentum_v1', 'volume_anomaly_v1']
```

Os dois digests vivos são **byte a byte** os do brief §2. O digest da versão nova está aí para o
operador comparar no momento da ativação; **não** o pinei em `FROZEN_DIGESTS`, de propósito: até a
ativação ele não protege nada e faria toda correção de revisão quebrar o teste. (O agente da T3.33a
escolheu pinar o dele; é decisão dele, e é a causa da falha `breakout_v1` que aparece na suíte do
worker enquanto ele ainda edita o módulo.)

### A prova de que os testes mordem — duas mutações deliberadas

Rodadas e **revertidas**, com `sha256sum -c` confirmando o arquivo idêntico depois:

| mutação | o que ela simula | resultado |
|---|---|---|
| `trend_bars[:-1]` -> `trend_bars[1:]` na SMA | a barra corrente entra na própria média | **4 testes falham**, incluindo `test_the_forming_hour_never_reaches_the_trend_gate` |
| `align_open_time(cut, trend_timeframe)` -> `cut` | a porta de tendência olha a hora ainda aberta | `test_the_forming_hour_never_reaches_the_trend_gate` falha (a decisão some) |

```
$ sha256sum -c /tmp/mr.sha
packages/core/hunter_core/strategies/mean_reversion_v1.py: OK
```

### Números exatos da série sintética (todos escritos à mão, nenhum lido da implementação)

100 barras de 15 min: rampa de fechamentos 20→99, patamar em 100, e o recuo fechando em 99 com
máxima 100,75 e mínima 96,25. Toda barra tem meia-amplitude 2,25 e todo passo de fechamento é
`|Δ| ≤ 2,25`, então **todo true range vale 4,5** e o ATR de Wilder(14) é 4,5 sem arredondamento.

| grandeza | valor exato | de onde sai |
|---|---|---|
| `sma_15m` | 99,95 | (19×100 + 99)/20 |
| `sd_15m` | 0,2179449471770336776118490992 | `sqrt(0,0475)` sob `CONTEXT` |
| `zscore_15m` | −4,358898943540673552236981984 | −0,95 / sd |
| `close_1h` / `sma_1h` | 99 / 75,2 | hora 24 vs média das horas 4–23 |
| ATR / ATR% | 4,5 / 0,04545454545454545454545454545 | Wilder(14) sobre 97 barras; 4,5/99 |
| referência / stop / alvo1 / alvo2 | 99 / 94,5 / 105,75 / 110,25 | 1,0 e 1,5 e 2,5 ATR |

A aritmética do z-score é conferida à parte contra a série do brief §10.2 (`[100]×19 + [97]`), com
média, variância populacional e desvio calculados **no teste**, em `Decimal`, sem `pytest.approx`.
E há um teste de fronteira em que o z é **exatamente −1** (dez fechamentos em 101 e dez em 99):
a regra é `z <= −zscore_depth_min`, inclusiva, e o teste prova a inclusão.

## RECIBO do replay — **não houve replay**, e o motivo é estrutural

**Nenhuma coorte foi criada. Nenhuma corrida foi executada. O banco da VPS não foi tocado nesta
tarefa — nem leitura.**

`replay.run` resolve `--version mean_reversion:v1` por `resolve_version` ->
`load_active_versions`, que só enxerga versões **ativadas** em `strategy_versions`
(`replay/plan.py:62`). Sem ativação a corrida termina em
`SystemExit: version 'mean_reversion:v1' is not one runnable version`. A ativação está proibida no
meu escopo ("NÃO ative a versão"), então o replay do dia um é **do operador**, nesta ordem:

```bash
# 1. semear a descrição nova da família (a chave já existe como draft)
docker exec -i hunter-api-1 python - < infra/scripts/seed.py
# 2. ativar — congela code_ref, parameters_schema e default_parameters; irreversível
docker exec -i hunter-api-1 python - mean_reversion v1 --dry-run \
  --changelog 'T3.33b: pullback in a 1h uptrend, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
docker exec -i hunter-api-1 python - mean_reversion v1 \
  --changelog 'T3.33b: pullback in a 1h uptrend, research cohort (research_only, no wallet)' \
  < infra/scripts/activate_strategy_version.py
# 3. replay em duas fatias contíguas, MESMA coorte, cada uma < 4 min de relógio
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version mean_reversion:v1 --from 2026-08-08 --to 2026-08-23 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:<uuid> --ledger /tmp/replay-mean-reversion-v1.jsonl
docker exec hunter-strategy-worker-1 python -m hunter_strategy_worker.replay.run \
  --version mean_reversion:v1 --from 2026-08-23 --to 2026-09-08 \
  --markets ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT --workers 3 \
  --cohort replay:<mesmo uuid> --ledger /tmp/replay-mean-reversion-v1.jsonl
```

**Antes de ativar, confira o digest**: a versão só pode ser congelada com
`hunter_core.strategies.mean_reversion_v1@sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f`.
Qualquer correção de revisão no módulo muda esse valor — remeça antes.

### A tabela do recibo, com as colunas já declaradas e **sem número inventado**

| fatia | coorte | mercados | barras | decisões | `unavailable` | `not_triggered` | desfechos | `E_bruta` | `E_liq` | PF | cobertura `R_net` |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-08-08 → 08-23 | — | — | — | — | — | — | — | — | — | — | — |
| 2026-08-23 → 09-08 | — | — | — | — | — | — | — | — | — | — | — |

Além dessas colunas, o dia um **tem de publicar** (compromissos assumidos no portão C1–C8 e no §7
do brief):

- a **distribuição de `z` no instante da decisão** — sem ela, `zscore_depth_min = 1` continua sendo
  convenção e não quantil;
- a **quota de barras recusada por cada porta** (`no_uptrend_1h`, `not_stretched`, `close_below_mid`,
  `atr_out_of_range`), para saber qual porta está pagando por si;
- `gap` e `trend_gap` **separados** — com a ressalva do CONCERN 2: `trend_gap` virá zero por
  construção;
- a decomposição **por regime de BTC e por decil de ATR%** (era a instrução de revisão do C4);
- a expectancy **com e sem** a porta de tendência sobre a mesma população de recuos.

Critérios de morte congelados **antes** de rodar: K1–K5 de `notes-T3.33.md` §5.1. Para esta versão o
que vigiar é o **K2**: um portão de 1 desvio dispara muito, e passar de 1 500 decisões em 31 dias ×
4 mercados significa que a profundidade é um relógio, não uma condição.

## O teto de custo desta geometria (a confirmação que a `notes-T3.32.md` pediu)

A T3.32 mediu, em dez populações, `custo_R × risco%_do_preço = 0,0020` **constante** (desvio
≤ 1,9×10⁻⁵). É aritmética de 20 bps de ida e volta, não estatística. Reproduzido em `Decimal`
(`prec = 28`) para esta geometria, em que `stop = 1,0 ATR` e portanto `risco% = ATR%`:

```
teto de custo (custo_R x risco%_do_preco = 0,0020)
mean_reversion_v1 no piso ATR%   risco%=0.006      custo_R=0.3333
mean_reversion_v1 no teto ATR%   risco%=0.05       custo_R=0.0400
momentum_v1 no piso ATR%         risco%=0.0045     custo_R=0.4444
momentum_v4 (piso 0,0089)        risco%=0.01335    custo_R=0.1498
```

**O teto é 0,3333 R por operação**, no pior caso admissível. Fica **abaixo** do teto do
`momentum_v1` (0,4444 R) apesar do stop mais apertado em ATR, e muito abaixo do custo **medido** da
`volume_anomaly v2` no replay (0,6152 R). É isso que o piso de ATR% em 0,006 compra, e é a única
razão pela qual a geometria "1,0/1,5" é defensável.

A tabela de equilíbrio do brief §5 também foi reproduzida do zero, e bate dígito a dígito:

```
geometria           ATR%      R_net alvo   R_net stop   equilibrio
1,5/1,0 recusada     0.003       0.1955      -1.2736       0.8669
1,5/1,0 recusada     0.010       0.5122      -1.0888       0.6801
1,0/1,5 escolhida    0.006       1.0592      -1.2112       0.5335
1,0/1,5 escolhida    0.008       1.1614      -1.1619       0.5001
1,0/1,5 escolhida    0.050       1.4412      -1.0267       0.4160
momentum 1,5/1,5     0.003       0.4893      -1.2736       0.7224
```

## Portão C1–C8 — veredito

**`REVISE`**, escore 65,5. Tabela completa, critério a critério, na seção nova do `EXP-0009`.
Resumo: C1 80 · C2 60 · C3 80 · **C4 40** · C5 80 · C6 80 · **C7 50** · **C8 10**.

- **C4** (plano sem regime) — corrigido **na avaliação**, não no protocolo congelado: o dia um
  publica a decomposição por regime e por decil de ATR%. Mesmo com C4 = 80 o escore vai a 69,5 e
  continua `REVISE`, porque um `fail` sozinho já impede `PASS`.
- **C7** (sem filtro de volume) — **recusado com motivo**: um portão de volume mudaria a tabela
  congelada e faria esta versão medir o mesmo eixo da `volume_anomaly_v1`.
- **C8** (sem invalidação) — **recusado, e é o desenho**: braço `INV-B` da KB-0006. O portão pontua
  a ausência como defeito porque foi calibrado para estratégias que têm invalidação; aqui a ausência
  **é** a hipótese.

Limite do próprio portão, declarado: o C3 estima oportunidades com base 252 (barra diária, ações).
Esta versão avalia 96 barras/dia/mercado — a leitura honesta não é escassez de amostra, é o risco
oposto (K2).

## Os MUST-FIX da Astra que se aplicam a esta entrega

1. **Cortar informação no instante em que seria conhecida (MUST-FIX 3).** A porta de tendência usa
   `align_open_time(cut, 1h)`: a hora em formação **nunca** entra. Provado por mutação (tabela
   acima) e por um teste que muda o fechamento de uma barra **dentro** da hora em formação e exige
   que `close_1h` e `sma_1h` não se movam — enquanto o z-score de 15 min se move, que é o correto.
   Nenhum quantil sobre o mês, nenhum beta até o fim da amostra, nenhum funding futuro: esta versão
   não lê funding nem OI.
2. **Nunca tocar `base.py` nem o fecho (MUST-FIX 1).** Zero edições nos nove módulos do fecho; o
   z-score vive no módulo da estratégia. Digests vivos provados imóveis por teste.
3. **Separar instrumento de sinal, de resultado (MUST-FIX 2).** Registrado, **não resolvido aqui**:
   o replay seleciona `PERPETUAL` (`replay/plan.py`) e qualquer leitura desta versão é sobre perp.
   Ela **não** é evidência de rentabilidade spot, e o EXP diz isso. Resolver exige contexto novo, o
   que é brief próprio.
4. **Não confundir saída ruim com efeito causal da saída (MUST-FIX 5).** `invalidations = ()` aqui é
   escolha de desenho sobre uma **população própria** — não o contraste pareado `INV-A/B` da
   KB-0006, que é o `brief-T3.27`. Está escrito no módulo, no EXP e aqui.

## CONCERNS

1. **O portão diz `REVISE` e eu implementei mesmo assim.** É o pedido explícito do brief, e as três
   instruções de revisão estão respondidas uma a uma (uma aceita, duas recusadas com motivo). Quem
   ativar está ativando uma versão com veredito `REVISE` **declarado**, não escondido.
2. **`trend_warmup` e `trend_gap` são ramos mortos com os parâmetros congelados.** A janela de ATR
   alcança 1455 min para trás; a de tendência, no pior caso, 1305. A de tendência é **subconjunto**
   da de ATR, então todo buraco dela também é buraco da de ATR e sai como `atr_gap` primeiro. Os
   dois ramos existem, estão testados (por variante, `trend_sma_bars = 40` e `atr_bars = 20`) e há um
   teste `test_the_atr_window_dominates_the_trend_window` que **documenta a dominância** para
   ninguém ler o zero do replay como boa cobertura. Consequência prática: a promessa do brief §7 de
   "reportar `trend_gap` separado" é honesta mas vazia — o número informativo é o `atr_gap`.
3. **`close_1h`/`sma_1h` são nomes fixos, e `trend_timeframe` é parâmetro.** Uma variante que
   mudasse `trend_timeframe` para `15m` gravaria um `close_1h` que não é de 1 h. Segui o brief §9 e a
   convenção que o `momentum_v1` já tem (`atr_pct_15m` com `atr_timeframe` parametrizado), para o
   envelope ser consultável por nome estável. É uma dívida da família inteira, não desta versão.
4. **`zscore_depth_min = 1` e `zscore_bars = 20` são convenção, não medida.** Declarado no brief, no
   EXP e no código. O dia um tem de publicar a distribuição de `z` para que uma v2 escolha um
   quantil em vez de um número redondo.
5. **`trend_sma_bars = 20` foi escolhido pelo orçamento de contexto, não pelo mercado.** 21 barras
   horárias cabem em 1560 min; 51 não cabem. É uma restrição de infraestrutura virando parâmetro de
   pesquisa, e isso precisa estar na leitura de qualquer resultado.
6. **A geometria "1,0/1,5" contraria a forma clássica da família.** Reversão à média clássica é alvo
   pequeno e stop largo; aqui é o contrário, por aritmética de custo. Se a hipótese falhar, uma das
   explicações possíveis é **essa inversão**, não a reversão em si — e o EXP não consegue separar as
   duas. Ficou registrado.
7. **Multiplicidade.** É uma de quatro versões abertas no mesmo dia (KB-0010). O veredito desta tem
   de ser lido sabendo que houve quatro.
8. **Duas falhas de suíte que não são minhas, observadas ao rodar tudo junto:**
   - `services/strategy-worker/tests/test_constraints_outside_freeze.py::…[breakout_v1]` — o agente
     da T3.33a pinou o digest do módulo dele e continua editando o módulo. Não toquei;
   - `packages/core/tests/unit/test_runtime.py::test_role_registry_starts_empty_for_t03` — falha
     **só** quando a suíte do `strategy-worker` roda no mesmo processo (reproduzido com
     `pytest services/strategy-worker/tests packages/core/tests/unit/test_runtime.py`), e passa com
     `pytest packages/core/tests/unit` (850 passed). Verifiquei que **não** vem dos meus imports:
     `import hunter_strategy_worker.code_ref, .config, .main` deixa `RoleRegistry` vazio. É
     poluição de estado global entre suítes, anterior a esta tarefa.
9. **Nenhuma dessas leituras é validação.** Nada rodou contra dado real. `Result` do EXP-0009
   continua `inconclusivo`, e o replay do dia um, quando vier, sai rotulado **REPLAY** — mesma
   janela que gerou a hipótese.
