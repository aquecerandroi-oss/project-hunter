# T3.74g — o custo de uma avaliação: perfil, o corte, e o que sobra

Brief salvo em `.claude/state/brief-T3.74g-custo-por-avaliacao.md`. Tudo medido **localmente**
(perfil de CPU sem Docker + testcontainer); nada implantado, nada commitado, nenhum contêiner
tocado, nenhuma escrita na VPS, nenhum módulo de `packages/core/hunter_core/strategies/`
alterado. Hoje é 2026-09-10; horários em Brasília (UTC−3) com o UTC ao lado.

## 0. Resumo executivo

O perfil de uma barra inteira (50 mercados × 10 versões = 500 avaliações) diz que **59 % do
tempo de CPU não era estratégia nenhuma**: era o pydantic revalidando cada `NormalizedCandle`
a cada construção de `StrategyContext` — uma construção por versão, sobre a mesma janela do
mesmo mercado na mesma barra (1 182 000 execuções de `NormalizedCandle._check_invariants` por
barra, 8,56 s de 16,88 s). Ao lado disso, cada versão abria a própria sessão e fazia as
próprias leituras: com dez versões devidas, dez `hot_state.read_tail`, dez `load_derivatives`
(duas queries cada) e — desde a T3.74b — uma leitura de vela por *família* em vez de por barra.

**O corte** (`hunter_strategy_worker/bar_context.py`): uma leitura, uma montagem e **uma**
validação por `(mercado, barra)`; cada versão recebe uma *fatia* da janela já validada
(`bisect` + `model_copy`, que o pydantic documenta como não revalidante) e a sua própria
elegibilidade carimbada por cima. Nenhuma decisão muda — provado por igualdade de objeto
(`StrategyContext.__eq__`) no teste de unidade e por `Evaluation`/`Provenance` idênticas contra
Postgres real. Medido:

| medida | antes | depois |
|---|---|---|
| CPU por avaliação (50×10, sem banco; mediana de 4 execuções) | 13,1 ms | 8,6 ms |
| barra completa 50×10, só CPU | 6,5-7,4 s | 3,9-5,1 s |
| `load_candles` + `read_tail` + `load_derivatives` por barra (4 versões) | 12 idas | 3 idas |
| queries por avaliação (ponta a ponta, 4 versões) | 12,0 | 10,2 |

**O que isto não entrega**: o alvo do brief (≤ ~8 ms por avaliação na VPS, ~10× menos CPU). O
ganho medido é de ~1,5× (1,3-1,9× conforme a máquina respira). O que sobra está no §5, com os
dois próximos degraus e o preço de cada um — nenhum deles é uma mudança que este agente possa
tomar sozinho.

## 1. O perfil (entrega 1)

`cProfile` sobre uma barra equivalente a um shard: 50 mercados × 6000 velas de 1 min, dez
versões (8 variantes de `mean_reversion_v1`, `mean_reversion_h1_v1` v1 e `momentum_v1`), todas
devidas na mesma barra. Janelas efetivas derivadas por `required_context_minutes` e limitadas
pelo piso/teto vivos (1560/6000): 1560 (v1, v2, v3, v14, momentum), 1815 (v7, v8), 3165 (v6,
v10), 5880 (h1).

```
WALL boundary=6.57s  evaluations=500  per_eval=13.1ms
         30980062 function calls in 16.878 seconds   (sob cProfile)

   ncalls  tottime  cumtime  função
      500    0.015    9.915  strategies/base.py:167(build_context)          <- 59 %
      500    0.370    9.274  pydantic SchemaValidator.validate_python
  1182000    1.401    8.560  domain/market.py:281(NormalizedCandle._check_invariants)
     1450    1.758    6.616  strategies/aggregate.py:91(aggregate)          <- 39 %
  1183450    0.861    6.451  domain/market.py:65(is_aligned)
      400    0.029    4.807  strategies/mean_reversion_v1.py:150(explain)
  1184400    1.728    4.397  domain/market.py:47(align_open_time)
    78600    0.398    2.780  strategies/aggregate.py:77(_fold)
  2368850    1.415    2.420  domain/types.py:47(ensure_utc)
       50    0.009    1.560  strategies/mean_reversion_h1_v1.py:165(explain)
       50    0.002    0.534  strategies/momentum_v1.py:126(explain)
      550    0.328    0.623  builtins.sorted
```

Leitura, por fatia do brief:

- **objetos Python (churn)**: `build_context` = 9,92 s de 16,88 s. Praticamente tudo é
  `_check_invariants` **do candle**, chamado 1 182 000 vezes = 2364 velas × 500 construções. O
  pydantic 2.13 reexecuta o `model_validator(mode="after")` de um modelo aninhado mesmo com
  `revalidate_instances` no padrão (`never`) — verificado num caso mínimo de 12 linhas: 100
  `Inner` construídos uma vez, 10 `Outer` sobre a mesma tupla ⇒ 1100 execuções do validador.
  As velas já tinham sido validadas quando saíram do banco; a segunda a décima validação é
  trabalho puro;
- **recomputação de indicador**: `aggregate` = 6,62 s (39 %), sendo 2,78 s de `_fold`
  (`Decimal` max/min/sum por barra agregada). São 1450 chamadas: três por avaliação de
  `mean_reversion` (sinal 15 m, ATR 15 m, tendência 1 h) e duas de `momentum`. O ATR de 6000
  minutos aparece aqui, não separado: `wilder_atr` sozinho não chega ao top-20 (a recursão é
  sobre ~97 barras já agregadas; o caro é *agregar* 1455 minutos para chegar nelas);
- **banco**: zero neste perfil, por construção (é CPU pura). Medido à parte no §3;
- **gate/política**: não aparece — `evaluate_hours_gate` é aritmética e os gates de regime/
  breadth são queries (§3), não CPU.

Comando: `uv run python <scratch>/prof_eval.py` (harness de bancada; a versão versionada e
reprodutível dele é `services/strategy-worker/tests/test_evaluation_cost_benchmark.py`).

## 2. O corte (entrega 2)

`hunter_strategy_worker/bar_context.py` — `BarBundle`/`BarView`:

1. **uma leitura por `(mercado, barra)`, não por família nem por versão**: o teto
   (`max(context_minutes)` das versões devidas), a cauda do hot state e os derivativos são
   lidos **uma vez**, numa sessão só;
2. **uma validação por `(mercado, barra)`**: `build_context` — o de verdade, com o filtro
   anti-look-ahead e os invariantes estritos — roda uma vez sobre a janela do teto. Cada versão
   recebe `base.candles_1m[bisect_left(...):]`, um *sufixo* da série já ordenada e filtrada, e
   um `model_copy` com a elegibilidade dela. A janela de uma versão é sufixo da do teto porque
   as duas terminam no mesmo corte — é o mesmo argumento que `replay/candles.py::WindowCache`
   já fazia para as linhas, aplicado ao contexto;
3. **sem tocar em estratégia nenhuma**: `evaluate` continua recebendo velas de 1 min cruas e
   continua agregando por conta própria. `git diff --stat -- packages/core/hunter_core/strategies/`
   é vazio e os nove digests são os de hoje (§4).

O que **não** foi feito, e por quê: (b) do brief — manter a série *agregada* por
`(mercado, timeframe)` e anexar 15 min por barra — não é implementável sem mudar as
estratégias. Quem chama `aggregate(ctx.candles_1m, ...)` é o módulo congelado; entregar a ele
uma série pré-agregada exige mudar a assinatura de `explain`, o que move o `code_ref` e cria
população nova. A versão de (b) que sobra é incremental na *janela crua* (§5.2), com um preço
que não é meu para pagar sozinho.

Fallback: `load_bar_bundle` devolve `None` em qualquer falha e o consumidor volta para os
leitores de família da T3.74b — que por sua vez caem para leitura por versão. O caminho lento
continua sendo o caminho testado.

## 3. As provas

```
uv run pytest services/strategy-worker/tests/test_bar_context.py -q
12 passed in 1.07s

uv run pytest services/strategy-worker/tests/test_bar_context_engine.py -q -s
4 passed in 56.09s
  t374g_bundle_cost_against_postgres after_ms_per_evaluation=623.0 before_ms_per_evaluation=679.6
  (2 mercados × 4 versões contra Postgres em Docker Desktop/Windows: o número absoluto é
   latência de contêiner, não de produção — o que vale é a direção e as contagens abaixo)

uv run pytest services/strategy-worker/tests/test_evaluation_cost_benchmark.py -q -s   (4 execuções)
  before_ms_per_evaluation=11.52 / 13.07 / 13.17 / 14.82   (mediana 13,1)
  after_ms_per_evaluation= 7.41 /  9.53 / 10.15 /  7.76    (mediana  8,6)
  speedup=1.55 / 1.37 / 1.30 / 1.91

uv run pytest services/strategy-worker/tests -q -m unit
422 passed, 382 deselected in 38.12s

uv run pytest services/strategy-worker/tests/test_context_cache_engine.py -q -k TestEquivalence
1 passed, 1 deselected in 39.56s          (o cache de família da T3.74b continua equivalente)

uv run pytest services/strategy-worker/tests/test_shadow_decisions.py -q
15 passed in 95.10s

uv run pytest services/strategy-worker/tests/test_replay_engine.py -q
16 passed in 191.50s

uv run pytest services/strategy-worker/tests/test_replay_lookahead.py -q
6 passed in 49.67s

uv run pytest services/strategy-worker/tests/test_code_ref.py -q
27 passed in 2.30s

uv run ruff check services/strategy-worker/ -> All checks passed!
uv run ruff format --check services/strategy-worker/ -> 154 files already formatted
uv run pyright <arquivos desta tarefa> -> 0 errors, 0 warnings, 0 informations
uv run python infra/scripts/check_file_size.py -> scanned 623 files; 0 over budget
```

**Equivalência.** `test_bar_context.py` compara `bundle.view(m).context` com
`build_context(janela, ...)` para 1, 60, 240, 500 e 600 minutos (`==` do pydantic: campo a
campo, tupla de velas inclusive), compara a fatia durável com o que `load_candles` teria
devolvido, e prova que o corte sobrevive ao atalho — uma vela não final e uma vela que fecha
depois do corte entram no pacote e não aparecem em janela nenhuma; **mudar a vela em formação
não muda nada do que qualquer versão vê**. `test_bar_context_engine.py` faz a mesma prova pelo
worker: `build_market_context` com e sem pacote devolve `StrategyContext` igual e `Provenance`
igual (todos os campos menos `eligibility_observed_at`, que é relógio de parede de duas leituras
diferentes), e `evaluate_slot` devolve `Evaluation` idêntica (estado, motivo, detalhe, decisão)
para quatro versões em duas janelas distintas.

**O replay não é afetado**: `replay/simulate.py` chama `evaluate_slot` sem `bundle`, e
`bundle=None` é literalmente o caminho de antes (o `if view is None:` de `context.py` contém o
código de antes, intocado). `test_replay_engine.py` (16) e `test_replay_lookahead.py` (6) passam.

**Contagens (independentes de máquina)**, uma barra com 4 versões:

| ida | antes | depois |
|---|---|---|
| `load_candles` | 4 (1 por versão; 1 por família com a T3.74b) | 1 |
| `hot_state.read_tail` | 4 | 1 |
| `load_derivatives` (2 queries) | 4 | 1 |
| `SET LOCAL ROLE` + `SET LOCAL statement_timeout` | 4 sessões/versão × … | idem, menos a do contexto quando o pacote serve |
| **queries por avaliação** | **12,0** | **10,2** |

Decomposição do que sobra por avaliação (medido com um contador em `AsyncSession.execute`):
4 × preâmbulo de sessão (`SET LOCAL ROLE`, `SET LOCAL statement_timeout`, duas sessões por
versão), 4 × slot (`lock_slot` roda duas vezes: upsert + select cada), 1 × `slots.advance`.

## 4. `code_ref` intocado

```
git diff --stat -- packages/core/hunter_core/strategies/    (vazio)

breakout_v1 v1            sha256:4c920b0cc412429c2c4a6a19ca389aca8a215a638f0ff750a8caf61b16264ff1
mean_reversion_h1_v1 v1   sha256:cc18c3f1b380fa197645f284442c0433e06fbce1cea31b32c5542bf014006631
mean_reversion_v1 v1      sha256:a970c9d98fface2d714abdce25468828ee07087f9287fdb1239dadc3f0bd395f
momentum_v1 v1            sha256:ab2e039825c9334da5b81666791c0a782f25bb35a3cb9529391bdb238ebaa40c
session_orb_v1 v1         sha256:a4d514adeb0771d5ae23303878fb4fdac734721d6ac0140801c88d617e878bba
sweep_reclaim_v1 v1       sha256:a1150343f436494e9c007a1219c90c1467ecc9359d5ca0fa5e75658f0023556c
trendline_bounce_v1 v1    sha256:fb7263ce5f06956f6d57c86f2a0790c62644b3f453904d83546674de4dabdb75
trendline_breakout_v1 v1  sha256:7b83a1ff07946fa743d12c9d098f15b538c2e2b19f5269363203ee0671e19648
volume_anomaly_v1 v1      sha256:9b8c14ab3390646ac9adb26fbbb90e160a800f1c70f128d873a49ffd1dd19f22
```

`test_code_ref.py` (27 testes) passa, que é a prova de que o digest continua sendo o do código
que roda — os hashes acima são só o registro do dia.

## 5. O que sobra (entrega 3) — três perguntas para o orquestrador

Depois do corte, 8,6 ms de CPU por avaliação nesta máquina. **Não chega aos ~8 ms na VPS**, que
é mais lenta que este notebook por um fator que a T3.74f mediu indiretamente (80 ms/avaliação lá
contra 13,1 ms aqui, com banco e asyncio no meio). Onde está o que sobra:

### 5.1 `aggregate` dentro do módulo congelado — 72 % do que restou

`aggregate` custa ~6,2 ms dos 8,6 ms por avaliação (perfil depois do corte: 6,85 s de 9,52 s).
E é trabalho **repetido**: seis das oito variantes de `mean_reversion` usam
`atr_timeframe=15m, atr_bars=97`, então elas agregam exatamente a mesma janela do mesmo mercado
na mesma barra e chegam ao mesmo objeto. Deduplicar isso é a maior economia disponível — e é
impossível de fora: quem chama `aggregate` é o módulo cujo digest congela a versão, e
memoizar por *monkeypatch* faria o `code_ref` afirmar um código que não é o que executa (o
próprio `code_ref.py` chama isso de "a única direção em que o freeze nunca pode falhar").
**Pergunta:** vale uma família nova (`mean_reversion_v2`) que receba janelas pré-agregadas em
vez de velas cruas? É `code_ref` novo, população nova, coorte nova — decisão de pesquisa, não
de performance.

### 5.2 Materializar a janela crua — ~48 ms por (mercado, barra)

`load_candles` constrói `NormalizedCandle` a 15,3 µs cada (medido): 3165 velas = 48,3 ms, 6000
velas = 83,3 ms — **por mercado, por barra**, mesmo com o pacote (que já reduziu de 2-3 leituras
para 1). Num shard de 50 mercados isso é ~2,4 s de CPU por fechamento de 15 min (~4,2 s na hora
cheia, quando a versão de 1 h entra e o teto vira 5880). O degrau (b) do brief, na única forma
que existe sem mudar estratégia, é um cache **entre barras**: guardar a janela por mercado e
anexar os 15 minutos novos. Preço, os dois honestos:

- **frescor**: a janela vira fotografia. Um backfill que preencha um buraco antigo deixa de ser
  visto — o que hoje muda decisão (`aggregate` responde `gap` em vez de agregar). Dá para
  guardar com **uma** query barata por (mercado, barra) — `count(*)` e `max(received_at)` da
  janela, comparados com o que o cache tem — que pega inserção, remoção e atualização (o
  `received_at` anda para frente no upsert). Uma query agregada em vez de 3165 linhas;
- **memória**: ~0,8-1,8 KB por vela ⇒ 50 mercados × 5880 velas ≈ 235-540 MB **por processo de
  shard**, × 4 shards. Sem um teto LRU e sem saber o orçamento de RAM da VPS, isto troca um
  problema de CPU por um de OOM.

**Pergunta:** implemento com verificação por `count(*)`/`max(received_at)` e teto LRU, ou o
orçamento de memória da VPS não comporta?

### 5.3 O universo de sombra — a alavanca estrutural

Nenhum dos dois degraus acima muda o fato de que o custo é **linear em (mercados × versões)**.
Hoje são ~200 mercados × ~10 versões = ~2000 avaliações por fechamento de 15 min, divididas em
4 shards. As versões de pesquisa derivadas rodam sobre os 200 mercados, mas só 16 têm 90 dias
de histórico — a coorte comparável é a dos 16. Restringir o universo das versões *de pesquisa*
a esses 16 (mantendo as `paper` nos 200) cortaria as avaliações por barra em ~8× — mais do que
todo o trabalho desta tarefa somado. **Pergunta ao orquestrador, não mudança:** as versões
`research_only` precisam decidir sobre os 200, ou os 16 com histórico bastam? (Cortar isso muda
população, não código: é decisão de pesquisa.)

## 6. Arquivos

```
git status --porcelain (só os desta tarefa)
 M services/strategy-worker/hunter_strategy_worker/consumer.py
 M services/strategy-worker/hunter_strategy_worker/context.py
 M services/strategy-worker/hunter_strategy_worker/decide.py
?? services/strategy-worker/hunter_strategy_worker/bar_context.py
?? services/strategy-worker/tests/test_bar_context.py
?? services/strategy-worker/tests/test_bar_context_engine.py
?? services/strategy-worker/tests/test_evaluation_cost_benchmark.py
?? .claude/state/brief-T3.74g-custo-por-avaliacao.md
?? .claude/state/notes-T3.74g.md
 M docs/PIPELINE.md                    (§6b — orçamento de custo por avaliação)
 M obsidian/07-BUGS/Open Bugs.md       (entrada T3.73/T3.74)
```

Nada commitado (regra do brief). A árvore é compartilhada: outros arquivos aparecem em
`git status` e não são desta tarefa.
