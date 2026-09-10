# T3.74b — o portão ganha um terceiro olho; o custo N×M ganha um cache por família

**Escopo:** item 1 (backend-specialist) — `consumer_lag` no portão `live_lane_degraded`, TDD,
unitário, sem banco. Item 2 (quant-engineer + backend-specialist, arquitetural) — desenho em
`docs/plans/T3.74b-CONTEXT-CACHE.md`, aprovado com a Astra antes de codar, depois implementado com
prova de equivalência e benchmark num testcontainer. Item 3 (`pg_stat_statements`, devops) — fora
do meu escopo (backend-specialist), não tocado. **Nenhuma escrita na VPS, nenhum reinício/recriação
de contêiner, nenhum parâmetro de versão viva tocado, nenhum commit.**

---

## 1. Item 1 — `consumer_lag`, o terceiro motivo do portão

### 1.1 O que foi pedido e o que o brief prescrevia, literalmente

`.claude/state/brief-T3.74b-consumer-lag-e-custo-por-barra.md` item 1 pede um terceiro motivo em
`live_lane_degraded` lendo `XINFO GROUPS` do stream `market.candles.closed`, grupo
`strategy-worker.shadow`, citando "o campo `lag` já existe no Redis (medido em T3.74: 69 agora) e é
exatamente o número que faltou". Implementei exatamente isso — não a paráfrase do despacho que me
lançou ("publicar um `decision_lag_s` p50/p95 nas timings do próprio consumidor"), porque o brief é
a fonte específica e detalhada para esta tarefa (nome de stream, nome de grupo, padrão de nome de
limiar já community usado em `REPLAY_*`) e a paráfrase do despacho, mais genérica, não tem a mesma
precisão. Registro a divergência aqui por transparência; ver §1.3 para o motivo de isso não ter
fechado o sintoma sozinho — o que confirma, na prática, por que o despacho pedia a medida em
segundos.

### 1.2 Implementação

- **Novo:** `services/strategy-worker/hunter_strategy_worker/replay/consumer_lag.py` —
  `group_lag(redis, *, stream=LIVE_CONSUMER_STREAM, group=LIVE_CONSUMER_GROUP) -> int | None`. Lê
  `XINFO GROUPS`, localiza a entrada do grupo comparando o campo `name` no tipo em que o Redis o
  enviou (bytes ou str, sem decodificar o nome de **outros** grupos — correção da revisão da Astra,
  §1.4), extrai `lag`. `None` cobre quatro casos tratados igual pelo chamador (fail-closed, nunca
  como zero): a chamada falhar, o grupo não existir, `lag` ausente, `lag: null` explícito (grupo
  cujo primeiro PEL foi cortado por `MAXLEN` antes de ler qualquer coisa).
- **`replay/budget.py`:** `ReplayBudget.consumer_lag_max: int = 100` (env `REPLAY_CONSUMER_LAG_MAX`,
  padrão dos outros `REPLAY_*`); `live_lane_degraded` chama `group_lag` depois do `outbox_lag_s` e
  devolve `consumer_lag:<n>` ou `consumer_lag_unreadable`. Extraí a lógica de parsing para o módulo
  novo porque `budget.py` estourou 350 linhas com a implementação inline (380); depois da extração:
  334 linhas.
- **Testes:** `test_replay_contract.py::TestConsumerLagGate` (11 casos: saudável, acima do limiar,
  exatamente no limiar, outro grupo no mesmo stream nunca confundido, grupo ausente, falha do
  `XINFO`, `lag` ausente, `lag: null` explícito, resposta totalmente textual — Astra apontou que o
  parser real do redis-py normaliza chaves para `str` mesmo sem `decode_responses`, então o fixture
  só-bytes não bastava —, e um nome de outro grupo com bytes inválidos em UTF-8 que não pode
  derrubar a checagem do nosso). `test_replay_drain_pause.py` ganhou
  `test_a_backlogged_consumer_group_never_pops_a_request` (o `_drain` real recusa quando o lag está
  alto, não só quando o heartbeat está ruim).

### 1.3 Medição ao vivo (VPS, somente leitura) — por que este motivo não fecha o sintoma

```
$ timeout 60 ssh hunter-vps "docker exec hunter-redis-1 redis-cli XINFO GROUPS market.candles.closed"
# 2026-09-10 05:51Z: strategy-worker.shadow -> pending=0 lag=0 (grupo saudável neste instante)
$ timeout 60 ssh hunter-vps "docker exec hunter-redis-1 redis-cli HGETALL hb:strategy:shadow"
# outbox_lag_s=0.0, evaluated_bars=2000, last_iteration fresco
```

Mas a mesma janela, medida por SQL (somente leitura, sem escrita):

```sql
-- últimos 30 min a partir de 05:5x UTC
select count(*), percentile_cont(0.5)..., percentile_cont(0.95)...
from agent_signals where emitted_at >= now() - interval '30 minutes'
  and supporting_features ? 'observation_ts';
-- 24 sinais | p50 = 97.8s | p95 = 184.8s | max = 185.0s
```

E, granular (últimos 10 min, mesma barra `bar_close = 05:45:00Z`):

| `emitted_at` | `bar_close` | atraso |
|---|---|---|
| 05:45:36.7 | 05:45:00 | 36.7 s |
| 05:45:39.7 | 05:45:00 | 39.7 s |
| 05:46:29.7 | 05:45:00 | 89.7 s |
| 05:48:04.0 a 05:48:05.0 (8 linhas) | 05:45:00 | 184.0–185.0 s |

**A mesma barra lógica (05:45:00Z) produziu sinais entre 36,7 s e 185,0 s de atraso, escalonados**
— não é um evento, é uma rampa dentro da própria barra. Uma amostragem de 40 leituras de `XINFO
GROUPS`/`XPENDING` por 5 s ao longo de ~3,5 min (janelas de 05:52–05:56Z, cobrindo o próximo
fechamento de 5 min) mostrou `lag=0`/`pending=0` quase o tempo todo, com um único blip de `lag=13`
durante o burst de 05:55Z. **Conclusão honesta**: `XINFO GROUPS`' `lag` mede o quanto o grupo ainda
não *leu* do stream — não quanto tempo um item lido está demorando para ser *processado e
persistido*. Se o `market-worker` publica os candles da mesma barra escalonados ao longo de ~2–3
min (hipótese, não causa estabelecida — ver ressalva da Astra abaixo), o `strategy-worker` lê cada
candle quase assim que ele chega (backlog baixo) e o atraso real está em quando o candle **chegou**
ao stream, não em quanto tempo ficou esperando ser lido. `consumer_lag` continua sendo um sinal real
e independente (um consumidor travado/morto certamente o levantaria), mas **não é** o
`decision_lag_s` que o despacho original pedia — essa lacuna permanece aberta.

**Ressalva da Astra (revisão do diff, `--dangerously-bypass-approvals-and-sandbox` não usado por
mim — chamada correta via `astra.sh ask`):** a atribuição a "publicação escalonada" é hipótese, não
causa estabelecida — `consume()` entrega lotes de até 10 (`hunter_core/events/consume.py`,
`batch: int = 10`) e o Redis marca como lidas as entregas do lote inteiro no momento da
`XREADGROUP`, antes de cada mensagem ser processada e confirmada individualmente — então trabalho
já entregue mas ainda não terminado (o próprio worker lento por versão, não por publicação atrasada)
também não apareceria neste `lag`. Documentado como hipótese em todo lugar que toquei
(`budget.py`, `Open Bugs.md`, aqui).

### 1.4 Segunda opinião da Astra (item 1)

Pedida via `infra/scripts/astra.sh ask t374b-consumer-lag ...` sobre o diff do item 1 antes de eu
seguir para o item 2. **APPROVE_WITH_NITS.** Achados aplicados:
- decodificar o `name` de um grupo **alheio** para compará-lo era desnecessário e podia lançar numa
  entrada malformada — corrigido para comparar sem decodificar (`consumer_lag.py::_find_lag`);
- `lag: null` explícito (distinto de campo ausente) precisava de teste próprio — adicionado;
- uma resposta totalmente textual do parser real do redis-py (que decodifica chaves mesmo sem
  `decode_responses`) não estava coberta pelo fixture só-bytes — adicionado;
- manteria `REPLAY_CONSUMER_LAG_MAX = 100` como **provisório** e retiraria a linguagem "≈ metade do
  universo" (a métrica conta eventos, não mercados distintos) — docstring reescrito, ver `budget.py`.
Íntegra: `.claude/state/astra-review-t374b-consumer-lag.md`.

---

## 2. Item 2 — cache de contexto por família

### 2.1 Desenho antes de codar

`docs/plans/T3.74b-CONTEXT-CACHE.md`, escrito antes de qualquer linha de produção, revisado pela
Astra (`infra/scripts/astra.sh ask t374b-context-cache-design ...`,
`.claude/state/astra-review-t374b-context-cache-design.md`) **antes** da aprovação. Dois must-fix
da Astra, ambos incorporados ao desenho e ao código antes de escrever o primeiro teste de
integração:

1. **Semântica de fotografia, não escondida.** O cache é um retrato do candle no instante em que é
   montado — a mesma propriedade que `WindowCache` já assume para o replay ("a snapshot ... a
   property, not a bug"). Sem o cache, um backfill que alcançasse um candle já fechado *entre* duas
   avaliações da mesma barra já podia fazer duas versões discordarem; o cache estreita essa janela
   (para a duração de um `handle_candle`), não a inventa. Documentado no módulo, no `PIPELINE.md` e
   aqui.
2. **Isolamento de falha no pré-carregamento.** Uma família cujo `load_window` falhe (timeout,
   conexão) não pode derrubar as outras famílias nem a barra inteira — `build_family_readers` isola
   por família (try/except por chave), e `load_family_readers` (a função que `consumer.py` chama)
   isola de novo por fora (sessão própria, nunca deixa uma exceção subir), preservando o mesmo
   contrato que já existe por versão em `handle_candle`.

### 2.2 O que foi implementado

- **Novo `hunter_strategy_worker/context_cache.py`** (160 linhas): `build_family_readers` (agrupa
  `versions` — a lista `due` já calculada por `handle_candle`, não o roster inteiro — por
  `strategy_key`, ignora grupos de 1, calcula `ceiling = max(context_minutes do grupo)`, chama
  `replay.candles.load_window` com `window_start == window_end == bar_close`, isolando falha por
  família) e `load_family_readers` (abre sua própria sessão, nunca deixa uma exceção escapar para
  `handle_candle`).
- **`consumer.py`:** `handle_candle` chama `load_family_readers` uma vez antes do laço de versões e
  passa `candles_reader=family_readers.get(version.strategy_key)` para cada `evaluate_slot` — a
  mesma injeção que o replay já usa desde T3.19b, nenhuma mudança em `decide.py`/`evaluate_slot`.
- **`context.py`:** só documentação — o docstring de `CandleReader` agora nomeia os dois eixos de
  reuso (replay entre barras, T3.19b; consumidor vivo entre versões da mesma barra, T3.74b) e
  corrige uma referência morta (`test_replay_candle_cache`, que não existe — o teste real é
  `test_replay_engine.py::TestTheCandleCache`).
- **`context_budget.py`: não tocado**, deliberadamente — o teto por família é `max()` de números
  que `ActiveVersion.context_minutes(config)` já sabe computar; agregar isso lá acoplaria um módulo
  puro (sem IO, sem noção de barra/família) a uma decisão de runtime do consumidor (§5 do desenho).

### 2.3 Prova de equivalência (testcontainer, `test_context_cache_engine.py::TestEquivalence`)

Uma família de 4 versões (`equiv_family`, mesma estratégia `volume_anomaly_v1`, duas janelas
distintas — `atr_bars=97` → 1560 min pelo piso, `atr_bars=103` → 1570 min, exercitando o `max()` do
teto de verdade) decide sobre uma série gravada e imutável (1600 min, pico de volume nos últimos 5)
através do `evaluate_slot` real duas vezes: uma com `candles_reader=None` (caminho de hoje), outra
com o leitor de `build_family_readers`. `Evaluation` é computada **antes** do lock do slot
(`decide.py`), então chamar `evaluate_slot` duas vezes para a mesma versão/mercado/barra nunca
corrompe a comparação — só a *persistência* da segunda chamada vira no-op (a barreira do slot já
andou), nunca a decisão devolvida. As 4 versões concordaram byte a byte (`state`, `reason`,
`decision`) entre as duas passadas.

### 2.4 Benchmark (mesmo testcontainer, mesma invocação — `TestBenchmark`)

11 versões (8 `bench_a` + 3 `bench_b`, a forma que a T3.74 mediu ao vivo) × 16 mercados, dois cortes
de barra diferentes sobre os mesmos mercados (nenhuma passada interfere no estado de slot da outra),
contando `load_candles` de verdade via `monkeypatch` em `context.py`/`replay/candles.py`:

Primeira execução (relógio real, sem `clock=` fixo — ver §2.5, a Astra pegou isso):

```
$ uv run pytest services/strategy-worker/tests/test_context_cache_engine.py -q -s
t374b_context_cache_benchmark  after_bars_per_s=1.5 after_elapsed_s=118.86 after_load_candles_calls=32
                                before_bars_per_s=1.3 before_elapsed_s=131.48 before_load_candles_calls=176
2 passed in 324.31s (0:05:24)
```

**Revalidada** depois da correção (relógio fixado em `bar_close + 2s`, determinístico independente
de quando o teste roda de verdade):

```
$ uv run pytest services/strategy-worker/tests/test_context_cache_engine.py -q -s
t374b_context_cache_benchmark  after_bars_per_s=1.5 after_elapsed_s=116.25 after_load_candles_calls=32
                                before_bars_per_s=1.4 before_elapsed_s=128.44 before_load_candles_calls=176
2 passed in 312.69s (0:05:12)
```

Os dois números concordam (131,5→118,9 e 128,4→116,3): a correção de relógio não estava mascarando
um resultado diferente, só tornando o teste determinístico para qualquer hora em que rode.
**176 → 32 chamadas a `load_candles`** — exatamente o desenhado (11×16 → 2 famílias×16), **asserted**
no teste. **128,4 s → 116,3 s (1,4 → 1,5 avaliações/s, ~9,5 %)** de tempo total — real, mas
reportado, não *asserted* (CI/timing não é contrato). **Ressalva da Astra (revisão final, MEDIUM,
aplicada):** eu tinha atribuído a diferença entre a redução de 5,5× em query e o ganho de só ~9,5%
de relógio a "o custo de `lock_slot`/`load_regime_asof`/`persist_decision`/`slots.advance` domina" —
a Astra apontou que isso é afirmativo sobre uma composição que o benchmark não decompôs (ele mede
tempo agregado e contagem de `load_candles`, não o tempo de cada função). Reescrito em todo lugar
(aqui, `Open Bugs.md`, `docs/plans/T3.74b-CONTEXT-CACHE.md`) como hipótese explícita, não conclusão.

### 2.5 Segunda opinião da Astra (implementação final) — REQUEST_CHANGES, aplicado

Pedida sobre o diff final dos dois itens juntos (`infra/scripts/astra.sh ask t374b-final-diff ...`),
íntegra em `.claude/state/astra-review-t374b-final-diff.md`. Vereditos e o que fiz com cada um:

- **HIGH, aplicado.** `test_context_cache_engine.py` não fixava `clock=` em nenhuma chamada de
  `evaluate_slot`, então `lag_s = now (relógio real) − bar_close` podia ultrapassar
  `eligibility_max_lag_s` (300 s) e fazer toda avaliação virar `unavailable: lag` **antes** de tocar
  em um candle — o que teria comparado duas recusas idênticas em vez de duas decisões reais, sem
  aviso, dependendo só de que horas fossem quando o teste rodasse. Corrigido: todo `evaluate_slot`
  agora recebe `clock=lambda: <corte> + timedelta(seconds=2)`, o mesmo padrão de
  `test_context_per_version.py`. Revalidado (§2.4): os números batem com a execução acidentalmente
  correta de antes, então o bug não tinha corrompido o resultado já relatado — mas o teste ficou
  determinístico para qualquer hora em que rodar, o que importa.
- **MEDIUM, aplicado.** Ver §2.4 acima — linguagem causal trocada por hipótese explícita em três
  lugares (`Open Bugs.md`, este arquivo, o desenho).
- **NICE-TO-HAVE, não aplicado nesta tarefa:** evitar o pré-carregamento da família para barras já
  inelegíveis por atraso (hoje `load_family_readers` roda antes do `lag_s` de cada versão ser
  checado dentro de `evaluate_slot`) — teria custo extra de leitura durante uma recuperação de
  backlog. Registrado como pendência, não implementado: o `handle_candle` de hoje já constrói o
  `market` antes de saber a elegibilidade de cada versão, então mover o pré-carregamento para depois
  do gate de elegibilidade exigiria conhecer o `lag_s` de todo o grupo *antes* de decidir se vale a
  pena compartilhar — mudança de forma, não de uma linha, fora do escopo já grande desta tarefa.
- **Nomear a métrica "avaliações/s" em vez de "bars/s":** aplicado no texto solto (`Open Bugs.md`,
  este arquivo); mantive o nome do campo de log (`before_bars_per_s`/`after_bars_per_s`) porque é o
  termo literal do brief ("bars/s antes vs depois") e mudar o nome do campo depois de já ter rodado
  o teste geraria uma segunda rodada só por causa do nome.
- **"Não encontrei o `notes-T3.74b.md` citado":** a Astra revisou antes de eu terminar de escrever
  este arquivo (chamada em paralelo enquanto eu ainda montava as notas) — corrigido pela própria
  existência deste documento agora.

---

## 3. Comandos de qualidade (saída real)

```
$ uv run pytest services/strategy-worker/tests/test_replay_contract.py services/strategy-worker/tests/test_replay_drain_pause.py services/strategy-worker/tests/test_context_cache.py -q
54 passed in 5.10s

$ uv run pytest services/strategy-worker/tests -q -m unit
318 passed, 327 deselected in 8.43s

$ uv run pytest services/strategy-worker/tests/test_context_cache_engine.py -q -s
2 passed in 312.69s (0:05:12)   (saída completa em §2.4 — revalidada após a correção de relógio)

$ uv run ruff check services/strategy-worker/
All checks passed!

$ uv run ruff format --check services/strategy-worker/
125 files already formatted

$ uv run pyright services/strategy-worker
3 errors, 0 warnings, 0 informations
(pré-existentes, mesma família aceita em T3.73/T3.74: test_replay_stress.py:35 reportPrivateUsage
de _delayed/_plan_for, test_replay_drain_pause.py:91 reportPrivateUsage de _drain — nenhum é meu)

$ uv run python infra/scripts/check_file_size.py
scanned 597 files; 0 over budget, 0 grandfathered
(consumer.py 339, context_cache.py 160, replay/budget.py 334, replay/consumer_lag.py 71,
test_context_cache_engine.py 297)
```

## 4. Arquivos tocados/criados (árvore compartilhada — só o desta tarefa)

```
 M obsidian/07-BUGS/Open Bugs.md
 M docs/PIPELINE.md
 M services/strategy-worker/hunter_strategy_worker/consumer.py
 M services/strategy-worker/hunter_strategy_worker/context.py
 M services/strategy-worker/hunter_strategy_worker/replay/budget.py
 M services/strategy-worker/tests/test_consumer_isolation.py
 M services/strategy-worker/tests/test_replay_contract.py
 M services/strategy-worker/tests/test_replay_drain_pause.py
?? .claude/state/astra-review-t374b-consumer-lag.md
?? .claude/state/astra-review-t374b-context-cache-design.md
?? .claude/state/astra-review-t374b-final-diff.md
?? .claude/state/notes-T3.74b.md
?? docs/plans/T3.74b-CONTEXT-CACHE.md
?? services/strategy-worker/hunter_strategy_worker/context_cache.py
?? services/strategy-worker/hunter_strategy_worker/replay/consumer_lag.py
?? services/strategy-worker/tests/test_context_cache.py
?? services/strategy-worker/tests/test_context_cache_engine.py
```

`.claude/state/brief-T3.74b-consumer-lag-e-custo-por-barra.md` já existia (escrito pela T3.74, não
por mim). Nada em `apps/**` foi tocado; nenhum `.env*` foi lido ou escrito.

## 5. Ressalvas honestas (resumo)

1. **`consumer_lag` não fecha o sintoma medido.** É um sinal real (backlog de leitura do grupo),
   independente do heartbeat, mas o atraso confirmado de 97–185 s medido ao vivo nesta mesma tarefa
   ocorreu com `lag` em 0 quase o tempo todo. A causa (hipótese: publicação escalonada da mesma
   barra pelo `market-worker`; não estabelecida) segue sem correção. `REPLAY_CONSUMER_LAG_MAX = 100`
   é provisório (Astra: "um blip de 13 não estabelece uma distribuição saudável").
2. **O cache de contexto reduz query, mas o ganho de relógio medido localmente foi modesto (~10%).**
   O mecanismo está correto e provado (equivalência byte a byte, isolamento de falha), mas o quanto
   ele resolve o atraso de 125 s+ na VPS real não foi medido nesta tarefa — só argumentado a partir
   da pressão de CPU já medida em T3.74.
3. **Item 3 do brief (`pg_stat_statements`, devops-engineer) não foi tocado** — fora do papel
   backend-specialist desta execução.
4. Nenhuma escrita na VPS; toda medição ao vivo foi `HGETALL`/`XINFO GROUPS`/`XPENDING`/SQL
   `repeatable read read only`.
