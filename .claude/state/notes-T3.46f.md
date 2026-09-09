# T3.46f — a ordem de leitura do scanner: snapshot primeiro, corte depois

**Owner:** quant-engineer · **Data:** 2026-09-08 (Brasília) · **Base:** `main` @ `1ea2d2f` ·
**Nada foi commitado.** Árvore compartilhada: outros agentes têm mudanças em voo nela (não tocadas).

Leituras da VPS: **23:10 → 23:41 de Brasília (02:10 → 02:41 UTC do dia 09)**. Somente leitura:
`redis-cli hget/hmget/mget/--scan/--latency-history`, `psql` em
`begin transaction isolation level repeatable read read only`. Nenhum container parado, recriado ou
alterado; nenhuma escrita; nada publicado.

---

## STATUS

**DONE_WITH_CONCERNS.** A ordem de leitura foi invertida (o scanner lê o hot state primeiro e relê
`covered_until` depois), com prova de que o teste novo falha na ordem antiga e passa na nova, contra
Redis de verdade e contra fake. **Mas a meta do item 4 do brief (`< 10/200`) não é alcançável só com
esta correção, e eu medi isso antes de escrever a primeira linha de código:** com as duas leituras
coladas (o que a nova ordem produz), o `after_cut` cai de ~89-95 % para **~43 %**, não para < 5 %. O
resíduo tem duas causas, ambas do lado do **market-worker** e ambas medidas aqui (§2): o carimbo de
cobertura roda num laço independente do que grava o livro (250 ms de fase) e o `covered_until`
agregado é o **mínimo entre 4 shards** (dispersão p50 = 283 ms). §6 diz exatamente o que fecha o
resto e quanto vale cada parte.

---

## 1. A TRILHA DE LEITURA DE HOJE (item 1 do brief)

Três lugares, nesta ordem:

1. `services/scanner-worker/hunter_scanner_worker/runners.py:73`, uma vez por ciclo, **antes** de
   qualquer mercado:
   ```python
   scanner.coverage = await read_coverage(redis, config.exchange, now=now)
   due = scanner.state.due(now, config.feature_throttle_s)
   for market in due[: config.max_markets]:
       evaluation = await scanner.advance(redis, market, batch, now=now)
   ```
2. `scanner.py:129` → `context.py::build_market_context`, uma vez por mercado. Era:
   ```python
   moment = now or utcnow()
   as_of, covers_from, covered_until = evaluation_cut(coverage, symbol, now=moment)   # corte
   raw = await read_hot_state(redis, exchange, symbol, market_type=market_type)       # livro
   ```
   `evaluation_cut` **não faz IO**: ele lê o objeto `TapeCoverage` que o laço leu no topo do ciclo.
   `read_hot_state` (`packages/indicators/.../hotstate.py:88`) faz um pipeline com
   `lrange candles`, `get book`, `lrange trades`, `hgetall deriv`.
3. as features são calculadas contra `as_of` (`decode_book(raw.book, as_of)`,
   `decode_trades(..., as_of, ...)`, `decode_deriv(..., as_of)`, `history_entry(..., as_of)`) — **e
   continuam assim**, nada disso mudou.

**O resíduo é o intervalo entre (1) e (2).** Não é o round-trip de uma leitura: é a posição do
mercado dentro do ciclo. O corte é lido uma vez, os 200 mercados são avaliados em sequência, e o
livro do mercado de índice 150 é lido centenas de milissegundos (ou segundos) depois do corte com que
vai ser comparado.

---

## 2. MEDIÇÃO — quanto cada causa vale (feita **antes** do código)

### 2.1 Método

Experimento pareado, 150 s, 5 mercados, um ciclo por `docker exec` (o próprio round-trip do SSH pauta
a cadência). Cada ciclo lê o corte, **depois** os livros, **depois** o corte de novo — o mesmo livro
comparado com o corte de antes (ordem velha) e com o de depois (ordem nova):

```bash
ssh hunter-vps '
END=$((SECONDS+150)); i=0
while [ $SECONDS -lt $END ]; do
  i=$((i+1)); echo "===CYCLE $i==="
  docker exec -i hunter-redis-1 sh -c "redis-cli hget mkt:binance:coverage covered_until; \
    redis-cli --no-raw mget mkt:binance:BTCUSDT:book mkt:binance:ETHUSDT:book \
    mkt:binance:LTCUSDT:book mkt:binance:HBARUSDT:book mkt:binance:ATOMUSDT:book; \
    redis-cli hget mkt:binance:coverage covered_until"
done
echo "TOTAL_CYCLES $i"'
```
```
TOTAL_CYCLES 1806
```

`ts` extraído do msgpack cru por regex sobre a saída `--no-raw` (texto escapado, nunca binário na
tela), deltas calculados localmente. **9 025 pares válidos.**

### 2.2 A ordem, sozinha, não fecha nada — porque o intervalo entre as duas leituras já era ~0

```
cycles usable: 1805
OLD    n=9025 p50=-55.0ms p90=379.0ms p99=1102.0ms min=-1377.0 max=2451.0 after_cut%=43.2
NEW    n=9025 p50=-60.0ms p90=376.0ms p99=1102.0ms min=-1377.0 max=2451.0 after_cut%=42.6
BTCUSDT   n=1805 old_after_cut%=50.4 new_after_cut%=49.9
ETHUSDT   n=1805 old_after_cut%=51.0 new_after_cut%=50.4
LTCUSDT   n=1805 old_after_cut%=42.2 new_after_cut%=41.4
HBARUSDT  n=1805 old_after_cut%=34.1 new_after_cut%=33.6
ATOMUSDT  n=1805 old_after_cut%=38.4 new_after_cut%=37.8
gap A->C (ms): p50=0.0 p90=0.0 max=655.0
```

Lido assim, "inverter a ordem" muda 0,6 ponto. **O que a inversão realmente compra é apagar o
intervalo**, e é por isso que ela vale ~46 pontos na produção: o mesmo conjunto de dados,
comparando o livro de cada ciclo com o corte lido **k ciclos antes** (o que o laço do scanner faz
hoje), dá a curva do `after_cut` em função do intervalo:

```
lag_ciclos  gap_medio_ms  after_cut%   (cut lido k ciclos ANTES do livro)
         0             0       43.2   n=9025
         1            83       54.7   n=9020
         2           166       65.7   n=9015
         3           249       75.7   n=9010
         5           414       90.3   n=9000
         8           663       97.8   n=8985
        12           995       99.6   n=8965
        18          1493      100.0   n=8935
```

**414 ms de intervalo = 90,3 % de `after_cut`** — exatamente o que o heartbeat mostra (§4.1: 168/200
= 84 %, e 178/200 no brief). A correção leva o scanner do regime "≥ 400 ms" para o regime "0 ms",
isto é, **de ~90 % para ~43 %**.

### 2.3 O que sobra em 43 % — duas causas, as duas no market-worker

Distribuição só dos casos que continuam `after_cut` na ordem nova:

```
apenas os casos after_cut na ordem NOVA: n=3846
  book.ts - covered_until: p50=187ms p90=589ms p99=1528ms max=2451ms
  <= 250ms: 60.6%   <= 500ms: 84.9%   <= 1000ms: 96.9%
  ainda after_cut se o cut fosse relido 1 ciclo  (~83ms)  depois: 75.1%
  ainda after_cut se o cut fosse relido 3 ciclos (~249ms) depois: 39.7%
  ainda after_cut se o cut fosse relido 6 ciclos (~498ms) depois: 15.4%
```

Segunda medição (90 s, 1 052 ciclos, ordem nova), comparando o mesmo livro com o corte agregado e com
o `until` do **shard que é dono daquele símbolo** (`mkt:binance:coverage:shards`):

```
ciclos=1052
  after_cut BTC_min      =  53.9%     (corte agregado = min dos 4 shards)
  after_cut BTC_shard3   =  25.7%     (o shard que coleta BTCUSDT)
  after_cut ETH_min      =  51.3%
  after_cut ETH_shard0   =  21.3%
  dispersao entre os 4 shards (max-min): p50=283ms p90=727ms max=2021ms
```

Ou seja, do resíduo de ~52 %:

- **~26 pontos são a agregação `min` entre 4 shards** (T2.5g): o livro de um mercado do shard 3 é
  comparado com o mínimo dos quatro coletores, e um shard atrasado impõe seu atraso a todos os
  outros. O `min` é a resposta certa para uma pergunta global ("até quando **todo** o universo está
  provado?") e a resposta errada para a pergunta por mercado ("até quando **este** símbolo está
  provado?");
- **~21-26 pontos são a fase entre dois laços do market-worker**: o livro é gravado pelo
  `coalesce_loop` a cada `tick_coalesce_ms` = 250 ms (`coalesce.py:234`) e o `covered_until` é
  carimbado pelo laço de housekeeping a cada `COVERAGE_STAMP_S` = 0,25 s (`streaming.py`), sem
  nenhuma ordem causal entre os dois. Quando o flush cai depois do último carimbo, o livro que ele
  grava carrega um `ts` que a prova ainda não cobre — mesmo com a `observe_proof` da T3.46d, que
  garante o valor certo mas não o **momento** certo.

Nenhuma das duas é do scanner e nenhuma é resolvível por ordem de leitura. §6 diz o que resolve.

---

## 3. O CONSERTO (item 2 do brief) — ordem, não tolerância

`build_market_context` passou a ser:

```python
moment = now or utcnow()
raw = await read_hot_state(redis, exchange, symbol, market_type=market_type)
# T3.46f: after the snapshots, never before them. ``coverage`` is the
# per-cycle read (it carries the ``sym:*`` roster); this re-read only moves
# ``covered_until`` forward, and only within the same session.
coverage = await refreshed_cut(redis, coverage, exchange=exchange, market_type=market_type)
as_of, covers_from, covered_until = evaluation_cut(coverage, symbol, now=moment)
```

`refreshed_cut` (novo, em `hunter_scanner_worker/coverage.py`) faz um `HMGET` de **dois campos**
(`session_since`, `covered_until`) — não um `HGETALL`, porque o hash também carrega um campo
`sym:*` por símbolo assinado (200 hoje), e o roster não muda entre duas leituras coladas. O valor
mais recente vence, com três recusas explícitas em `TapeCoverage.advanced_to`:

1. nada publicado, ou nada para avançar → o objeto volta intacto;
2. **`session_since` diferente**: o coletor reconectou entre as duas leituras, e levantar o corte
   mantendo o `covers_from`/roster da sessão anterior seria reivindicar cobertura **por cima do
   buraco** que a reconexão é. Nesse caso o comportamento é byte a byte o de antes da T3.46f;
3. corte que não andou para frente (leitura de réplica atrasada) → fica o maior dos dois.

`decode_book`, `MarketContext.__post_init__` e o corte `ts > as_of` **não foram tocados**: um
snapshot ainda à frente do corte relido continua recusado como `after_cut`, e existe um teste que
prova isso (`test_a_book_still_ahead_of_the_re_read_cut_is_refused`). `packages/indicators` não foi
alterado — o helper de leitura da prova é do scanner, que é quem conhece a semântica da cobertura.

### 3.1 O argumento de não-antecipação

- `covered_until` continua sendo **prova publicada**, nunca o relógio e nunca uma tolerância. Depois
  da T3.46d ele é o `ts` do último evento que o coletor **já aceitou** (`observe_proof`), limitado ao
  próprio relógio do carimbo. Relê-lo mais tarde não muda a natureza do valor: continua sendo uma
  afirmação sobre o passado, feita pelo processo que tem a prova.
- A relação temporal fica **a favor** da não-antecipação, não contra: antes, o corte era lido **antes**
  dos bytes com que seria comparado (e por isso não podia cobri-los); agora é lido **depois** deles.
  Um corte publicado depois da leitura de um snapshot só pode estar atrás dele por uma corrida real
  dentro do coletor — e essa corrida continua sendo **recusa**, exatamente como hoje.
- `as_of` pode ficar alguns milissegundos à frente do `now` que o ciclo capturou (o ciclo demora).
  Nunca à frente do relógio de parede real, porque é uma prova que o coletor já publicou.
  `ContextBuild.lagged_s` já era `max(0.0, ...)`; documentei isso no campo.
- `source_bar_close` é alinhado ao minuto (`PIPELINE.md` §2, "Anti-look-ahead"). O corte anda
  milissegundos **dentro do mesmo minuto** (o pior caso medido, p99, é 1,5 s = 2,5 % de um minuto),
  então nenhuma estratégia passa a enxergar a barra de decisão seguinte. As bar-features continuam
  lendo só candles `is_final` com `close_time <= as_of`.
- Efeito colateral positivo, verificado: `Scanner.regime_for(as_of)` **retém** um regime mais novo
  que o corte (`ScoreContext` recusa evidência posterior ao corte). Com o corte mais fresco, o
  componente de regime deixa de ser retido em parte dos mercados — nunca o contrário.

### 3.2 Custo

Dois round-trips por mercado por ciclo em vez de um. Medido na VPS
(`docker exec hunter-redis-1 redis-cli --latency-history -i 2`, 8 s):

```
0 2 0.30 10
0 2 0.21 24
0 2 0.20 40
```
(min 0 ms, max 2 ms, **média 0,20-0,23 ms**) → ~40 ms a mais por ciclo de 200 mercados, contra
~90 % de snapshots de livro que deixam de ser recusados. Registrado no docstring da função.

**Alternativa avaliada e descartada:** pendurar o `HMGET` no **mesmo** pipeline de `read_hot_state`
(ordem garantida pelo servidor, zero round-trip extra). Descartei por dois motivos: `hotstate.py`
está exatamente em **350/350** linhas (teto do `check_file_size.py`), então caberia só cortando
docstring alheio; e faria `hunter_indicators` conhecer a semântica de cobertura, que a T3.46d
deliberadamente manteve fora dele. Fica registrado como opção se o custo de 40 ms/ciclo incomodar.

---

## 4. ANTES (item 4 do brief) — o depois depende do deploy

### 4.1 Heartbeat do scanner, 23:39:57 BRT (02:39:57 UTC de 09/09)

```
$ redis-cli hmget hb:scanner:617fdf42d177:1 markets detectors_disarmed baselines_usable ts
200
... ORDERBOOK_IMBALANCE:baseline_absent=6,ORDERBOOK_IMBALANCE:baselines_under_construction=25,
ORDERBOOK_IMBALANCE:feature_after_cut=168,ORDERBOOK_IMBALANCE:feature_missing_input=1, ...
12914
2026-09-09T02:39:57.830514+00:00
```

`ORDERBOOK_IMBALANCE:feature_after_cut = **168/200** (84 %)`.

### 4.2 `feature_snapshots`, 30 minutos até 23:41 BRT (02:41 UTC), somente leitura

```sql
begin transaction isolation level repeatable read read only;
with recent as (select market_id, features->'values' as v from feature_snapshots
                where ts >= now() - interval '30 minutes'),
     f(feature) as (values ('orderbook_imbalance_20'),('spread_pct'),('trade_velocity_1m'))
select f.feature, count(*) linhas,
       count(*) filter (where r.v -> f.feature ->> 'quality' = 'ok') ok, ...
```
```
== 1. qualidade (ultimos 30 min) ==
+------------------------+--------+------+-------------+--------+-------------+
|        feature         | linhas |  ok  | unavailable | pct_ok | mercados_ok |
+------------------------+--------+------+-------------+--------+-------------+
| orderbook_imbalance_20 |   5804 |  307 |        5497 |    5.3 |         122 |
| spread_pct             |   5804 |  307 |        5497 |    5.3 |         122 |
| trade_velocity_1m      |   5804 | 5392 |         412 |   92.9 |         204 |
+------------------------+--------+------+-------------+--------+-------------+

== 2. motivo (ultimos 30 min) ==
| orderbook_imbalance_20 | after_cut     | 5493 |
| orderbook_imbalance_20 | missing_input |    4 |
| spread_pct             | after_cut     | 5493 |
| spread_pct             | missing_input |    4 |
```

**Previsão conferível depois do deploy (não uma esperança — a curva do §2.2 aplicada ao ciclo
real):** `feature_after_cut` deve cair de ~168-178/200 para **~85-110/200** e o `pct_ok` de
`orderbook_imbalance_20`/`spread_pct` deve subir de 5,3 % para **~45-57 %**. Se cair para menos que
isso, algo além da ordem de leitura melhorou junto; se ficar acima de ~120/200, a hipótese do §2.2
está errada e o próximo passo é instrumentar `refreshed_cut` (um log por mercado com o par
`covered_until` lido / `book.ts`) em vez de repetir a medição.

Repetir depois do deploy, sem alterar nada:

```bash
ssh hunter-vps 'docker exec -i hunter-redis-1 redis-cli hget hb:scanner:<instancia>:1 detectors_disarmed'
```

---

## 5. TESTES

### 5.1 Unitários — a ordem de leitura, com um coletor que não para (item 3 do brief)

`services/scanner-worker/tests/test_coverage.py`, 5 casos novos. O duplo é um `FakeHotState` em que
**toda leitura custa um tique** e um tique é o que os dois laços do market-worker fazem juntos: o
coalescer grava um livro mais novo e o housekeeping carimba uma cobertura que o cobre.

```bash
uv run pytest services/scanner-worker/tests/test_coverage.py -q -p no:randomly
```
```
............                                                             [100%]
12 passed in 3.27s
```
(7 pré-existentes, nenhum alterado, + 5 novos.)

**Prova de que o teste tem dentes** — com a ordem antiga restaurada à mão em `context.py` (corte
antes do snapshot) e nada mais alterado:

```
        book = build.context.book
>       assert book.reason is None, "the book the collector had already written was refused"
E       AssertionError: the book the collector had already written was refused
E       assert 'after_cut' is None
E        +  where 'after_cut' = SourceEntry(value=None, ts=None, reason='after_cut', ...).reason

services\scanner-worker\tests\test_coverage.py:186: AssertionError
=========================== short test summary info ===========================
FAILED services/scanner-worker/tests/test_coverage.py::test_the_cut_read_after_the_snapshots_covers_them
1 failed, 11 passed in 3.11s
```

A ordem foi restaurada em seguida e conferida com `diff` contra a cópia guardada antes do
experimento (`IDENTICO ao estado pos-fix`), e os 12 voltaram a passar.

Os cinco:

- `test_a_cut_read_before_the_book_is_already_behind_it` — a ordem antiga, mantida no arquivo como
  oráculo do que está sendo consertado (`decode_book(...).reason == AFTER_CUT`);
- `test_the_cut_read_after_the_snapshots_covers_them` — a ordem nova pelo caminho de produção;
- `test_the_re_read_never_lifts_the_cut_across_a_reconnection` — `session_since` diferente entre as
  duas leituras não levanta corte nenhum;
- `test_the_re_read_never_moves_the_cut_backwards` — a relectura nunca anda para trás, e um campo
  ausente não vira zero;
- `test_an_absent_proof_stays_absent_after_the_re_read` — sem prova publicada, continua sem prova
  (as janelas de fita seguem `insufficient_coverage`).

### 5.2 Testcontainer — a mesma ordem contra um Redis de verdade

Não existia teste de testcontainer no caminho de leitura de hot state do scanner (os que usam
container — `test_bootstrap`, `test_persistence`, `test_regime_job`, `test_beta_job` — não passam por
`build_market_context`). Criei **um** arquivo, `services/scanner-worker/tests/test_read_order.py`:
o cliente real é embrulhado por um duplo cuja única diferença é carimbar um `covered_until` novo
**depois** que o pipeline de hot state executa — que é literalmente o que o laço de housekeeping faz
enquanto o scanner decodifica.

```bash
uv run pytest services/scanner-worker/tests/test_read_order.py -q -p no:randomly
```
```
...                                                                      [100%]
3 passed in 6.82s
```

Três casos: a ordem antiga recusa o livro (oráculo), a ordem nova o aceita com
`as_of == carimbo relido` e `book.value.ts == BOOK_TS`, e **um livro ainda à frente do corte relido
continua recusado** — a prova de que nenhuma tolerância entrou junto.

Orçamento de testcontainer do brief respeitado: **duas invocações, ambas neste único arquivo** (a
segunda depois dos ajustes finais de docstring). Não rodei `test_bootstrap.py`/`test_persistence.py`
— eles importam `builders.FakeHotState`, que só ganhou um método novo (`hmget`), estritamente
aditivo.

### 5.3 Suíte inteira do serviço, sem container

```bash
uv run pytest services/scanner-worker/tests -q -p no:randomly -m "not integration"
```
```
105 passed, 45 deselected, 1 xfailed in 80.52s (0:01:20)
```
(100 antes + 5 novos; o `xfail` é o `test_load` de sempre — orçamento de latência da T2.5, estrito e
inalterado.)

### 5.4 Portões

```bash
uv run ruff check services/scanner-worker
```
```
All checks passed!
```
```bash
uv run ruff format --check services/scanner-worker/hunter_scanner_worker/coverage.py \
  services/scanner-worker/hunter_scanner_worker/context.py services/scanner-worker/tests/builders.py \
  services/scanner-worker/tests/test_coverage.py services/scanner-worker/tests/test_read_order.py
```
```
5 files already formatted
```
```bash
uv run pyright services/scanner-worker
```
```
0 errors, 0 warnings, 0 informations
```
```bash
uv run python infra/scripts/check_file_size.py
```
```
scanned 580 files; 0 over budget, 0 grandfathered
```
(`coverage.py` 139 → 227 linhas, `context.py` 187 → 213; teto 350, sem aperto em texto alheio.)

---

## 6. O QUE FECHA O RESTO (T3.46g sugerida, market-worker)

Em ordem de retorno medido, com o número do §2.3 ao lado:

1. **Carimbar a cobertura no mesmo pipeline do flush** (`coalesce.py::flush_ticks`), depois das
   escritas de livro, com a prova que aquele flush acabou de gravar. Isso dá ordem **causal** entre
   "o livro está no Redis" e "a prova cobre o livro", e mata a fase de 250 ms por construção —
   ~21-26 pontos. É o gêmeo exato da T3.46d: a T3.46d acertou **o valor** do carimbo, esta acertaria
   **o momento**;
2. **Publicar o corte por shard e o scanner ler o do dono do símbolo** (ou o agregado passar a ser
   por símbolo em vez do `min` global) — ~26 pontos. O `min` continua correto para perguntas globais;
   o que está errado é usá-lo para responder uma pergunta por mercado. `mkt:binance:coverage:shards`
   já publica `{i}of{n}:until` — o dado existe, falta o scanner ter permissão de brief para lê-lo.

Com as duas, e com a ordem de leitura desta tarefa, o `after_cut` deve ir a ~0 % — nenhuma delas
introduz tolerância nem antecipação.

---

## 7. ARQUIVOS

### Código (nada commitado)

| arquivo | o quê |
|---|---|
| `services/scanner-worker/hunter_scanner_worker/coverage.py` | `CUT_FIELDS`, `read_cut`, `refreshed_cut`, `TapeCoverage.advanced_to`; parágrafo T3.46f no docstring do módulo |
| `services/scanner-worker/hunter_scanner_worker/context.py` | ordem invertida em `build_market_context` (snapshots → relectura do corte → `evaluation_cut`); docstring do módulo com a ordem e o argumento de não-antecipação; custo dos dois round-trips no docstring da função; nota em `ContextBuild.lagged_s` |
| `docs/PIPELINE.md` | §2, uma bala nova ("a ordem de leitura faz parte do corte") |

### Testes

| arquivo | o quê |
|---|---|
| `services/scanner-worker/tests/test_coverage.py` | 5 casos novos + o duplo `TickingCollector`; 7 pré-existentes inalterados |
| `services/scanner-worker/tests/test_read_order.py` | **novo**, 3 casos contra Redis real (testcontainer) |
| `services/scanner-worker/tests/builders.py` | `FakeHotState.hmget` (5 linhas, aditivo) |

### Estado

- `.claude/state/notes-T3.46f.md` (este arquivo)

### Medição bruta (scratchpad da sessão, fora do repositório)

`t346f-raw.txt` (1 806 ciclos pareados), `t346f-shards.txt` (1 052 ciclos com os 4 shards),
`parse.py`/`lag.py`/`residual.py`/`shards.py`, `t346f.sql`.

---

## 8. CONCERNS

1. **A meta numérica do item 4 do brief não vai ser atingida por esta mudança** e eu sabia disso
   antes de codificar (§2). O brief supunha que a ordem de leitura era o resíduo inteiro; a medição
   diz que ela é ~46 dos ~89 pontos. Implementei mesmo assim porque a ordem está objetivamente
   errada do jeito que estava e porque é **pré-requisito** dos dois consertos do §6: com o corte de
   início de ciclo, mesmo um market-worker perfeito continuaria dando ~90 % de `after_cut`.
2. **A prova pós-deploy continua pendente do orquestrador.** Nada foi publicado (VPS somente
   leitura). §4 tem o "antes" completo e a previsão conferível.
3. **Custo de +1 round-trip por mercado por ciclo** (~40 ms num ciclo de 200, §3.2). Se isso
   incomodar o orçamento de latência (que já é `xfail` por outro motivo), a alternativa sem custo é
   pendurar o `HMGET` no pipeline de `read_hot_state` — exige liberar ~10 linhas em `hotstate.py`,
   que está em 350/350.
4. **`build_market_context` agora relê a cobertura em todo caminho, inclusive nos frios** (testes,
   `test_load`, qualquer chamador futuro sem laço). É uma leitura barata e o duplo de teste a
   responde, mas é um IO a mais num lugar que antes tinha um só — deixo explícito porque não é
   visível olhando só a assinatura, que não mudou.
5. **A janela de medição é de 150 s + 90 s numa noite** (23:11-23:22 BRT de 08/09), não de uma hora.
   São 9 025 + 1 052 ciclos, bem acima do piso de mil, e concordam com o heartbeat e com o SQL de
   30 minutos em ordem de grandeza (84-95 % de `after_cut` hoje), mas a decomposição do §2.3
   (26 pontos de shard, 21-26 de fase) vem só dessa janela.
6. **`services/strategy-worker/hunter_strategy_worker/context.py` tem um `build_market_context`
   próprio — conferi, e ele *não* tem este defeito:** corta em `source_bar_close` (alinhado ao
   minuto, recebido pelo chamador) e não lê livro nenhum, então não existe corrida de carimbo lá.
   Nada a fazer naquele serviço.

## §4 — prova pós-deploy (orquestrador, 2026-09-09 00:1x BRT, scanner em 188ff72)
Heartbeat `detectors_disarmed`, ORDERBOOK_IMBALANCE, de 200 mercados: ANTES `feature_after_cut=183` (baselines_under_construction=13). DEPOIS, minuto a minuto: 77, 55, 75, 51, 42, 64 (`baselines_under_construction` 106–135, `baseline_absent` 15–23). Melhor que a previsão (~85–110): a ordem de leitura removeu ~60–70 pontos; o resíduo (21–38 %) é o do coletor → T3.46g. O livro passou a alimentar a baseline: a partir de agora `sample_size` cresce até o portão 120.
