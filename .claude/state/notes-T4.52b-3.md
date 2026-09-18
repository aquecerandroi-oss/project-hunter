# Notas T4.52b-3 — o portão de evento

Data: 2026-09-18. Escopo: `services/meme-worker/hunter_meme_worker/event_gate*.py`,
`event_gate_wiring.py`, `status_wiring.py`, `lab.py`/`lab_fast.py` (o campo `caches` e o guarda
`recently_proposed`), `proposals.py`/`proposals_row.py`/`lab_repo_fast.py` (três campos novos em
`GateRow`), `main.py` (fiação), `.env.example`, `infra/vps/docker-compose.prod.yml`,
`docs/RISK_ENGINE_MEME.md` §9, `docs/DATABASE.md` §43.2.

## 1. Arquitetura entregue

`event_gate.py` ficou fino de propósito (121 linhas): só as cinco corrotinas (`_sync_loop`,
`_read_loop`, `_evaluate_loop`, `_flush_loop`, `_heartbeat_loop`) e `run_event_gate`. O resto foi
para módulos por responsabilidade (todos ≤ 350 linhas):

- `event_gate_config.py` — `MEME_EVENT_GATE`/`SOLANA_RPC_WS_URL`/`MEME_EVENT_COMMITMENT`/
  `MEME_EVENT_GATE_MAX_MINTS` lidos do ambiente a cada chamada (mesmo padrão de
  `fast_lane_config.py`/`events_config.py`); fila (2000) e debounce (100 ms) são constantes, não
  variáveis — o plano já fixa os dois números.
- `event_gate_runtime.py` — `EventGateRuntime` (o estado que todo laço lê/escreve) e `Debouncer`
  (puro, testável sem asyncio: `poll(mint, now_s)`/`drain_ready(now_s)`).
- `event_gate_caches.py` — `EventGateCaches`, alimentada por `lab_fast.fast_gate_step` a cada
  tique: `specs` (só `clock == "15s"`), `open_mints` (substituído por inteiro a cada refresh — uma
  posição fechada não pode ficar bloqueada para sempre), `base_rows` (mesclado, mint a mint, para
  sobreviver a um tique sem foto nova daquele mint), `pedigree`/`e2b` (por mint, não por
  `(mint, end_time)` — ver §3), e `recently_proposed_mints`/`mark_proposed`, o guarda que as duas
  pistas escrevem e leem.
- `event_gate_rows.py` — `build_event_row`: a `GateRow` em memória. `EventReserves` é um par
  `(virtual_sol, virtual_token)` deliberadamente separado de `event_state.CurvePoint` (que nunca
  carrega reservas virtuais) — vem do próprio evento que disparou a avaliação, não da série.
- `event_gate_subscriptions.py` — `sync_subscriptions`: assina/desassina contra
  `fast_lane.young_mints`, sem query nova.
- `event_gate_eval.py` — `apply_notification` (funde uma notificação no estado), `evaluate_mint`
  (a única função que abre sessão) e `handle_reconnect`.
- `event_gate_wiring.py`/`status_wiring.py` — a glue de `main.py`, extraída para caber no
  orçamento (o `main.py` também ganhou `register_health`/`register_lab_health` movidos para
  `status_wiring.py`, sem mudança de comportamento).

## 2. Três campos novos em `GateRow` (compatíveis, default `None`)

`initial_real_token_reserves` (a linha de 15 s já selecionava a coluna mas descartava — o portão de
evento precisa dela para `compute_fast` refazer o progresso sobre a série em memória, já que
`curve_progress_pct` da linha-base é uma foto parada) e `recent_drawdown_pct`/`_peak_age_s`/
`_reason` (EXP-M13, T4.52b-2): só o portão de evento os preenche; a pista de 15 s/minuto continua
lendo `None` → `recent_drawdown_unknown`, o comportamento de falha fechada que já existia — nenhum
set congelado muda de veredito.

## 3. Simplificações declaradas (consistentes com o desenho já existente, não atalhos novos)

1. **Drawdown com a janela padrão (60 s/30 s), não a do set.** `evaluate_gate` já julga **uma**
   `GateRow` compartilhada por todos os sets de um tique (a fita de 60 s, por exemplo, também não
   varia por set); o portão de evento segue a mesma convenção. Só um set nomearia
   `max_recent_drawdown_pct` com janela própria — nenhum existe hoje.
2. **Pedigree/E2-b por mint, não por `(mint, end_time)`.** O portão de evento julga um instante que
   o tique nunca leu, então a chave exata do E2-b não pode bater; o cache guarda a última leitura
   por mint e a reaplica sob uma chave nova — uma aproximação, documentada, que vira
   `e2b_top_buyer_unknown` no pior caso (mint fora do cache), nunca um número errado sob a chave
   certa.
3. **`event_to_proposal_s` é `(slot atual − slot do evento) × 0,4 + segundos desde `last_event_at``**,
   não uma medição de `path_ms` monotônica separada — o plano aceita essa fórmula (§3) e o teste de
   integração não a exercita além de "não quebra"; falta medir ao vivo (T4.52b-5, rollout).
4. **`fast_gate_step` só atualiza os caches quando tem uma linha de 15 s nova na janela.** Se não
   houver foto nova (`load_fast_gate_rows` vazio), a função já retornava cedo antes desta tarefa;
   isso significa que `open_mints`/`base_rows`/`pedigree` podem ficar até `lab_cycle_s` mais um
   pouco (não só 15 s) sem refresh num mint parado — aceitável dentro do "≤ 15 s" que o plano
   declara como o normal, mas vale registrar para quem for medir ao vivo.

## 4. Testes

- `test_event_gate_pure.py` (11 casos, sem Docker): `Debouncer`, `recently_proposed`/TTL/escopo por
  `rule_set`, `refresh_event_gate_caches` (substitui `open_mints`, mescla `base_rows`),
  `build_event_row` fail-closed (fita aquecendo, sem `total_supply`/reservas, sem leitor de
  holders).
- `test_event_gate_notify.py` (7 casos, sem Docker, `FakeWs`): sincronização de assinaturas
  (assina, desassina por idade, respeita o teto), `apply_notification` decodificando as fixtures
  reais da T4.52b-1 (`trade_events_from_logs`), ignorando uma assinatura desconhecida, atualizando
  `rt.slot` sem nunca regredir. As fixtures têm `block_time` real (18/09); os testes rebasam
  `received_at` para `block_time + 0,5 s` por notificação — sem isso, o `janela de 120 s` do estado
  as descartaria de cara (o `received_at`/`now` do parse é sempre "hoje").
- `test_event_gate_integration.py` (6 casos, testcontainers Postgres): evento que passa
  `flow_v2/1` → uma linha em `meme_proposals` com `series = meme_event_gate_v1` e um `wake`;
  replay duplo → uma linha (o índice único); `recently_proposed` marcado por uma pista bloqueia a
  outra; `fast_gate_step` no mesmo instante (proposta plantada à mão + tique fresco) → `already_open`
  via `open_mints`; modo `shadow` conta e nunca insere; sem linha-base → contador, nenhuma
  avaliação; reconexão com `websockets.serve` real (dropa uma vez) → `meme_ingest_gaps` gravado,
  `state.gaps` incrementado, a fita zerada.

  **Achado de teste, registrado por precisar de duas rodadas para pegar:** (1) o servidor de teste
  do reconnect tem que mandar a notificação **e** a resposta de id — só a resposta nunca chega a
  `listen()` como algo que `_read_loop` veja, então o reconhecimento de reconexão nunca dispara.
  (2) `task.cancel()` logo depois que `rt.stats.reconnects` vira 1 corre com a própria escrita do
  `meme_ingest_gaps` (que só acontece depois, dentro da mesma função) — cancelar no meio de um
  `role_session` desfaz a transação. O teste agora espera a **linha aparecer no banco**, não um
  tempo fixo, antes de cancelar.

## 5. Comandos

- `pytest services/meme-worker/tests -m "not live and not integration"`: 373 passed (era 355 antes
  desta tarefa).
- `pytest services/meme-worker/tests/test_event_gate_integration.py`: 6 passed (~28 s).
- `pytest services/meme-worker/tests/test_lab_fast.py test_lab_wake.py test_lab_persistence.py`
  (os arquivos que `proposals.py`/`lab_fast.py`/`GateRow` tocam mais de perto): 24 passed.
- `pytest services/meme-worker/tests -m "integration and not live" --ignore=.../test_event_gate_integration.py`:
  94 passed (a suíte de integração pré-existente, intocada).
- `ruff check`/`format --check` limpos em `services/meme-worker/` (964 arquivos escaneados por
  `check_file_size.py`, 0 acima do orçamento). `pyright` limpo (0 erros) em todos os arquivos
  tocados, incluindo os três de teste novos.

## 6. O que fica para T4.52b-4/5 (fora do escopo desta tarefa, mas já parcialmente entregue aqui)

O brief desta rodada pediu wiring/config/heartbeat/docs além do que o `plan-T4.52b.md` original
reserva para a T4.52b-4 — entregue junto (config module, `main.py`, heartbeat `event_gate_*`,
`status_details["event_gate"]`, `.env.example`, `docker-compose.prod.yml`). Falta, para uma
T4.52b-4/5 futura se ainda for aberta: medir `event_to_proposal_s` ao vivo contra a fórmula do §3,
decidir se `event_gate_stats`/`event_gate_heartbeat_fields` precisam de um teste de reconexão via
`main.py` inteiro (hoje só `_read_loop`+`handle_reconnect` são exercitados diretamente), e o
rollout em três fases que `plan-T4.52b.md` §5 descreve (off → shadow 24 h → on).

## T4.52b-4 (consertos)

Data: 2026-09-18. Escopo: os sete achados de `review-T4.52b.md` (F1–F7), a corrida entre pistas do
§2 e as métricas do §5, sobre o mesmo conjunto de arquivos da T4.52b-3 mais dois novos
(`proposal_race.py`, `test_proposal_race.py`). `services/meme-executor/` e `apps/` não tocados.

### F1 — memória sem teto

`event_gate_caches.py` ganhou `EventGateCaches.updated_at` (quando `base_rows`/`pedigree`/`e2b`
souberam de um mint pela última vez) e `prune_event_gate_caches(caches, keep, now, max_mints)`:
evict por `mint not in keep` **ou** `updated_at < now - 10min`, depois um teto duro de
`max_mints * 2` (derruba os mais antigos primeiro mesmo que ainda "kept"). `Debouncer` ganhou
`forget(mint)` e `prune(keep, now_s, max_age_s)` com a mesma regra. Chamado de dentro de
`sync_subscriptions` (a cada `subscription_sync_s`, que já calcula `young_mints`) — não dentro de
`refresh_event_gate_caches` (chamado por `lab_fast.fast_gate_step`), para não mudar a assinatura
que `test_refresh_replaces_open_mints_wholesale_but_merges_base_rows` já fixa. `_unsubscribe_mint`
também chama `rt.debouncer.forget(mint)` e limpa `pending_trail`/`trail_last_written` do mint (ver
F6/F7). Heartbeat: `_heartbeat_loop` (`event_gate.py`) monta `cache_sizes` (`base_rows`, `pedigree`,
`e2b`, `debounce`) e `heartbeat_fields` os prefixa como `event_gate_cache_*`.

### F2 — queda do WS / crash-loop do worker inteiro

`rpc_ws.py`: `listen()` nunca mais levanta `ExchangeUnavailable` — `_backoff_or_raise` virou
`_backoff` (sempre dorme, nunca levanta; teto de backoff caiu de 60 s para 30 s, como o brief
pede); `MAX_RECONNECT_FAILURES`/`max_reconnect_failures` removidos (nada mais os lia fora do
próprio módulo — conferido por grep). `attempt` zera na conexão bem-sucedida (`ws_state=connected`),
não só na entrega de uma notificação. O timeout de ociosidade (`IDLE_TIMEOUT_S`) só arma quando
`self._specs` não está vazio — zero assinaturas nunca conta como falha.
`event_gate.py`: `run_event_gate_forever` é o que `main.py` roda agora (era `run_event_gate` direto)
— qualquer exceção (incluindo o `ExceptionGroup` do `TaskGroup` interno) é logada e a porta inteira
reinicia após 5 s, sem propagar para o `TaskGroup` de `main.py` (que mataria discovery/via
rápida/Lab junto). Também novo: `_slot_subscribe_loop` (chama `subscribe_slot()` uma vez, com
retry) — dá `rt.slot` para `event_to_proposal_s` e garante que a conexão nunca fica com zero
assinaturas por muito tempo.

### F3 — `creator_sold` só pode ADICIONAR uma venda

`event_gate_rows.py`: `base.creator_sold=True` vence sempre; `base.creator_sold=None` usa a regra
da própria pista (`covered_from_birth` → `False`, senão `None`); `base.creator_sold=False` só é
promovido a `True` por uma venda que a memória de fato testemunhou — nunca voltando a `None`.

### F4 — `top10_share` não pode nascer só na pista de evento

`event_gate_rows.py`: `top10_share`/`top10_reason` agora vêm literalmente de `base.top10_share`/
`base.top10_reason` (hoje sempre `None`, porque `lab_repo_fast._FAST_ROWS` não seleciona a coluna)
em vez de calculados dos boards em memória — a pista de evento falha fechado exatamente como a de
15 s até que exista um leitor lá.

### F5 — curva completa no meio do caminho

`event_gate_rows.py`: `completed_at=base.completed_at or (as_of if state.complete else None)` — um
`accountNotification` que já viu `complete=True` marca `completed_at` na hora, em vez de esperar o
próximo tique de 15 s atualizar `meme_tokens.completed_at`.

### F6/F7 — sessão de banco por avaliação e `shadow` que escreve

`event_gate_eval.py` reestruturado: `shadow` nunca abre `role_session` (avalia todos os sets em
memória, classifica, conta, loga, retorna); `on` só abre uma sessão quando pelo menos um set
produziu um rascunho para inserir. A trilha de recusa por mint não é mais escrita por avaliação —
fica em `EventGateRuntime.pending_trail`/`trail_last_written` (novos campos) e só é gravada (a) na
mesma sessão de um insert daquele mint, ou (b) pelo novo `_trail_flush_loop` (`event_gate.py`, a
cada 15 s, via `event_gate_eval.flush_pending_trail`) — nunca mais de uma vez por mint por minuto
(`TRAIL_COOLDOWN_S=60`).

### Corrida entre pistas (§2) e métricas (§5)

`proposal_race.py` (novo): `insert_proposals_reserved` reserva o mint (`caches.mark_proposed`)
**antes** do `await insert_proposals`, e libera (`caches.unmark_proposed`, novo) se aquele insert
não inseriu nada (a linha já existia — provavelmente da outra pista). `lab_fast.py` e
`event_gate_eval.py` chamam a mesma função em vez de inserir em lote e só marcar depois.
Métricas: `_slot_subscribe_loop` garante `rt.slot` (então `event_to_proposal_s` deixa de ser sempre
vazio); `shadow_proposals_total` dedupa por `(mint, rule_set)` via `EventGateCaches.shadow_marked_until`
(novo, TTL próprio, nunca lido por `already_open`); `shadow_only_event_mints`/`shadow_agree_mints`
(novos campos em `EventGateStats`, janela de 60 s) classificam cada avaliação de `shadow` contra
`caches.recently_proposed_mints` (a pista de 15 s): mint já coberto por ela → "agree"; mint que só
o evento propõe → "only". Aproximação declarada: por não haver DB em `shadow`, a comparação é só
contra o que a pista de 15 s marcou nesta mesma instância de processo (TTL do `lab_proposal_ttl_s`),
não contra o histórico completo de `meme_proposals` — medir isso de verdade ao vivo (T4.52b-5).

### Testes novos

- `test_event_gate_pure.py`: +12 (F1 × 4 incluindo `Debouncer.forget`/`prune`; F3 × 3; F4 × 1; F5 × 2;
  mais o par de pruning de `EventGateCaches`).
- `test_proposal_race.py` (novo, 4 casos): reserva antes do insert, liberação em insert que não
  inseriu nada, reserva seletiva quando só um de vários rascunhos vence, sem `caches` insere sem
  reservar.
- `test_pumpfun_rpc_ws.py`: +2 — seis recusas de conexão seguidas de uma aceita (a tarefa continua
  viva, nunca um `ExchangeUnavailable`); ociosidade sem nenhuma assinatura não conta como falha
  (escalado para frações de segundo, não os 10 min reais do plano).
- `test_event_gate_integration.py`: +2 — `shadow` não escreve a trilha nem para um quase-passa
  (contagem contra uma baseline, porque o próprio seed do teste já grava uma linha de "muito jovem"
  para o mesmo mint); `on` enfileira a trilha em vez de escrever por avaliação, o flush periódico
  escreve uma vez, e uma segunda quase-falha 2 s depois não duplica (cooldown de 60 s).

### Comandos

- `uv run pytest services/meme-worker/tests -q -m "not live and not integration"` → `387 passed,
  102 deselected` (era 373 antes desta rodada).
- `uv run pytest services/meme-worker/tests/test_event_gate_integration.py -q` → `8 passed in
  ~36s` (era 6).
- `uv run pytest services/meme-worker/tests/test_lab_fast.py test_lab_wake.py -q` → `10 passed`
  (sem mudança de contagem — só a fiação do `insert_proposals_reserved`).
- `uv run pytest services/meme-worker/tests/test_proposal_race.py -q` → `4 passed`.
- `uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_rpc_ws.py -q` → `14 passed`
  (era 12).
- `uv run ruff check`/`format --check` limpos em `services/meme-worker/` e
  `packages/exchange-adapters/` (313 arquivos formatados). `uv run python
  infra/scripts/check_file_size.py` → `965 files; 0 over budget`. `uv run pyright` limpo (0 erros)
  em todos os arquivos tocados (fonte e teste).
- `uv run pytest services/meme-worker/tests -m "integration and not live"
  --ignore=.../test_event_gate_integration.py` (a suíte de integração pré-existente, 94 casos
  antes desta rodada): saída em segundo plano (excedeu 120 s), `exit code 0` — todos passaram; a
  contagem exata não ficou no buffer capturado (só os pontos), mas o código de saída confirma zero
  falhas.

### Concerns

- A classificação `shadow_only_event_mints`/`shadow_agree_mints` é uma aproximação (parágrafo
  acima) — não é uma prova de "o evento chegou primeiro", só um indício.
- `event_to_proposal_s` continua a fórmula aproximada da T4.52b-3 (§3 do plano) — o `subscribe_slot`
  novo só garante que `rt.slot` deixa de ser `None`, não que a fórmula em si foi validada ao vivo.
- Nenhum destes sete fixes muda o veredito de F-drawdown (janela fixa 60/30 ignorando
  `recent_drawdown_window_s` do set) nem a lista de "raio de explosão" restante do §4 da revisão
  além dos itens F1–F7 nomeados — continuam fora do escopo desta tarefa.
