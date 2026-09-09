# T3.46d — o livro "chega do futuro": a corrida de carimbo do `covered_until`

**Owner:** exchange-integration-specialist · **Data:** 2026-09-08/09 (Brasília) · **Base:** `main` @ HEAD ·
**Nada foi commitado.** Árvore compartilhada: outros agentes têm mudanças em voo nela (não tocadas).

Leitura da VPS: **22:21:53 → 22:25:32 de Brasília (01:21:53 → 01:25:32 UTC do dia 09)**, só `redis-cli`
(`hget`/`mget`/`--no-raw`) em primeiro plano, `docker exec` sem `-d`, nenhum container parado,
recriado ou alterado. Nenhuma escrita.

---

## STATUS

**DONE.** A corrida foi medida com número (13 427 leituras pareadas, 5 mercados, ~220 s), a causa
raiz identificada (não é o livro, é o carimbo de `covered_until` correndo descoordenado da escrita
do livro), e o conserto fecha a corrida por construção — não por tolerância. Testes novos provam a
regra antes/depois no nível do `CoverageTracker`, sem tocar `hunter_indicators` (o corte
`ts > as_of` de `decode_book` continua exatamente o mesmo). A prova final do item 4 do brief (a
razão `after_cut` cair de 97,7 % para < 5 % **depois do deploy**) fica pendente do orquestrador —
não posso publicar nem reiniciar nada na VPS — mas deixo aqui exatamente o comando para conferir.

---

## 1. MEDIÇÃO (item 1 do brief) — a distribuição real, não a amostra de 8 leituras da T3.46b

### 1.1 Método

A T3.46b tinha 8 leituras pareadas (`.claude/state/notes-T3.46b.md` §1.3). Para ter uma distribuição
de verdade, medi `book.ts − covered_until` em 5 mercados (`BTCUSDT`, `ETHUSDT`, `LTCUSDT`,
`HBARUSDT`, `ATOMUSDT`) por ~220 s, um ciclo a cada `docker exec` (sem `sleep` artificial — o próprio
round-trip do SSH pauta a cadência):

```bash
ssh hunter-vps '
END=$((SECONDS+220))
i=0
while [ $SECONDS -lt $END ]; do
  i=$((i+1))
  echo "===CYCLE $i $(date -u +%Y-%m-%dT%H:%M:%S.%3N)==="
  docker exec -i hunter-redis-1 sh -c "redis-cli hget mkt:binance:coverage covered_until; \
    redis-cli --no-raw mget mkt:binance:BTCUSDT:book mkt:binance:ETHUSDT:book \
    mkt:binance:LTCUSDT:book mkt:binance:HBARUSDT:book mkt:binance:ATOMUSDT:book"
done
echo "TOTAL_CYCLES $i"
'
```

```
TOTAL_CYCLES 2692
```

`ts` foi extraído do msgpack cru com um regex sobre a saída `--no-raw` (escapada, texto puro — nunca
um binário na tela) e os deltas calculados localmente em `awk`, sem tocar a VPS de novo. **2685-2692
ciclos válidos por mercado, 13 427 pares no total** — acima do piso de "≥ 1000 ciclos" do brief.

### 1.2 Resultado — `book.ts − covered_until`, em ms (positivo = livro depois do corte = `after_cut`)

```
GLOBAL   n=13427 p50=339.3ms p90=762.3ms p99=1471.5ms min=-943.5ms max=2551.0ms after_cut%=89.4
BTCUSDT  n=2685  p50=367.2ms p90=774.7ms p99=1545.0ms min=-228.1ms max=2551.0ms after_cut%=93.7
ETHUSDT  n=2692  p50=384.4ms p90=793.8ms p99=1440.0ms min=-303.7ms max=2255.4ms after_cut%=95.1
LTCUSDT  n=2689  p50=292.7ms p90=714.7ms p99=1443.0ms min=-817.4ms max=2431.0ms after_cut%=86.2
HBARUSDT n=2675  p50=286.9ms p90=740.5ms p99=1498.8ms min=-602.8ms max=2354.0ms after_cut%=83.7
ATOMUSDT n=2686  p50=335.9ms p90=774.3ms p99=1471.5ms min=-943.5ms max=1999.0ms after_cut%=88.3
```

**De onde vem cada carimbo:** `book.ts` é o relógio da **exchange** (o campo `ts` do último `depth`
aceito, gravado em `_book_payload` — `hot_state.py:230`). `covered_until` é o relógio **local**
(`utcnow()`) menos a margem `COVERAGE_SAFETY_S=0,5 s`, lido no laço de *housekeeping* de
`streaming.py` (a cada ~250 ms, `_HOUSEKEEPING_INTERVAL_S=0,1 s`, gatilho `coverage.due()` a cada
`COVERAGE_STAMP_S=0,25 s`) — um laço **assíncrono e independente** do laço que grava o livro
(`coalesce_loop`/`flush_ticks`, também ~250 ms, mas outra task, outra fase).

**Sensibilidade a uma tolerância fixa** (o que uma correção do tipo "(b)" teria que absorver):

```
tolerance<=0ms   -> usable 10.6% (n=1426/13427)
tolerance<=300ms -> usable 45.1% (n=6053/13427)
tolerance<=500ms -> usable 71.8% (n=9641/13427)   <- o teto sugerido pelo brief
tolerance<=800ms -> usable 91.2% (n=12245/13427)
tolerance<=1000ms-> usable 95.9% (n=12880/13427)
tolerance<=1500ms-> usable 99.1% (n=13309/13427)
```

Uma tolerância declarada de **500 ms** (o teto que o próprio brief sugere) deixaria **28,2 %** ainda
`after_cut` — não fecha a meta do item 4 (`< 5 %`). Só uma tolerância de ~1000-1200 ms chegaria lá, e
essa magnitude deixa de ser "uma folga contra ruído de sub-segundo" e passa a ser uma antecipação de
mais de um segundo, declarada ou não. Isso decidiu a escolha da correção (§2).

---

## 2. O CONSERTO — opção (a) do brief: fechar a corrida, não tolerá-la

### 2.1 Por que não (b)

A opção (b) (tolerância declarada, ≤ 500 ms) foi descartada com número: §1.2 mostra que a cauda real
(p90 = 762 ms, p99 = 1 472 ms) é maior do que a suposição de +2..+400 ms que a amostra de 8 leituras
da T3.46b sugeria. Uma tolerância bastante grande para cobrir a cauda deixaria de ser "folga contra
ruído" — seria antecipação de mais de um segundo, e o próprio código do projeto trata isso como uma
linha que não se cruza: `MarketContext.__post_init__` (`packages/indicators/.../context.py`) **levanta
exceção** se `book.ts > as_of` chegar até ali — "a garantia anti-antecipação... garantida pelo tipo,
nunca por disciplina". Aceitar uma leitura ainda-no-futuro na entrada (`decode_book`) para depois
proibi-la na saída (`MarketContext`) exigiria também afrouxar essa invariante — dois lugares a
manter coerentes em vez de um.

### 2.2 A causa raiz não é o livro — são dois relógios descoordenados

`covered_until` sempre carimba `agora − 0,5 s`. Um livro de uma perpétua líquida chega a cada
~100-250 ms, então seu `ts` está quase sempre **mais fresco que 500 ms**. Não é um caso raro: é a
consequência aritmética inevitável de comparar "o relógio menos uma margem fixa" com "algo que é
quase sempre mais novo que essa margem". Sincronizar os dois laços (rodá-los na mesma cadência) não
resolveria sozinho — o problema é a margem em si, aplicada a um dado que quase nunca é velho o
bastante para respeitá-la.

### 2.3 A correção: `CoverageTracker.observe_proof`

Em vez de tolerar a leitura futura, o carimbo passa a **usar a prova que o próprio processo já tem**:
todo evento que `consume()` (`streaming.py`) já **aceitou** (passou pela ordenação/validação de
`handle_event`, `hunter_market_worker/ingest.py`) tem seu `ts` reportado a
`CoverageTracker.observe_proof`. `stamp()` eleva `covered_until` até esse valor — nunca além dele,
nunca além do próprio relógio do carimbo (`moment`), e **só quando todo sinal de rompimento já diz
`caught_up`** (`ws_state`, `connection_generation`, `queue_progress`/`queue_oldest_pending_ts`,
`dropped_events` — nenhum desses ganhou uma linha nova; o piso só se aplica depois deles, exatamente
como a margem antiga). Uma sessão que nunca chama `observe_proof` (um teste que chama `stamp`
direto, ou um adaptador futuro que não o alimente) fica **idêntica, byte a byte**, ao comportamento
anterior — é um piso aditivo, nunca uma substituição.

```python
def observe_proof(self, ts: datetime | None) -> None:
    """``ts`` de um evento já aceito nesta sessão (T3.46d)."""
    if ts is not None and (self._observed_proof is None or ts > self._observed_proof):
        self._observed_proof = ts
```

```python
if caught_up:
    margin_based = moment - timedelta(seconds=COVERAGE_SAFETY_S)
    proof = self._observed_proof
    if proof is not None and proof > margin_based:  # T3.46d floor
        margin_based = proof if proof < moment else moment
    self._last_safe_covered_until = margin_based
```

E o único ponto de fiação, em `streaming.py::consume()`, ao lado do código que já mantinha
`heartbeat_state.last_event_at`:

```python
if accepted and source_ts is not None:
    previous = heartbeat_state.last_event_at
    heartbeat_state.last_event_at = max(previous, source_ts) if previous else source_ts
    if coverage is not None:
        coverage.observe_proof(source_ts)
```

Isso vale para livro, ticker e fita igualmente — nenhum tratamento especial para "livro"; a correção
é geral porque a causa (dois relógios descoordenados) também é geral, e `spread_pct` (que também
depende de `decode_book`) se beneficia do mesmo jeito.

### 2.4 O argumento de não-antecipação (revisão do quant-engineer pedida no brief)

`source_bar_close` das estratégias é alinhado ao minuto (`docs/PIPELINE.md` §2, "Anti-look-ahead");
o livro é intra-minuto. `observe_proof` nunca admite um valor além do relógio de parede real
(`proof if proof < moment else moment`) e nunca um valor que este processo não tenha **já aceitado**
de fato — não é uma suposição sobre o que "deve" ter acontecido, é o carimbo do evento que
literalmente already está em memória, prestes a ser gravado no mesmo ciclo de coalescência que o
brief descreve. O livro que fica visível em qualquer `as_of = covered_until` é, por construção, um
livro que este processo **já escreveu** — porque já era velho o bastante para escrever (a guarda de
ordenação de `handle_event`/T2.5-adapter). Elevar o corte até ele não fabrica informação nova, só
para de descartar uma informação que já era segura. E como a folga é sempre < 1 barra de 1 minuto
(o pior caso medido, p99, é 1,47 s — 2,45 % de um minuto), não existe cenário em que essa elevação
faça uma estratégia enxergar dados da **barra de decisão seguinte**: o corte muda por
milissegundos dentro do mesmo minuto, nunca atravessa o fechamento de uma vela.

### 2.5 Por que não mexi em `packages/indicators`

`decode_book`, `MarketContext` e o corte `ts > as_of` continuam exatamente como estavam. A correção
inteira vive do lado que **produz** `covered_until` (o `market-worker`), nunca do lado que o
**consome** — coerente com "nada específico de exchange vaza do `hunter_exchanges`" e com o próprio
enunciado do brief ("`packages/indicators`... só se uma tolerância declarada for a escolha").

---

## 3. TESTES

### 3.1 A corrida reproduzida (novo, dentro do arquivo existente)

```bash
uv run pytest services/market-worker/tests/test_tape_coverage.py -q -p no:randomly
```
```
.................                                                        [100%]
17 passed in 6.94s
```

17 = 13 testes já existentes (nenhum alterado, nenhum quebrado) + 4 novos:

- `test_book_stamped_150ms_after_the_naive_cut_is_accepted_once_proven` — reproduz a corrida:
  sem `observe_proof`, `covered_until = now − 0,5s` fica **antes** de um livro carimbado 150 ms
  depois desse corte ingênuo (`decode_book` recusaria como `after_cut`); com `observe_proof(book_ts)`
  chamado como `consume()` chamaria, o próximo carimbo eleva `covered_until` **até** `book_ts` —
  aceito.
- `test_observed_proof_never_lifts_covered_until_while_disconnected` — uma prova observada antes de
  uma reconexão não pode fazer o intervalo congelado avançar.
- `test_observed_proof_resets_when_the_session_breaks` — uma prova de uma sessão morta não pode
  vazar para a sessão nova que a substitui (o teste usa uma prova **à frente** do próprio carimbo da
  sessão nova — se vazasse, o resultado publicado seria diferente do que uma sessão sem prova
  nenhuma produziria).
- `test_observed_proof_never_exceeds_this_stamps_own_clock` — uma prova "do futuro" (relógio
  dessincronizado, ou um chamador com bug) é limitada ao próprio relógio do carimbo, nunca publicada
  como está.

### 3.2 Testcontainer na trilha de cobertura (item 3 do brief — "um teste testcontainer no caminho de cobertura")

O próprio `test_tape_coverage.py` roda contra Redis real via testcontainer (`redis_client` →
`redis_container`, doc do arquivo: "a hand-written double would be testing a different writer than
production runs" — o script Lua de `coverage_publish` só é testado de verdade contra um Redis de
verdade). Isso conta como o arquivo de testcontainer nº 1 dos dois permitidos.

Regressão de sanidade no segundo arquivo permitido (sharding — a lógica mais próxima do que toquei):

```bash
uv run pytest services/market-worker/tests/test_tape_coverage_shards.py -q -p no:randomly
```
```
.........                                                                [100%]
9 passed in 6.93s
```

Nenhuma regressão. **Não rodei** `test_tape_coverage_backlog.py` (terceiro arquivo de testcontainer
que também usa `CoverageTracker.stamp`) — orçamento do brief é de dois arquivos. Risco residual:
baixo, porque nenhum teste ali chama `observe_proof`, e a mudança em `stamp()` é estritamente aditiva
(o piso só participa quando `proof is not None`, e `_observed_proof` começa e permanece `None` para
qualquer chamador que nunca invoque o método novo).

### 3.3 Suíte ampla, sem testcontainer (confiança extra, sem gastar orçamento)

```bash
uv run pytest services/market-worker/tests -q -p no:randomly -m "not integration"
```
```
........................................................................ [ 61%]
..............................................                           [100%]
118 passed, 315 deselected in 12.24s
```

`packages/indicators` não foi tocado (§2.5) — nada para rodar de novo lá; o comportamento de
`decode_book`/`MarketContext` é byte a byte o que já era.

### 3.4 Portões

```bash
uv run ruff check services/market-worker
```
```
All checks passed!
```

```bash
uv run ruff format --check services/market-worker/hunter_market_worker/coverage.py \
  services/market-worker/hunter_market_worker/streaming.py services/market-worker/tests/test_tape_coverage.py
```
```
3 files already formatted
```

```bash
uv run pyright services/market-worker
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

`coverage.py` chegou a **426** linhas com o docstring completo do T3.46d (o arquivo já estava em
**350/350**, no teto, antes desta tarefa) — comprimi o texto novo e apertei três blocos de docstring
pré-existentes (T2.5-adapter/T2.5e/T2.5g, sem perder nenhum fato, só a prolixidade) até fechar
exatamente em **350**. Nenhum outro arquivo do repositório está listado num baseline de
grandfathering (`infra/scripts/file_size_baseline.txt` não existe) — a única saída honesta era
caber no orçamento.

---

## 4. PROVA PENDENTE (item 4 do brief) — depende do deploy

**Não posso fechar isto sozinho.** A VPS continua rodando o binário anterior; nada foi publicado. A
conferência, depois que o orquestrador subir esta versão, é o mesmo método do §1.1 — rodar por
1 hora (ou reaproveitar a consulta agregada que a T3.46b já usa sobre `feature_snapshots`) e comparar:

```sql
-- infra/scripts/sql/research/2026-09-09-t346b-03-features-vivas.sql (consulta 2), reaplicada
-- depois do deploy, sobre a hora seguinte
select motivo, count(*) from feature_snapshots_values
where feature = 'orderbook_imbalance_20' and quality = 'unavailable'
group by motivo;
```

**Antes (medido, T3.46b):** `after_cut` em 11 717 de 12 002 leituras (97,7 %) numa hora.
**Antes (medido aqui, direto no Redis, §1.2):** 89,4 % das leituras pareadas em 5 mercados, ~220 s.
**Depois:** pendente do orquestrador. Meta do brief: `< 5 %`.

Se depois do deploy a razão não cair para menos de 5 %, o próximo passo é instrumentar
`CoverageTracker.stamp` em produção (um log por carimbo com `proof` vs `margin_based`) em vez de
repetir a mesma medição — o mesmo princípio da T3.46b (§1.5, "não repetir SQL").

---

## 5. ARQUIVOS

### Código (nada commitado)

| arquivo | o quê |
|---|---|
| `services/market-worker/hunter_market_worker/coverage.py` | `CoverageTracker.observe_proof` (novo), piso em `stamp()`, docstring do módulo com a seção T3.46d |
| `services/market-worker/hunter_market_worker/streaming.py` | `consume()` chama `coverage.observe_proof(source_ts)` ao lado do `heartbeat_state.last_event_at` já existente |
| `docs/PIPELINE.md` | §1 item 10 (novo, a correção completa), §2 (uma frase na bala "o corte é a prova de cobertura"), §3 (uma frase fechando o `feature_after_cut` da T3.46b) |

### Testes

- `services/market-worker/tests/test_tape_coverage.py` — 4 casos novos (§3.1), 13 existentes inalterados

### Medição bruta (scratchpad da sessão, não faz parte do repositório)

- `t346d-raw2.txt` (saída crua do `redis-cli`, 2692 ciclos), `t346d-deltas.txt` (13 427 pares
  calculados), ambos no diretório de scratch desta sessão — não commitados, não fazem parte do
  repositório do projeto.

---

## 6. CONCERNS

1. **A prova do item 4 (`after_cut` < 5 % pós-deploy) depende do orquestrador.** Não fiz — nem
   poderia, sob a regra de VPS somente leitura — nenhuma publicação. §4 documenta exatamente o
   comando de conferência.
2. **Um arquivo de testcontainer não foi rodado por orçamento** (`test_tape_coverage_backlog.py`,
   §3.2). Risco avaliado como baixo (mudança estritamente aditiva, nenhum teste ali chama o método
   novo), mas não é o mesmo que ter rodado.
3. **`coverage.py` estava exatamente no teto de 350 linhas antes desta tarefa.** Qualquer adição
   futura a este módulo vai precisar cortar em outro lugar primeiro — deixo isso registrado porque
   não é óbvio olhando só o resultado (350/350) que não havia folga nenhuma.
4. **O piso de `observe_proof` também beneficia `trade_velocity_1m`/`buy_pressure_5m`/
   `sell_pressure_5m` e o `deriv`, não só o livro** — são consumidores do mesmo `covered_until`. Isso
   é internamente consistente (a causa raiz é geral) mas é um efeito colateral que ninguém pediu
   explicitamente: essas features já estavam em ~98 % de disponibilidade, então o efeito prático
   deve ser pequeno (menos "quase-insuficiente" perto da borda), mas não medi separadamente.
5. **A medição do §1 é de ~220 s numa única janela (22:21:53-22:25:32 BRT de 08/09), não de 1 hora.** Está
   acima do piso de "≥ 1000 ciclos" do brief (13 427 pares), mas é uma janela mais curta que a hora
   que a T3.46b usou para o número de 97,7 %. As duas medições concordam em ordem de grandeza
   (industrial: ambas > 85 %), a diferença provável é o método (agregado do Postgres por minuto vs
   amostragem direta do Redis em alta frequência) e não um sinal de que o problema mudou de
   magnitude.

---

## T3.46e

**Owner:** exchange-integration-specialist · **Data:** 2026-09-08 (Brasília) · nit 1 da revisão da
T3.46d: nenhum teste até aqui exercitava o único ponto de fiação real
(`streaming.py::consume()` chamando `coverage.observe_proof(source_ts)`) — os 4 testes novos da
T3.46d chamam `tracker.observe_proof` direto, pulando `consume_once`/`handle_event` por completo.

**STATUS: DONE.**

### O que foi acrescentado

Dois testes de integração em `services/market-worker/tests/test_ingest_integration.py` (arquivo já
existente, já com `redis_client` via testcontainer e já com os dois testes T2.5-adapter no mesmo
padrão — nenhum arquivo novo de testcontainer):

1. `test_consume_once_wires_observe_proof_to_lift_covered_until_to_event_ts` — positivo. Sobe
   `consume_once` de verdade com `FakeAdapter` + `CoverageTracker`, empurra um `NormalizedOrderBook`
   real com `ts = utcnow()` (relógio da exchange) e `received_at` propositalmente atrasado 30 s
   (`model_copy`), e espera (polling, timeout 5 s) o `covered_until` publicado no Redis real chegar a
   **exatamente** `book.ts` — nunca a `received_at`. Prova o `ts` certo é o que atravessa
   `handle_event` → `observe_proof` → `stamp` → `coverage_publish`, não só a lógica isolada do
   `CoverageTracker` (que os 4 testes da T3.46d já cobriam).
2. `test_consume_once_observe_proof_does_not_lift_covered_until_during_backlog` — o gêmeo negativo.
   Mesma fiação, mas com `adapter.set_queue_progress(enqueued=5, delivered=3)` (backlog, 2 itens em
   trânsito) antes de empurrar um book com `ts` à frente da margem (`utcnow() + 200ms`). `observe_proof`
   roda do mesmo jeito (é chamado para todo evento aceito, independente da saúde da conexão), mas o
   piso do T3.46d só entra quando `stamp()` já diz `caught_up` — com backlog, `caught_up = False`, e o
   `covered_until` publicado permanece congelado no valor de antes do backlog, comprovadamente menor
   que o `book_ts` observado.

Não toquei `coverage.py` (permanece 350/350, nada mudou nele nesta tarefa) nem `streaming.py`
(o ponto de fiação já existente é exatamente o que os dois testes exercitam).

### Comandos e saída real

```
uv run pytest services/market-worker/tests/test_ingest_integration.py -q -p no:randomly -k "coverage or observe_proof"
```
```
..                                                                       [100%]
2 passed, 17 deselected in 10.92s
```

```
uv run pytest services/market-worker/tests/test_ingest_integration.py -q -p no:randomly
```
```
...................                                                      [100%]
19 passed in 11.69s
```
(17 pré-existentes + 2 novos — nenhuma regressão. Único arquivo de testcontainer tocado, rodado uma
vez após o ajuste de formatação e mais uma vez depois, para confirmar — ambas as vezes 19/19.)

```
uv run ruff check services/market-worker/tests/test_ingest_integration.py
```
```
All checks passed!
```

```
uv run ruff format --check services/market-worker/tests/test_ingest_integration.py
```
```
1 file already formatted
```
(precisou de um ajuste manual — `ruff format` quis quebrar a linha do `assert frozen[...] == healthy[...]  # comentário`; movi o comentário para a linha de cima e reformatei; reconferido depois.)

```
uv run pyright services/market-worker/tests/test_ingest_integration.py
```
```
0 errors, 0 warnings, 0 informations
```

```
uv run python infra/scripts/check_file_size.py
```
```
scanned 580 files; 0 over budget, 0 grandfathered
```

```
uv run pytest services/market-worker/tests -q -p no:randomly -m "not integration"
```
```
........................................................................ [ 61%]
..............................................                           [100%]
118 passed, 317 deselected in 6.63s
```

```
uv run ruff check services/market-worker
```
```
All checks passed!
```

### Arquivos

| arquivo | o quê |
|---|---|
| `services/market-worker/tests/test_ingest_integration.py` | 2 testes novos (positivo + negativo), 1 linha de import ajustada (`datetime` além de `timedelta`) — nada mais tocado |

Nada commitado. `coverage.py`/`streaming.py` do código de produção não foram tocados.

### Concerns

1. O teste positivo depende de o relógio de parede real não avançar mais de `COVERAGE_SAFETY_S`
   (0,5 s) entre o `push_event` e o próximo `stamp()` do housekeeping (a cada ~0,1-0,35 s na prática)
   — mesma suposição de timing que os testes T2.5-adapter já existentes no mesmo arquivo fazem (ex.:
   `test_internal_reconnect_holds_covered_until_back_without_ending_the_generator` já dorme 0,9 s/0,4 s
   fixos). Não é um teste novo de timing sensível, é o mesmo padrão já aceito no arquivo; o polling com
   timeout de 5 s (em vez de um sleep fixo) dá folga extra em vez de apostar num sleep exato.
2. Não criei um teste de "sessão quebrada" (reconexão) como segunda metade do par negativo — usei
   backlog porque é o cenário que o `FakeAdapter` já sabe simular sem exigir uma terceira via de
   estado (`set_queue_progress`, já usado no mesmo arquivo). Cobre a mesma cláusula do piso
   (`caught_up` precisa ser `True`), mas não é literalmente "sessão quebrada" — se o revisor quiser
   especificamente o caminho `ws_state="reconnecting"`, é um teste adicional de poucas linhas seguindo
   `test_internal_reconnect_holds_covered_until_back_without_ending_the_generator` como molde.

## §4 (medido pelo orquestrador, 2026-09-08 22:52–23:06 BRT) — prova pós-deploy NÃO atingida
Coletores em `2b7cef9`, scanner em `09b8fa6`. Heartbeat `detectors_disarmed`, ORDERBOOK_IMBALANCE, a cada minuto por 14 min: `feature_after_cut` = 178, 174, 184, 184, 198, 186, 184, 191, 185, 195, 186, 193, 179 (de 200); `baseline_absent`/`baselines_under_construction` = 1–5 / 1–22. Antes (coletores antigos): 134 de 134. Conclusão: o carimbo por prova está certo, mas o resíduo é a ordem de leitura do scanner (corte antes do livro; o livro anda entre as duas leituras) → T3.46f (`brief-T3.46f-scanner-read-order.md`).
