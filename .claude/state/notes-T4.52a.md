# T4.52a — Entrada instantânea: o executor acorda no instante da proposta

**Data:** 2026-09-17
**Pedido:** Everton, 17/09/2026 — "o robô precisa tomar decisão em milissegundos" (diretriz
"Entrada instantânea", ver memória). Meta do R55: derrubar o gargalo de 4,8 s medido entre a
proposta ser escrita e o executor pegá-la.

---

## 1. Desenho escolhido — e por que não o preferido do brief

O brief pedia, como opção preferida, Postgres `LISTEN`/`NOTIFY` (trigger `AFTER INSERT` em
`meme_proposals`, migração `0051`, conexão dedicada asyncpg no executor). **Não implementei essa
opção**: `docs/SPEC_REVIEW.md` §R7 e `docs/DATABASE.md` (repetido em ~15 revisões de migração, ex.
§27.5) proíbem `LISTEN`/`NOTIFY` **no projeto inteiro**, porque toda conexão de runtime passa por
um pooler em modo transação (Neon/PgBouncer) — uma sessão `LISTEN` não sobrevive a isso. O próprio
brief previu esse caso e deu a alternativa explícita: "check docs/DATABASE.md/infra/vps for
pgbouncer... if LISTEN/NOTIFY is awkward... Redis pub/sub". Escolhi essa alternativa.

**Desenho implementado — Redis pub/sub, sem migração nenhuma:**

- Canal `meme:proposals:wake` (`hunter_core.redis.keys.meme_proposals_wake`).
- Lado do radar (`services/meme-worker`): `LabContext.wake` (novo campo opcional,
  `Callable[[], Awaitable[None]] | None`) é chamado uma vez por tick de `lab_tick` que **comitou**
  pelo menos uma proposta — tanto pela porta do minuto (`_gate_step`/`scale_step`) quanto pela pista
  rápida de 15 s (`fast_gate_step`, T4.43). A publicação real (`hunter_meme_worker.wake.wake_publisher`)
  faz `PUBLISH meme:proposals:wake` no Redis do `WorkerRuntime`, depois que os `role_session` de
  cada inserção já fecharam (ou seja, depois do commit).
- Lado do executor (`services/meme-executor`): `ProposalWakeListener` (`wake.py`) assina o canal
  numa conexão pub/sub dedicada e liga um `asyncio.Event` (`ExecutorContext.wake_event`) a cada
  mensagem. `main.forever(...)` ganhou um parâmetro opcional `wake_event`: quando presente, o
  intervalo de espera entre execuções do passo (`entries_once`, `config.loop_s` = 1 s por padrão)
  vira um **timeout**, não mais o único gatilho — `asyncio.wait_for(wake_event.wait(),
  timeout=interval_s)`. Perdeu a corrida (Redis fora do ar, mensagem perdida)? O poll de 1 s
  continua rodando exatamente como antes.
- Reconexão: `ProposalWakeListener` reconecta com backoff exponencial com jitter
  (`redis.backoff.ExponentialWithJitterBackoff`, base 0,25 s, teto 5 s) e nunca derruba o processo —
  um Redis instável degrada a latência, nunca a correção (o polling nunca para).
- Nada em admissão, kill switch, sizing ou simulador mudou. Uma mensagem duplicada ou "falsa" (ex.
  publicada e a inserção não commitou por algum motivo — não deveria acontecer, mas é inofensivo)
  só faz o executor rodar `entries_once` um pouco mais cedo; a query do próprio `entries_once`
  continua sendo a única fonte de verdade.

## 2. Medição: latência antes/depois (nos testes deste pacote)

- **Antes (R55, produção real, 24 h):** Proposal→Received p50 = 4,8 s, p95 = 7,5 s (76 % da
  latência ponta a ponta de 6,6 s).
- **Depois (testado com Redis real via testcontainers, `test_wake_integration.py`):** publicação →
  `asyncio.Event` ligado em bem menos de 200 ms (o teste falha se passar de 200 ms; nas execuções
  locais ficou na casa de poucos ms — o teto de 200 ms inclui a margem de rede+scheduler do
  container). Isso é só a metade "escuta" do caminho; a medida completa em produção só se lê depois
  do deploy, pelo novo campo do heartbeat abaixo.
- **Novo campo de heartbeat (`hb:meme:executor`):** `proposal_pickup_lag_s_p50` /
  `proposal_pickup_lag_s_max` — mediana e máximo de `received_at - proposal.proposed_at` sobre as
  últimas 200 propostas que `entries_once` viu (`ExecutorState.pickup_lags`, uma amostra por
  proposta, nunca duas — `live_candidates` nunca reoferece uma proposta que já tem `meme_live_orders`).
  É o mesmo número que o R55 mediu como "Proposal→Received"; dá para reler depois do deploy sem
  precisar reconstruir a consulta do R55 do zero.

## 3. Arquivos

**Criados:**
- `services/meme-executor/hunter_meme_executor/wake.py` — `ProposalWakeListener`.
- `services/meme-worker/hunter_meme_worker/wake.py` — `wake_publisher`.
- `services/meme-worker/hunter_meme_worker/lab_scale_step.py` — `_scale_step` extraído de `lab.py`
  (renomeado `scale_step`, público) só para caber no orçamento de 350 linhas depois da adição do
  campo `wake`; comportamento idêntico, mesma assinatura interna.
- `packages/core/hunter_core/redis_lock.py` — `acquire_lock` extraído de `redis.py`, mesmo motivo
  de orçamento de linhas (a nova chave `meme_proposals_wake()` empurrou o arquivo para 355 linhas;
  como só dois arquivos de teste importavam `acquire_lock`, movê-lo foi mais simples que reexportar
  com import circular).
- Testes: `services/meme-executor/tests/test_wake.py`, `test_wake_integration.py`,
  `test_forever_wake.py`; `services/meme-worker/tests/test_lab_wake.py`.

**Modificados:**
- `packages/core/hunter_core/redis.py` (nova chave), `packages/core/tests/unit/test_redis_keys.py`,
  `packages/core/tests/integration/test_redis_integration.py` (import de `acquire_lock` movido).
- `services/meme-executor/hunter_meme_executor/{context.py,repo.py,entries.py,heartbeat.py,main.py}`
  — `wake_event`, `pickup_lags`, `proposed_at` no `Candidate`, campos novos no heartbeat, fiação do
  listener e do fallback no `TaskGroup`.
- `services/meme-executor/tests/{conftest.py,test_live_persistence.py}` — fixtures de Redis
  (mesmo padrão do `market-worker`), dois testes novos de pickup lag, `_plant_proposal` ganhou
  `proposed_at` opcional.
- `services/meme-worker/hunter_meme_worker/{lab.py,main.py}` — campo `wake`, chamada em `lab_tick`,
  fiação do publisher.
- `docs/RISK_ENGINE_MEME.md` §9 — novo bloco datado T4.52a.

## 4. Comandos rodados (saída real)

```
uv run pytest packages/core/tests/unit -q                          → 1350 passed
uv run pytest packages/core/tests/integration/test_redis_integration.py -q → 5 passed
uv run pytest services/meme-executor/tests -q                      → 199 passed (131.21s)
uv run pytest services/meme-worker/tests -q                        → 440 passed (740.36s)
uv run pytest services/meme-worker/tests/test_lab_lines.py services/meme-worker/tests/test_lab_persistence.py
    services/meme-worker/tests/test_lab_fast.py services/meme-worker/tests/test_lab_mayhem.py
    services/meme-worker/tests/test_lab_operator_3.py services/meme-worker/tests/test_lab_moonshot.py -q
                                                                     → 29 passed
uv run ruff check .                                                 → limpo nos arquivos tocados
                                                                        (10 erros pré-existentes só em
                                                                        infra/scripts/research/*.py,
                                                                        não tocados)
uv run ruff format --check services/meme-executor services/meme-worker packages/core
                                                                     → 459 files already formatted
uv run pyright services/meme-executor/hunter_meme_executor
    services/meme-worker/hunter_meme_worker
    packages/core/hunter_core/redis.py packages/core/hunter_core/redis_lock.py
                                                                     → 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py                      → scanned 928 files; 0 over budget
```

## 5. O que fica para T4.52b

O tick do próprio radar continua em 15 s (pista rápida, `fast_lane_cycle_s`) / 60 s (porta do
minuto, `lab_cycle_s`) — essa fila (do evento na curva até o radar notar e escrever a proposta) não
foi tocada aqui. T4.52a só fecha a fila entre "proposta escrita" e "executor pegou"; a fila entre
"evento de mercado" e "proposta escrita" é o próximo alvo declarado no R55 §6 (poll do radar em vez
de reagir a evento) e fica para T4.52b.

## 6. Arquivos que não toquei (por instrução explícita)

`wallet_refresh.py`, os campos de carteira do `heartbeat.py` (só adicionei os campos de pickup lag,
não mexi nos de carteira), `packages/core/hunter_core/universe.py`.
