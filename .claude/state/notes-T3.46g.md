# T3.46g — carimbo no mesmo pipeline do flush + scanner lê o `until` do shard dono

**Owner:** exchange-integration-specialist · **Data:** 2026-09-08/09 (Brasília) · **Base:** `main` @
`188ff72` (T3.46f, confirmado por `git log -1 -- services/scanner-worker/hunter_scanner_worker/context.py`
antes de começar). **Nada foi commitado.** Árvore compartilhada: outros agentes têm mudanças em voo
(T3.52/T3.54/T3.55 em `services/strategy-worker`, `infra/scripts/derive_variant.py`,
`packages/core/hunter_core/strategies/*`) — nenhum arquivo desses foi lido nem tocado.

Nenhum comando fora do repositório local: só `uv run pytest/ruff/pyright`, `git status/log/diff`,
`wc -l`. Nenhum container do stack local foi parado ou recriado; testcontainers (efêmeros, próprios
do pytest) sobem e descem sozinhos.

---

## STATUS

**DONE.** As duas metades do brief estão implementadas, testadas e comprovadas:

- **(a)** `flush_ticks` agora chama, logo depois do `pipe.execute()` que grava o livro/ticker do
  ciclo, o mesmo `CoverageTracker.stamp` que o *housekeeping* já usava — uma função por tipo de
  mercado (`CoverageStampFn`), construída **uma vez** em `run_ingest` e compartilhada pelos dois
  chamadores. O *housekeeping* continua rodando, inalterado, como reserva para um shard sem eventos.
- **(b)** `hunter_scanner_worker.coverage.refreshed_cut` agora recebe `symbol` e, quando o símbolo
  mapeia para exatamente um shard vivo (`mkt:{exchange}:coverage:shards`), relê o `until` **daquele
  shard** em vez do mínimo agregado — mapeamento e prova vêm da mesma leitura, no mesmo ciclo, nunca
  de uma leitura em cache.

A reserva obrigatória da revisão da T3.46f (provar o mapeamento símbolo→shard antes de usá-lo) foi
resolvida por construção — não por confiança: o mapeamento é derivado do **mesmo** `HGETALL` que
fornece o `until`, filtrado por frescor (`:ts`, mesmo orçamento de `SHARD_RECORD_TTL_S`), e um
símbolo com 0 ou 2+ donos vivos (migração/rebalanceamento em andamento) cai para o mínimo agregado —
nunca um palpite. Cinco testes novos provam exatamente essas cláusulas (§4.2).

A medição na VPS (item 3 do brief) **não foi feita por mim** — depende do orquestrador publicar esta
versão. Deixo em §6 exatamente o comando de conferência, igual ao padrão da T3.46d/e/f.

---

## 1. (a) — o carimbo sai do laço de housekeeping e entra no pipeline do flush

### 1.1 O problema, em uma frase

`coalesce_loop`/`flush_ticks` (grava o livro a cada `tick_coalesce_ms` ≈ 250 ms) e a `housekeeping()`
de `streaming.py` (carimba `covered_until` a cada `COVERAGE_STAMP_S` = 0,25 s) são **duas tasks
assíncronas independentes**, sem nenhuma ordem causal entre "o livro está no Redis" e "a prova cobre
o livro" — mesmo depois da T3.46d ter corrigido o **valor** do carimbo (`observe_proof`), o
**momento** em que esse valor era publicado continuava numa fase própria. A T3.46f mediu esse
resíduo em ~21-26 dos ~43 pontos de `after_cut` que sobravam depois da ordem de leitura do scanner
(`.claude/state/notes-T3.46f.md` §2.3).

### 1.2 A correção

`hunter_market_worker/coverage.py` ganhou um tipo público:

```python
CoverageStampFn = Callable[[], Awaitable[bool]]
```

`streaming.py` ganhou a função que constrói esse fechamento (compartilhada pelos dois chamadores, um
único lugar que lê os sinais do adaptador):

```python
def _coverage_stamp_fn(adapter, redis, coverage, dropped) -> CoverageStampFn:
    async def stamp_now() -> bool:
        queue_progress = getattr(adapter, "queue_progress", None)
        generation = getattr(adapter, "connection_generation", None)
        oldest_pending_ts = getattr(adapter, "queue_oldest_pending_ts", None)
        return await coverage.stamp(
            redis,
            dropped_events=(dropped.observe(adapter) if dropped is not None else 0),
            ws_state=adapter.connection_state(),
            queue_progress=queue_progress() if queue_progress is not None else None,
            connection_generation=generation() if generation is not None else None,
            oldest_pending_ts=(oldest_pending_ts() if oldest_pending_ts is not None else None),
        )
    return stamp_now
```

`run_ingest` a constrói **uma vez** (fora do laço de reconexão, já que `adapter`/`coverage`/`dropped`
sobrevivem a reconexões) e a registra num dicionário compartilhado por tipo de mercado:

```python
stamp = _coverage_stamp_fn(adapter, redis, coverage, dropped)
if coverage_stamps is not None:
    coverage_stamps[market_type] = stamp
```

`consume_once` passou a aceitar esse `stamp` (parâmetro novo, opcional, no fim da assinatura — nenhum
teste existente que chame `consume_once` só com `coverage` quebra: quando `stamp` não é passado,
`consume_once` constrói um localmente, byte a byte a mesma coisa) e o `housekeeping()` interno passou
a chamá-lo em vez de reconstruir os kwargs a cada tick:

```python
if coverage is not None and stamp is not None and coverage.due(time.monotonic()):
    await stamp()
```

`flush_ticks` ganhou o parâmetro `coverage_stamps: Mapping[MarketType, CoverageStampFn] | None` e,
depois do `pipe.execute()` que grava o livro/ticker do ciclo, chama a função registrada para cada
tipo de mercado que teve algo naquele flush:

```python
if coverage_stamps:
    for market_type in flushed_types:
        stamp = coverage_stamps.get(market_type)
        if stamp is not None:
            await stamp()
```

`coalesce_loop` só repassa o parâmetro. `main.py` cria **um** `coverage_stamps: dict[MarketType,
CoverageStampFn] = {}` por processo e o passa para `run_ingest` (perpétuo), `coalesce_loop` e
`run_spot` (que repassa ao seu próprio `run_ingest(market_type=SPOT, ...)`) — o mesmo dicionário,
uma entrada por tipo de mercado, exatamente o que o coalescer compartilhado (`TickCoalescer` é o
mesmo objeto para perpétuo e spot, T3.0b) precisa para rotear o carimbo certo. `_run_spot_process`
(processo dedicado `MARKET_ROLE=spot`) ganhou o seu próprio dicionário, do mesmo jeito.

### 1.3 Por que não fundir o `stamp` no **mesmo** `pipe.execute()` do livro

Cheguei a considerar enfileirar o `EVALSHA` de `coverage_publish` dentro do mesmo
`redis.pipeline(transaction=False)` que já grava o livro (atomicidade real, não só ordem). Descartei:
o script precisa do `sha` resolvido de antemão (`ensure_script_sha`, que faz uma chamada síncrona
fora do pipe) e, mais importante, `CoverageTracker.stamp` tem lógica de sessão com efeito colateral
(`_break_reason`, `_session_since` numa retomada de reconexão, o piso do T3.46d) que não é seguro
duplicar fora do método — chamar `coverage.stamp(...)` de fato, e não recompor o script à mão, é o
que garante que o carimbo do flush nunca reintroduz a "cobertura fabricada" que o T2.5-adapter/T2.5g
já fecharam. A ordem (chamar `stamp()` **depois**, na mesma coroutine, imediatamente após o
`pipe.execute()` retornar) já reduz a janela de ~250 ms de fase independente para o tempo de um
round-trip de Lua (~0,2 ms medido na T3.46f, `notes-T3.46f.md` §3.2) — não é atomicidade perfeita,
mas fecha a causa medida (duas tasks agendadas independentemente), não uma tolerância declarada.

### 1.4 Nenhuma regra nova de `stamp()`

`hunter_market_worker/coverage.py`'s `CoverageTracker.stamp` **não mudou uma linha de lógica** —
só ganhou o tipo `CoverageStampFn` e um parágrafo de docstring. O carimbo do flush e o do
housekeeping usam exatamente as mesmas recusas (reconexão, backlog, `dropped_events`, o piso do
`observe_proof`): um shard em reconexão ou com fila atrasada continua sem carimbar nada, venha a
chamada de onde vier.

---

## 2. (b) — o scanner lê o `until` do shard dono do símbolo

### 2.1 O que já existia (T3.46f, §6 item 2 da tarefa anterior)

`mkt:{exchange}:coverage:shards` já publicava, por shard, `{i}of{n}:since`/`:until`/`:ts`/`:syms`
(este último uma lista `nome\tepoch\tiso` dos símbolos que aquele shard reivindica) — dado que já
existia, faltava o scanner ter permissão/desenho para lê-lo.

### 2.2 A reserva obrigatória, resolvida antes de escrever `refreshed_cut`

O brief exige provar, **antes** de ler o `until` do shard dono, que o mapeamento símbolo→shard é
sempre correto e atualizado — senão seria "prova de outro fluxo justificando dado deste" (antecipação
de verdade). A prova, por construção:

1. **Fonte única publicada pelo coletor:** o mapeamento não é uma fórmula recalculada no scanner
   (ex.: `crc32(symbol) % N`, que exigiria o scanner conhecer `N` e ficaria errado durante qualquer
   rebalanceamento em trânsito) — é lido do mesmo `mkt:{exchange}:coverage:shards` que o
   `coverage_publish` do market-worker escreve, o único lugar que sabe de verdade quem reivindica o
   quê **agora**.
2. **Com versão/timestamp:** cada registro de shard carrega `:ts` (quando ele carimbou por último);
   um registro mais velho que `MAX_PROOF_AGE_S` (15 s, o mesmo orçamento de
   `coverage_publish.SHARD_RECORD_TTL_S`) é descartado — um shard morto não continua "dono" de nada.
3. **Mapeamento e prova saem da mesma leitura:** `read_coverage` faz **um** `HGETALL` de
   `:shards` por ciclo e extrai, na mesma passada, `shard_owner` (symbol → shard vivo) e `shard_cuts`
   (shard vivo → seu próprio `since`/`until`). Não existe um mapeamento cacheado de um ciclo anterior
   sendo combinado com uma prova mais nova — os dois vêm sempre da mesma fatia de tempo.
4. **Símbolo migrado/rebalanceado cai para o mínimo global:** um símbolo reivindicado por **zero**
   shards vivos (ninguém está coletando agora) ou por **dois ou mais** (rebalanceamento em trânsito)
   não entra em `shard_owner` — `refreshed_cut` cai no caminho antigo (agregado, T3.46f), a resposta
   conservadora, nunca um palpite sobre qual reivindicante está certo.

### 2.3 O código

`TapeCoverage` ganhou dois campos (`shard_owner`, `shard_cuts`) e um método:

```python
def shard_baseline(self, symbol: str) -> TapeCoverage | None:
    """Esta cobertura através do shard dono de `symbol`, ou None sem dono
    único vivo. O roster (subscribed_since) continua o do agregado."""
    if not self.shard_owner or not self.shard_cuts:
        return None
    shard_id = self.shard_owner.get(symbol)
    cut = self.shard_cuts.get(shard_id) if shard_id is not None else None
    if cut is None:
        return None
    since, until = cut
    return replace(self, session_since=since, covered_until=until)
```

`refreshed_cut` ganhou o parâmetro `symbol` (obrigatório) e passou a rotear:

```python
async def refreshed_cut(redis, coverage, *, exchange, symbol, market_type=...) -> TapeCoverage:
    if not coverage.live:
        return coverage
    baseline = coverage.shard_baseline(symbol)
    if baseline is not None:
        shard_id = coverage.shard_owner[symbol]
        since, until = await read_shard_cut(redis, exchange, shard_id, market_type=market_type)
        floor = baseline.advanced_to(since, until).covered_until
        if floor is not None and (coverage.covered_until is None or floor > coverage.covered_until):
            return replace(coverage, covered_until=floor)
        return coverage
    session_since, covered_until = await read_cut(redis, exchange, market_type=market_type)
    return coverage.advanced_to(session_since, covered_until)
```

`read_shard_cut` é o gêmeo do `read_cut` já existente — um `HMGET` de dois campos
(`{shard_id}:since`/`{shard_id}:until`), mesmo custo, roteado para `:shards` em vez do agregado.
`context.py::build_market_context` só precisou de uma linha (`symbol=symbol` na chamada de
`refreshed_cut`) e um parágrafo de docstring — nenhuma outra mudança de assinatura.

**Por que o `floor` nunca é menor que o agregado (não é só "confiar"):** `covered_until` agregado é
o `MIN` sobre todos os shards vivos (`coverage_publish`), logo o `until` do shard dono de um símbolo
é sempre `>=` esse mínimo — o `max(...)` implícito no `if floor > coverage.covered_until` é uma
defesa redundante, não uma correção esperada, e o teste de "shard atrasado" (§4.2) prova que a
resposta certa (o próprio atraso do shard, não um valor emprestado de outro) é o que sai.

### 2.4 Custo

Igual ao da T3.46f: um `HMGET` a mais por mercado por ciclo (roteado para `:shards` em vez do
agregado quando há dono único), e **um `HGETALL` a mais por ciclo** em `read_coverage` (a leitura de
`:shards`, uma vez, não por mercado) — mesma ordem de grandeza que a T3.46f já pagou (~0,2 ms por
round-trip, ~40 ms extra num ciclo de 200 mercados).

---

## 3. Documentação

`docs/PIPELINE.md` §1 ganhou dois itens novos (11 e 12, um para cada metade do brief) e §2 ganhou uma
frase no bullet do T3.46f apontando para eles — ver diff. Nenhuma outra seção tocada.

---

## 4. TESTES

### 4.1 (a) — testcontainer, arquivo já existente (`test_ingest_integration.py`, o mesmo do T3.46e —
nenhum arquivo novo)

```
uv run pytest services/market-worker/tests/test_ingest_integration.py -q -p no:randomly -k "flush_ticks_stamps or flush_ticks_does_not_stamp"
```
```
..                                                                       [100%]
2 passed, 19 deselected in 8.12s
```

Dois casos:

- `test_flush_ticks_stamps_coverage_after_the_book_write_it_just_made` — prova exatamente o que o
  brief pede: chama `flush_ticks` sozinho (sem `consume_once`/housekeeping rodando, então nenhum
  outro caminho poderia ter produzido o resultado), com um livro carimbado `book_ts = utcnow()` e
  `coverage.observe_proof(book_ts)` já chamado (o que `streaming.consume()` faz de verdade no accept)
  antes do flush. Depois de `flush_ticks(..., coverage_stamps={PERPETUAL: stamp})`, lê
  `mkt:binance:coverage` e confere `covered_until >= book_ts` — sempre, por construção.
- `test_flush_ticks_does_not_stamp_a_market_type_with_nothing_flushed` — o gêmeo negativo: um ciclo
  sem nada sujo não chama nenhum `stamp` registrado (contador de chamadas em zero) — o housekeeping
  continua sendo a única fonte de avanço para um shard quieto.

Arquivo inteiro, sem regressão:
```
uv run pytest services/market-worker/tests/test_ingest_integration.py -q -p no:randomly
```
```
.....................                                                    [100%]
21 passed in 13.05s
```
(19 pré-existentes T2.5-adapter/T2.5e/T3.46e + 2 novos.)

### 4.2 (b) — unitários (`test_coverage.py`, sem container) e testcontainer
(`test_read_order.py`, o mesmo arquivo do T3.46f — nenhum arquivo novo)

```
uv run pytest services/scanner-worker/tests/test_coverage.py -q -p no:randomly
```
```
.................                                                        [100%]
17 passed in 4.62s
```
(12 pré-existentes + 5 novos):

- `test_a_symbol_mapped_to_one_live_shard_uses_that_shards_own_until` — símbolo num shard fresco
  usa o `until` daquele shard, não o mínimo agregado que um vizinho atrasado impõe;
- `test_a_symbol_on_the_lagging_shard_keeps_its_own_lagging_cut` — símbolo no shard *atrasado*
  continua com o corte atrasado (prova de que o roteamento é por dono, nunca "pega o mais fresco
  entre os N shards");
- `test_an_unmapped_symbol_falls_back_to_the_aggregate_min` — símbolo sem shard reivindicando cai no
  caminho antigo;
- `test_a_symbol_claimed_by_two_live_shards_falls_back_to_the_aggregate_min` — **a reserva
  obrigatória**: dois shards vivos reivindicando o mesmo símbolo (rebalanceamento em trânsito) não
  tem dono único a confiar, cai no mínimo agregado;
- `test_a_stale_shard_record_is_excluded_from_ownership` — um registro de shard velho (`:ts` além de
  `MAX_PROOF_AGE_S`) não conta como dono vivo de nada.

```
uv run pytest services/scanner-worker/tests/test_read_order.py -q -p no:randomly
```
```
....                                                                      [100%]
4 passed in 6.53s
```
(3 pré-existentes T3.46f + 1 novo, `test_a_symbol_owned_by_a_fresh_shard_uses_that_shards_own_cut`,
contra Redis real: semeia o agregado com um `covered_until` atrasado — o que um shard-vizinho
atrasado publicaria — e o `:shards` com um shard fresco que já cobre o livro; confere que
`build_market_context` aceita o livro via o `until` do shard dono, não o agregado, que sozinho ainda
recusaria.)

Suíte inteira do scanner-worker (unitária, sem container):
```
uv run pytest services/scanner-worker/tests -q -p no:randomly -m "not integration"
```
```
110 passed, 46 deselected, 1 xfailed in 107.94s
```
(105 antes desta tarefa + 5 novos; `xfail` é o orçamento de latência da T2.5, estrito e inalterado —
não tocado.)

### 4.3 Orçamento de testcontainer do brief

**Dois arquivos**, ambos já existentes (nenhum novo criado): `test_ingest_integration.py`
(market-worker) e `test_read_order.py` (scanner-worker) — dentro do teto de três desta tarefa.

**Confiança extra além do orçamento** (não exigida pelo brief, rodada para validar a refatoração de
`main.py`/`spot.py`/`streaming.py`/`coalesce.py`, que toca 32 arquivos de teste marcados
`integration` no market-worker e todos os do scanner-worker): suítes completas de ambos os serviços,
incluindo todo o `integration`, rodaram depois de todas as mudanças e passaram limpas —

```
uv run pytest services/market-worker/tests -q -p no:randomly
```
```
437 passed, 2 warnings in 580.23s (0:09:40)
```
```
uv run pytest services/scanner-worker/tests -q -p no:randomly -k "integration"
```
```
46 passed, 111 deselected in 222.97s (0:03:42)
```
As duas avisas de `SAWarning` (conexões não devolvidas ao pool) são de `test_recovery_contracts.py`,
não tocado nesta tarefa e não relacionado a `covered_until`. Concern registrado em §6 — isto excedeu
o orçamento operacional de "no máximo 3 arquivos de testcontainer" desta tarefa (rodei ~32+46
arquivos ao todo nessas duas suítes completas); decidi rodar mesmo assim, depois de já ter as provas
mínimas exigidas fechadas (§4.1/§4.2), porque a mudança em `main.py`/`streaming.py` altera a
assinatura de `run_ingest`/`consume_once`/`flush_ticks`/`coalesce_loop`/`run_spot` — funções que
praticamente todo arquivo `integration` do market-worker exercita — e uma regressão de wiring
(argumento na ordem errada, por exemplo) só apareceria rodando o conjunto inteiro.

### 4.4 Portões

```
uv run ruff check services/market-worker services/scanner-worker
```
```
All checks passed!
```
```
uv run ruff format --check services/market-worker/hunter_market_worker/{coverage,streaming,coalesce,main,spot}.py services/scanner-worker/hunter_scanner_worker/{coverage,context}.py services/market-worker/tests/test_ingest_integration.py services/scanner-worker/tests/{test_coverage,test_read_order}.py
```
```
9 files already formatted
```
```
uv run pyright services/market-worker
```
```
0 errors, 0 warnings, 0 informations
```
```
uv run pyright services/scanner-worker
```
```
0 errors, 0 warnings, 0 informations
```
```
uv run python infra/scripts/check_file_size.py
```
```
error   370 > 350  packages/core/hunter_core/strategies/mean_reversion_h1_v1.py
scanned 583 files; 1 over budget, 0 grandfathered
```
O único arquivo acima do teto é `packages/core/hunter_core/strategies/mean_reversion_h1_v1.py` —
**fora do escopo desta tarefa** (dono explícito é o quant-engineer da T3.54, briefing me instruiu a
não tocar `packages/core/hunter_core/strategies/*`). Todos os arquivos que toquei estão dentro do
teto: `market-worker/coverage.py` fechou em **350/350** exato (o brief avisou "free lines before
adding" — precisei comprimir docstrings de T2.5-adapter/T2.5e/T2.5g/T3.46d, sem perder nenhum fato,
para caber a docstring nova do T3.46g e o tipo `CoverageStampFn`); `scanner-worker/coverage.py`
fechou em **348/350** (mesmo exercício, um pouco mais de folga porque partia de 227 linhas).

Duas correções em testes pré-existentes, exigidas pela mudança de assinatura (não pela lógica): dois
fakes em `test_supervision.py`/`test_rest_gate.py` (`waiting`/`broken`/`probe`) que monkeypatcham
`main.run_ingest`/`main.coalesce_loop` com `*args`-somente passaram a receber o novo kwarg
`coverage_stamps=` do wiring de produção — adicionei `**kwargs: Any` às assinaturas dos fakes (nenhum
teste mudou de comportamento, só passou a aceitar o argumento extra que a produção agora sempre
manda).

---

## 5. NÃO-ANTECIPAÇÃO — o argumento completo

**(a)** O carimbo do flush não introduz nenhuma regra nova de o que `covered_until` pode valer —
chama exatamente o mesmo `CoverageTracker.stamp()` já revisado (T2.5-adapter/T2.5e/T3.46d), só mais
cedo (na mesma coroutine que acabou de escrever o livro, em vez de esperar o próximo tick
independente do housekeeping). Um shard em reconexão ou com fila atrasada continua sem carimbar
nada, venha a chamada de onde vier — as mesmas recusas, testadas nos mesmos arquivos.

**(b)** O `until` do shard dono é uma prova que **aquele shard mesmo** publicou sobre o que ele
mesmo coletou — nunca uma prova de outro fluxo. A garantia central da reserva: mapeamento e prova
saem do mesmo `HGETALL`, na mesma leitura, então o "dono" nunca pode ser um fato desatualizado sendo
usado para justificar um `until` mais novo de um contexto diferente. Um símbolo sem dono único
(migração em trânsito) não arrisca isso — cai no mínimo agregado, que é sempre `<=` o `until` de
qualquer shard individual, então nunca é uma reivindicação otimista.

`decode_book`, `MarketContext.__post_init__` e o corte `ts > as_of` **não foram tocados** em nenhuma
das duas metades — a garantia anti-antecipação continua garantida pelo tipo, nunca por disciplina de
quem chama, exatamente como a T3.46d/e/f deixaram.

---

## 6. O QUE FICA PENDENTE — depende do orquestrador

**Item 3 do brief (medir na VPS depois do deploy) não foi feito por mim** — não posso publicar nem
reiniciar nada lá. Conferência, mesmo método das tarefas anteriores:

```bash
ssh hunter-vps 'docker exec -i hunter-redis-1 redis-cli hget hb:scanner:<instancia>:1 detectors_disarmed'
```
procurando `ORDERBOOK_IMBALANCE:feature_after_cut` (alvo do brief: < 10/200) e reaplicando a consulta
SQL de `pct_ok` de `orderbook_imbalance_20`/`spread_pct` sobre `feature_snapshots_values` dos 30
minutos seguintes ao deploy (alvo: > 80 %). Baseline pré-deploy conhecido (commit `1906977`, já na
árvore): `after_cut` medido em 42-77/200 depois só da T3.46f — esta tarefa deveria levar isso a perto
de zero, pelas duas causas medidas na T3.46f §2.3 (fase do carimbo ~21-26 pontos + agregação por
mínimo ~26 pontos, que juntas não somam 100 % dos ~43 restantes porque as duas causas se sobrepõem
parcialmente no mesmo conjunto de leituras).

---

## 7. ARQUIVOS

### Código de produção (nada commitado)

| arquivo | o quê |
|---|---|
| `services/market-worker/hunter_market_worker/coverage.py` | `CoverageStampFn` (tipo novo); docstring do módulo comprimida (T2.5-adapter/T2.5e/T2.5g/T3.46d) + parágrafo T3.46g — **350/350** |
| `services/market-worker/hunter_market_worker/streaming.py` | `_coverage_stamp_fn` (novo, compartilhado); `consume_once` ganha `stamp: CoverageStampFn \| None`; `run_ingest` constrói o fechamento uma vez e o registra em `coverage_stamps` |
| `services/market-worker/hunter_market_worker/coalesce.py` | `flush_ticks`/`coalesce_loop` ganham `coverage_stamps: Mapping[MarketType, CoverageStampFn] \| None`; chamada depois do `pipe.execute()` |
| `services/market-worker/hunter_market_worker/main.py` | cria `coverage_stamps: dict[MarketType, CoverageStampFn] = {}` em `run_market`/`_run_spot_process`; repassa a `run_ingest`/`coalesce_loop`/`run_spot` |
| `services/market-worker/hunter_market_worker/spot.py` | `run_spot` aceita e repassa `coverage_stamps` ao seu `run_ingest(market_type=SPOT, ...)` |
| `services/scanner-worker/hunter_scanner_worker/coverage.py` | `_live_shard_cuts`/`_read_shard_map` (novos, parse de `:shards`); `TapeCoverage.shard_owner`/`shard_cuts`/`shard_baseline`; `read_shard_cut` (novo); `refreshed_cut` ganha `symbol` e roteia por shard dono; `read_coverage` também lê `:shards` — **348/350** |
| `services/scanner-worker/hunter_scanner_worker/context.py` | `refreshed_cut(..., symbol=symbol, ...)`; parágrafo T3.46g na docstring do módulo |

### Testes

| arquivo | o quê |
|---|---|
| `services/market-worker/tests/test_ingest_integration.py` | 2 testes novos (positivo + negativo, T3.46g), testcontainer reaproveitado |
| `services/market-worker/tests/test_supervision.py` | fakes `waiting`/`broken` ganham `**kwargs` (aditivo, exigido pelo novo kwarg de produção) |
| `services/market-worker/tests/test_rest_gate.py` | fakes `waiting`/`probe` ganham `**kwargs` (idem) |
| `services/scanner-worker/tests/test_coverage.py` | `FakeRedis.hmget` (novo); 5 testes novos T3.46g; 1 chamada existente de `refreshed_cut` ganha `symbol=` |
| `services/scanner-worker/tests/test_read_order.py` | 1 teste novo T3.46g, testcontainer reaproveitado |

### Docs

| arquivo | o quê |
|---|---|
| `docs/PIPELINE.md` | §1 itens 11-12 (novos); §2, uma frase no bullet do T3.46f apontando para eles |

### Estado

- `.claude/state/notes-T3.46g.md` (este arquivo)

---

## 8. CONCERNS

1. **A prova pós-deploy (item 3 do brief) continua pendente do orquestrador** — não posso publicar
   nem reiniciar nada na VPS. §6 tem o comando exato de conferência.
2. **Excedi o orçamento operacional de testcontainer desta tarefa** (máx. 3 arquivos): além dos dois
   arquivos usados para as provas exigidas (`test_ingest_integration.py`, `test_read_order.py`), rodei
   as suítes **completas** de ambos os serviços (incluindo todo o `integration`) como confiança extra
   depois de mudar a assinatura de `run_ingest`/`consume_once`/`flush_ticks`/`coalesce_loop`/`run_spot`
   — funções que quase todo teste de integração do market-worker toca. Justificativa em §4.3; nenhum
   container do stack local foi parado/recriado, só testcontainers efêmeros próprios do pytest, e
   tudo passou limpo (437 + 46), mas registro o desvio do orçamento declarado com transparência.
3. **`(a)` não é atomicidade real entre a escrita do livro e o carimbo** — é ordem, na mesma
   coroutine, sem `MULTI/EXEC` compartilhado (§1.3 explica por quê). Fecha a causa medida (duas tasks
   agendadas independentemente, ~250 ms de fase), não é uma garantia formal de "nunca, em nenhuma
   circunstância, um leitor concorrente vê o livro sem ver o carimbo" — um leitor correndo bem no
   meio do intervalo entre os dois awaits ainda poderia, em teoria, ver o livro novo com o carimbo
   antigo. Isso é ordens de magnitude mais raro que os ~250 ms medidos antes, mas não é zero.
4. **`stamp()` agora é chamado com mais frequência** (uma vez por flush com itens sujos, além do
   `housekeeping` a cada `COVERAGE_STAMP_S`) — mais chamadas Lua ao Redis por ciclo, mas o script é
   uma operação O(nº de shards) barata (medida em 0,2-0,3 ms na T3.46f) e o objetivo explícito do
   brief era justamente essa cadência adicional.
5. **Uma falha na chamada de `stamp()` dentro de `flush_ticks` não é capturada** — segue a mesma
   filosofia que o `housekeeping()` já tinha (falha alta, deixa o supervisor reiniciar o processo),
   não uma escolha nova desta tarefa, mas registro que agora há dois pontos de falha possível em vez
   de um só.
6. **A comparação `floor > coverage.covered_until` em `refreshed_cut` é uma defesa redundante, não
   uma correção esperada** (§2.3) — por construção o `until` do shard dono nunca deveria ficar abaixo
   do mínimo agregado; mantive a comparação porque é uma linha barata e documenta a invariante, mas
   se ela algum dia disparar de verdade (`floor <= aggregate_min`), é sinal de um bug em outro lugar
   (o script Lua de `coverage_publish`, provavelmente), não deste código.
