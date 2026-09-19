# T4.63 — saída por evento no executor real de memes

**Data:** 2026-09-18. Motivo: CITIZEN (19:06:43 → 19:11:29 BRT), compra 0,0716 SOL, pico de marca
0,1303 (+82 %), venda pelo trailing a 0,0142 (−0,80 R) — a curva drenou **entre dois tiques** de
10 s de `exits.py`. Vault: `obsidian/11-KNOWLEDGE/KB-0139-saida-por-evento.md`. Contrato:
`docs/RISK_ENGINE_MEME.md` §9 "T4.63: saída por evento"; operação: `docs/ACTIVATION.md` 9g.

Retomada depois de o agente anterior cair no meio (trabalho parcial em disco, não commitado). O que
faltava e foi fechado nesta sessão: o carimbo do criador violava o CHECK
`ck_meme_live_positions_a_creator_sale_has_its_fraction` (carimbava `creator_sold_seen_at` sem
`creator_sold_fraction`); a marca do frame que dispara ficava presa no throttle de 1 s; o teste de
restart fechava a linha sem `exit_at` (CHECK `a_closed_position_says_when`).

## O que existe (flag `MEME_EVENT_EXITS`, padrão `off`)

- `event_exits_config.py` — `MEME_EVENT_EXITS` (`off`|`on`, outro valor ⇒ `off` com aviso),
  `SOLANA_RPC_WS_URL` (vazio deriva de `SOLANA_RPC_URL`; sem nenhum, o público),
  `MEME_EVENT_COMMITMENT` (`confirmed`; `processed` aceito mas nunca decide sozinho). Constantes:
  sync 2 s, fila 1000, restart 5 s, marca ≤ 1/s por posição.
- `event_exits.py` — três laços num `TaskGroup` próprio (`_sync_loop`, `_read_loop`,
  `_handle_loop`) + `run_event_exits_forever` (qualquer exceção ⇒ conta, loga com traceback
  redigido, reinicia 5 s depois; nunca derruba o `TaskGroup` do `main.py`). Frame ruim é
  `try`/`except` por frame (`event_exits_bad_frames`). Fila cheia descarta e conta.
- `event_exits_watch.py` — assinaturas = `open_positions` (mais velha primeiro, teto
  `max_open_positions`), `accountSubscribe` + `logsSubscribe` da PDA da curva; fechada ⇒
  `unsubscribe`; poda as travas de posições que já não estão abertas (nunca uma trava tomada).
  `Watched` carrega `creator`, `creator_initial_tokens` (`0048`), o pico e os dois ids lógicos.
- `event_exits_eval.py` — `accountNotification` ⇒ `reserves_of_account` ⇒ `exit_common.mark_sol`
  (o mesmo `quote_sell` do tique) ⇒ pico ⇒ `decide_exit` com `exit_common.exit_params` (os mesmos
  do tique) ⇒ `_write_mark` (throttle 1 s, **forçado** num pico novo e no frame que disparou) ⇒
  `exits.sell_on_event` numa task com referência forte. `logsNotification` ⇒ só `TradeEvent` do
  próprio mint; venda do `creator` ⇒ `creator_sold_fraction(token_amount, creator_initial_tokens)`
  (vendido ÷ alocação, teto 1, piso 0,000001; `None` sem alocação ⇒ **só memória**:
  `Watched.creator_sold` + `CreatorSoldMemory`) ⇒ `repo.stamp_creator_sold(..., fraction=…)` ⇒ o
  mesmo frame julgado com `creator_dump = true`. Dois disparos em < 1 s são um; disparo com venda
  em voo não abre outra.
- `exits.py` — `manage_position` (tique) e `sell_on_event` (evento) tomam `exit_common.exit_lock`
  por `position_id`, releem a linha sob a trava (`repo.open_position`; fechada ⇒ nada) e passam pela
  mesma `route_exit` → `_sell` com `CurveRead` fresco por HTTP. `exit_settle.py` recebeu
  `reconcile_sell`/`close_from_fill` (orçamento de 350 linhas).
- `repo_positions.py` — `open_position(id)`, `stamp_creator_sold(id, at, fraction, now)` (recusa
  fração fora de (0, 1] por nome; `WHERE status='open' AND creator_sold_seen_at IS NULL`).
- `entries.py` — `ctx.event_exits_wake.set()` depois de cada fill confirmado.
- `heartbeat.py` — `event_exits_enabled`, `_ws_state`, `_subscriptions`, `_updates_60s`,
  `_triggered_total`, `event_to_sell_submit_s_p50`/`_p95`, `_bad_frames`, `_restarts_total`,
  `_reconnects`, `_dropped`, `_creator_sells_seen`, `_marks_written`, `_sell_errors` — publicados
  com a flag desligada também (`off`/`0`).
- `main.py` — tarefa `meme-event-exits` só com a flag ligada; `event_ws.aclose()` no `finally`.
- Passthrough: `.env.example`, `infra/docker/docker-compose.yml`,
  `infra/vps/docker-compose.prod.yml` (`MEME_EVENT_EXITS`, `SOLANA_RPC_WS_URL`).

## Decisões desta sessão

- **Fração medida contra a alocação, não contra o saldo anterior.** A `0038` define a fração como
  vendido ÷ saldo anterior; este caminho não tem o saldo (uma leitura de RPC a mais na hora da venda
  seria latência no caminho crítico). Usa `creator_initial_tokens` (`0048`) como denominador —
  limite inferior da fração real quando ele comprou mais depois; teto 1. Sem alocação, **não
  carimba** (o schema recusa carimbo sem fração) e a visão fica em memória; `creator_dump` dispara
  igual. O log `meme_event_exit_creator_sold` diz `fraction`, `stamped`, `memory_only`.
- **Marca do frame que dispara sempre gravada**: `_decide` roda antes de `_write_mark`, com
  `force = new_peak or reason is not None` — a linha carrega o número da decisão.
- `mark_source` continua `solana_rpc` (mesmos bytes do mesmo nó; rótulo novo exigiria migração).
- O teste de integração do criador entrega o denominador ao `Watched` em memória em vez de gravar
  `creator_initial_tokens` na linha: `meme_tokens` é compartilhada entre os testes do pacote e a
  coluna é write-once (o trigger recusa até voltar a NULL);
  `test_token_context_reads_the_creators_recorded_allocation` precisa da linha ainda vazia e é a
  prova de que `token_context` lê a coluna da linha real.

## Comandos rodados (saída real)

- `timeout 590 uv run pytest services/meme-executor/tests/test_event_exits.py -q -p no:cacheprovider -m "not live"`
  → **20 passed in 1.52s**
- `timeout 590 uv run pytest services/meme-executor/tests/test_event_exits_integration.py -q -p no:cacheprovider -m "not live"`
  → **3 passed in 36.12s** (antes desta sessão: 3 failed)
- `timeout 590 uv run pytest packages/risk-core/tests -q -p no:cacheprovider -m "not live"`
  → **394 passed in 6.77s**
- `timeout 590 uv run pytest services/meme-executor/tests -q -p no:cacheprovider -m "not live and not integration"`
  → **402 passed, 47 deselected in 7.39s**
- `timeout 590 uv run pytest services/meme-executor/tests -q -p no:cacheprovider -m "integration and not live"`
  → **47 passed, 402 deselected in 158.36s**
- `uv run ruff check services/meme-executor` → All checks passed!;
  `uv run ruff format --check services/meme-executor` → 88 files already formatted
- `uv run pyright <17 módulos tocados + 2 testes>` → 0 errors, 0 warnings
- `uv run python infra/scripts/check_file_size.py` → scanned 979 files; 0 over budget

## Pendências / ressalvas

- `tests/test_event_exits.py` tem 785 linhas (o gate do projeto isenta `tests/`; `test_live_persistence.py`
  tem 1 800) — dividir quando alguém mexer nele de novo.
- `event_to_sell_submit_s` mede notificação → `submitted_at` da ordem; o pouso na cadeia continua
  sendo 1–3 s a mais (KB-0134/KB-0135). O ganho em R por posição fica para o primeiro dia ligado.
- Migração para PumpSwap com a flag ligada: `sell_on_event` ⇒ `route_exit` ⇒
  `handle_migrated_position` (o mesmo do tique); a curva completa (`complete = true` no frame) vira
  `curve_complete` ⇒ `mark_blocked(curve_complete_awaiting_migration)`, como no tique.
- Não commitado (regra da sessão). Arquivos de outros trabalhos já modificados na árvore e **não**
  tocados aqui: `.claude/launch.json`, `.claude/state/notes-T4.31-explain.txt`, `docs/DESIGN.md`,
  `packages/core/tests/unit/test_settings.py`.
