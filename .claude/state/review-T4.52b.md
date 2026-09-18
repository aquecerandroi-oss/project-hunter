# review-T4.52b — revisão de risco (somente leitura) de `88e2b4f7` (T4.52b-2) e `549b1ac1` (T4.52b-3)

**Data:** 2026-09-18 · **Revisor:** guardião do risk-engine · **Escopo:** diffs dos dois commits, `plan-T4.52b.md`,
`notes-T4.52b-2.md`, `notes-T4.52b-3.md`, código vivo em `services/meme-worker`, `services/meme-executor`,
`packages/indicators`, `packages/exchange-adapters`. Nada editado; VPS/.env intocados.

**Veredito curto:** `88e2b4f7` **SAFE_TO_DEPLOY(off)** (puro, opt-in, falha fechada). `549b1ac1` **SAFE_TO_DEPLOY(off)**
byte-a-byte no comportamento com `MEME_EVENT_GATE=off`; **BLOCK para `shadow` e para `on`** até fechar F1–F5 abaixo
(memória sem teto, crash-loop do worker inteiro numa queda do WS ou lull de 6 min, sessão de banco por evento sobre
um pool de 4, `shadow` que escreve no banco e conta sem dedupe, `creator_sold`/`top10`/`curve_complete` mais
permissivos que a pista de 15 s).

Comandos rodados (saída real): `uv run pytest services/meme-worker/tests -q -m "not live and not integration"` →
`373 passed, 100 deselected in 5.02s`; `pytest …test_event_gate_pure.py …test_event_gate_notify.py …test_event_state.py
packages/indicators/tests/unit/test_meme_drawdown.py` → `45 passed`. Sonda própria (scratchpad, `build_event_row`):
```
A base.creator_sold=True  -> event creator_sold = False | covered_from_birth = True
B base.creator_sold=True  -> event creator_sold = None
C base.top10_share=None   -> event top10_share = 0.2 reason None
D state.complete=True     -> row.completed_at = None | snapshot.complete = True | progress_pct = 0.100000
E 2 points 100 ms apart   -> progress_rising = None reason too_few_points
F snapshot.observed_at = as_of
```

## 1. Mesma porta, mesmos parâmetros?

**Sim na função, não em três campos.** `event_gate_eval.py:170` chama `proposals.evaluate_gate` com `caches.specs`
(só `clock == "15s"`, `event_gate_caches.py:89`) — mesmos `RuleSetSpec`, mesmo `ttl_s`, mesmo `pedigree`/`e2b`
(por mint, aproximação declarada; ausente ⇒ `pedigree_unknown`/`e2b_top_buyer_unknown`, fechado).
`already_open` = `caches.open_mints[spec]` (foto do último tique, ≤ 15 s + backlog) ∪ `recently_proposed` — semântica
igual à de `lab_fast.py:103-105`, com a única diferença de o `open_mints` ser cache em vez de leitura viva (só menos
bloqueante quando uma aposta fecha entre tiques; nunca mais permissivo para proposta pendente, que está no
`recently_proposed` com TTL = `ttl_s`).

- **`progress_rising`/`holders_rising`: mesmo cálculo.** `event_gate_rows.py:63-77` chama `compute_fast` e
  `holders_trend` (`hunter_indicators/meme/fast.py:243-303`, `306-322`) sobre os pontos em memória; a referência tem
  de ter `observed_at ≤ newest − 60 s`, senão `too_few_points` → `progress_trend_unknown` (sonda E). Dois pontos a
  100 ms **não** dizem "rising". `apply_photo` (`event_state.py:227`) nunca é chamado: só eventos alimentam `points`
  — menos pontos que a série de 15 s, logo mais `too_few_points`, nunca menos. Fechado.
- **F3 — `creator_sold` MAIS permissivo (MÉDIO).** `event_gate_rows.py:136` sobrescreve `base.creator_sold` com
  `flow.net_seller` (`event_state.py:118-122`): `False` se `covered_from_birth` (assinatura ≤ 5 s após
  `first_seen_at`, `event_state.py:292`), senão `None`. A linha-base de 15 s dizia `True` (fita swap-api/batch viu
  a venda) e a linha de evento diz `False`/`None`. Cenário: criador vende via router/ALT que o filtro `mentions`
  não entrega (plano §1 item 8: "risco a medir", nunca medido), ou venda nos 5 s de graça, ou **restart do worker**
  (assinatura nova, `covered_from_birth` falso ⇒ `None` ⇒ passa com `creator_unknown_allowed_if_dev_measured` e
  `dev_share ≤ 0,10`, o que o `operator/5` usa — `RISK_ENGINE_MEME.md:192`). Resultado: proposta que a pista de 15 s
  recusaria `creator_is_net_seller`. A admissão do executor relê a ATA (T4.45) e refaz o veto (R56: 64 recusas) —
  não compra, mas o pré-registro "evento nunca mais permissivo que 15 s" cai. **Fix:** `creator_sold = True if
  base.creator_sold else flow.net_seller` (venda vista em qualquer fonte é venda).
- **F4 — `top10_share` MAIS permissivo (BAIXO hoje, MÉDIO ao editar o set).** A pista de 15 s nunca carrega
  `top10_share` (`lab_repo_fast.py:_FAST_ROWS` não seleciona; `GateRow.top10_share=None` ⇒ `top10_unknown` para
  qualquer set com `max/min_top10_share`); a de evento preenche dos boards (`event_gate_rows.py:124`, sonda C). Um
  set `15s` que ganhar `max_top10_share` na mesa passa a propor **só** pelo evento. Fail-closed? Não: é dado real,
  mas a comparação shadow × 15 s fica falsa por construção. **Fix:** ou carregar `top10_share` na `_FAST_ROWS`, ou
  deixar `top10_share=None` na linha de evento até lá.
- **F5 — `curve_complete` não é herdado do estado (MÉDIO).** `state.complete=True` (accountNotification) não
  toca `completed_at` (`event_gate_rows.py:107-139`, sonda D): `entry_features_of` lê `curve_complete =
  completed_at is not None` ⇒ `False`. Com `operator/5` em `max_progress_pct = 100` (T4.58) e `real_token = 0`
  ⇒ progresso 100 % **não** excede 100 ⇒ proposta de curva completa; só a janela 2–50 % do executor barra. Janela de
  exposição: até 5 s (`sync_subscriptions`) após `finished`. **Fix:** `completed_at = base.completed_at or (as_of if
  state.complete else None)`.
- **Drawdown com janela fixa 60/30 (`event_gate_rows.py:105`) ignorando `recent_drawdown_window_s` do set (BAIXO).**
  KB-0118: TAXCOIN dd 0,12 em N = 60 × 0,82 em N = 120 — um set que nomear 120 recebe a medida de 60 e **passa** onde
  queria recusar. Nenhum set liga hoje. **Fix:** calcular com `max(spec.gate.recent_drawdown_window_s)` ou por set.
- `holders/snipers/dev_share/pedigree/e2b/mayhem/snapshot`: mesma fonte que `fast_lane._readings`, fechados por nome
  (`no_holders_reader`, `snipers_unknown`, `no_snapshot_for_quote`, `mayhem_unknown`). `Snapshot.observed_at = as_of`
  (`event_gate_rows.py:89`) em vez do `observed_at` do ponto — honestidade do carimbo na `quote`, sem efeito de risco.

## 2. Dupla proposta

Índice único `(rule_set_id, mint, features_end_time)` não segura as duas pistas (end_time diferente); o guarda é
`recently_proposed` em memória. **Janela de corrida real, ambos os sentidos (MÉDIO):** `lab_fast.py:103-105` lê
`already_open` e depois avalia + `await insert_proposals` (`:125`) antes de `mark_proposed` (`:130`); o evento em
`event_gate_eval.py:154-176` lê o guarda e só marca depois de `await role_session` + `await insert_proposals`. Um
evento chegando durante o `insert` do tique (ou vice-versa) ⇒ duas linhas `proposed` para o mesmo mint/set. O teste
`test_fast_gate_step_in_the_same_instant_makes_already_open` planta a proposta à mão; não exercita a intercalação.
**No executor não compra duas vezes enquanto a 1ª está viva:** `auto_approve.py:171` `mint_busy` (posição aberta ∪
`pending_attempts`), `max_per_tick=1`, `mint_repeated`. **Pode recomprar** se a posição 1 sair (stop/creator_dump
em < 60 s, como PS no R56 a +47 s) e a proposta 2 ainda tiver `proposed_at` < 60 s (`AUTO_APPROVE_MAX_AGE_S`,
`auto_approve.py:90`) e `expires_at` no futuro: `mint_busy` some, não há cooldown de reentrada por mint, e a admissão
só refaz `duplicate_position` sobre posições abertas. **Fix:** `mark_proposed` **antes** do insert (reverter se 0
inseridos) nas duas pistas, e/ou o executor pular `proposed` cujo mint teve saída nos últimos N s.

## 3. Não-antecipação e relógio

`as_of` = `utcnow()` do worker no instante da avaliação (`event_gate.py:84,95`), não o `block_time`; `received_at`
é carimbado no parse (`rpc_ws.py:_parse_frame`) ⇒ sempre ≤ `as_of`; `compute_fast`/`tape_for`/`PeakDeque` filtram por
`received_at` e o `state.recent_drawdown` cai na dobra exata se a deque tem ponto posterior (`event_state.py:277-283`).
`features_end_time = proposed_at = as_of` ⇒ nunca no futuro do `now()` do executor (mesmo host); o executor nem lê
`features_end_time` da proposta (usa o de `meme_features_1m`, `admission.py:207-218`) e mede idade por `proposed_at`.
`accountNotification` sem block time ⇒ `observed_at = received_at` (`event_state.py:213`): um ponto "mais novo" que o
trade do mesmo slot por ~1 s — só torna a referência de 60 s mais conservadora. Sem achado.

## 4. Raio de explosão

- **`off`:** `build_event_gate` devolve `None` (`event_gate_wiring.py:34-45`), sem WS, `LabContext.caches=None` ⇒
  `lab_fast` só cria um dict vazio (`:92`); `_register_health` virou `status_wiring.register_health` (movimento fiel,
  conferido). Comportamento equivalente ao anterior; não byte-a-byte (dict extra, 3 `None` em `EntryFeatures`).
- **F1 — memória sem teto em `shadow`/`on` (ALTO).** `event_gate_caches.py:93,96,98`: `base_rows`, `pedigree`, `e2b`
  só crescem (nunca podados; ~10–30 k mints/dia × `GateRow`+`Snapshot` de alguns KB ⇒ dezenas a centenas de MB/dia);
  `Debouncer._last` (`event_gate_runtime.py:76,86`) idem. `EventBook`/`stats` são limitados; esses quatro não.
  Cenário: shadow de 24 h no container de 2+2 conexões e memória modesta ⇒ OOM/restart no meio da medição.
  **Fix:** em `refresh_event_gate_caches`, manter só mints presentes em `rows` ∪ `young_mints`; `Debouncer.forget(mint)`
  em `_unsubscribe_mint`.
- **F2 — queda do WS derruba o worker inteiro (ALTO; contradiz plano §4).** `rpc_ws.py:341` levanta
  `ExchangeUnavailable` após 5 falhas seguidas (≈ 31 s de provedor fora) e `attempt` só zera ao **entregar
  notificação** (`:318`) — com 0 assinaturas (lull, tracked vazio pós-restart) o idle de 60 s (`:56`) conta como
  falha ⇒ crash em ~6 min de silêncio. `_read_loop` (`event_gate.py:63`) não trata; o `TaskGroup` de
  `run_event_gate` (`:116-121`) cancela os irmãos e o `TaskGroup` de `main.py:288` derruba discovery, via rápida,
  Lab, boards, tudo — `restart: always` ⇒ crash-loop a cada ~45 s enquanto o WS estiver fora, com reconexões
  repetidas ao PumpPortal (ban de 1 h, T4.0 §2). Mesma classe: qualquer exceção de banco em `evaluate_mint`
  (`_evaluate_loop`/`_flush_loop`, `event_gate.py:87,95`) mata o processo. **Fix:** `subscribe_slot()` (mantém tráfego
  e dá `rt.slot`), `try/except` em `_read_loop` com backoff próprio e `ws_state=degraded`, `MAX_RECONNECT_FAILURES`
  ilimitado para este cliente, `evaluate_mint` protegido com contador `event_gate_errors`.
- **F6 — uma sessão de banco por avaliação, também em `shadow` (ALTO).** `event_gate_eval.py:154` abre `role_session`
  (SET ROLE + timeout, 2 roundtrips) **antes** de saber se há algo a escrever; pool do meme-worker é 2+2
  (`docker-compose.prod.yml:401-402`), compartilhado por ~15 laços. Debounce = 100 ms/mint ⇒ até 10 aval/s/mint ×
  150 mints; 50–200 aval/s realistas ⇒ fila no pool, `pool_timeout` 30 s ⇒ `TimeoutError` ⇒ F2. Enquanto isso a via
  rápida (`insert_fast_rows`) e o `lab_tick` esperam conexão: **é assim que o evento atrasa a pista de 15 s** (não há
  lock, é o pool e o loop único). **Fix:** abrir sessão só com `drafts` ou `trail` não vazios; em `shadow` nunca.
- **F7 — `shadow` escreve no banco e a trilha flooda (MÉDIO).** `event_gate_eval.py:189-193`: candidato de trilha por
  avaliação (0 ou 1 recusa) ⇒ `write_refusal_trail` também em `shadow`; cap é **por chamada**
  (`lab_trail.py:68`, `cap_trail_rows`), não por minuto ⇒ um quase-passa quente escreve até 10 linhas/s/set em
  `meme_gate_refusals_by_mint`; e a linha com zero recusas ("virou proposta") é gravada para uma proposta que não
  existiu. `test_shadow_mode_counts_and_never_inserts` só conta `meme_proposals`. **Fix:** trilha só em `on` e
  apenas quando `inserted > 0` ou refusal ≠ da última gravada por `(mint, set)` em 60 s.
- Fila `Queue(2000)` + `mark_gap` no drop (`event_gate.py:68-74`): ok. Reconexão: `_resubscribe_all` sequencial
  (300 pedidos × RTT) com `mark_gap` cobrindo o buraco: ok. Provedor: URL derivada de `SOLANA_RPC_URL`
  (`event_gate_config.py:97-105`) ⇒ keyed se o .env tiver chave; sem chave cai no público (WS não documentado, 1
  conexão, 300 assinaturas — limite desconhecido; `ExchangeUnavailable` no subscribe é engolido em
  `event_gate_subscriptions.py:29-30` e re-tentado a cada 5 s, ok). CPU: `evaluate_gate` × ~10 sets + `tape_for`
  sobre ≤ 4000 trades por avaliação no mesmo loop — sem medição; só o pool (F6) já basta para o veto.

## 5. Rollout e veredito

`shadow → on` **não é imposto**: `MEME_EVENT_GATE=on` liga direto (`event_gate_config.py:84-90`). A métrica de
prova prevista (`event_gate_shadow_proposals_total` × `lab_fast_proposals_total`) **não prova nada hoje**:
(a) em `shadow` não há `mark_proposed` (`event_gate_eval.py:168-176`) ⇒ o mesmo mint conta 1 "teria proposto" por
avaliação enquanto passa (5 ev/s × 30 s = 150 contra 1 da pista de 15 s); (b) `event_to_proposal_s_p50/p95` é sempre
`""` porque ninguém chama `subscribe_slot` — `rt.slot` fica `None` (`event_gate_eval.py:60,110`) — o critério de
sucesso do plano §5 (`p50 < 1 s`) é inverificável; (c) o "teria proposto" vive só no log `meme_event_gate_would_propose`
(mint, set, mcap, progresso). **Métrica correta a exigir antes de `on`:** por `(mint, set)` dedupado com TTL,
`shadow_first_seen_at` × `proposed_at` da proposta de 15 s do mesmo mint (Δ negativo = ganhou tempo; mint sem par de
15 s = F3/F4/F5 abrindo porta nova — tem de ser 0), mais `p95` medido com slot.

| Commit | Veredito | Condições |
|---|---|---|
| `88e2b4f7` T4.52b-2 | **SAFE_TO_DEPLOY(off)** | puro, `max_recent_drawdown_pct` off por padrão, `unknown` fecha; 131 testes de porta intactos; único residual: janela do set ignorada pela pista de evento (F-drawdown acima) |
| `549b1ac1` T4.52b-3 | **SAFE_TO_DEPLOY(off)** · **BLOCK(shadow)** · **BLOCK(on)** | shadow só depois de F1, F2, F6, F7 + slot; `on` só depois de F3, F4, F5 e da corrida do §2, com a métrica dedupada do §5 |

Fixes por linha: F1 `event_gate_caches.py:93-98` + `event_gate_runtime.py:76,86`; F2 `rpc_ws.py:59,318,341` +
`event_gate.py:63,87,95` + `event_gate_subscriptions.py` (`subscribe_slot`); F3 `event_gate_rows.py:136`;
F4 `lab_repo_fast.py:_FAST_ROWS` ou `event_gate_rows.py:124`; F5 `event_gate_rows.py:107-139`; F6/F7
`event_gate_eval.py:154,189-193`; corrida `lab_fast.py:125-130` + `event_gate_eval.py:168-176`.

## Re-revisão 9d3c72a1

**Data:** 2026-09-18 · somente leitura; nada editado, VPS/.env intocados. Comandos (saída real):
`uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_rpc_ws.py services/meme-worker/tests/test_proposal_race.py services/meme-worker/tests/test_event_gate_pure.py -q` → `39 passed in 1.85s`;
`uv run pytest services/meme-worker/tests/test_event_gate_integration.py services/meme-worker/tests/test_lab_fast.py -q` → `1 failed, 14 passed in 94.42s` (falha só quando os dois arquivos rodam juntos: `test_a_15s_row_becomes_a_proposal_filled…` vê um `meme_lab_bet_opened` para um mint `EVT_*` deixado pela integração do portão — vazamento entre testes no banco compartilhado, não bug de produto); `test_lab_fast.py` sozinho → `7 passed in 71.38s`.

| Item | Estado | Evidência |
|---|---|---|
| F1 memória | **FIXED** | `event_gate_caches.py:138-163` (`prune_event_gate_caches`: fora de `keep` ∪ > 600 s, teto `2×max_mints`), chamado em `event_gate_subscriptions.py:80-81`; `Debouncer.forget/prune` `event_gate_runtime.py:91-103`; `_unsubscribe_mint` limpa `reserves`/`pending_trail`/`trail_last_written` (`:47-51`); `proposed_until`/`shadow_marked_until` podados por TTL (`caches.py:103-107`); tamanhos no heartbeat `event_gate.py:150-155`. |
| F2 WS | **FIXED (2 residuais BAIXOS)** | (a) `rpc_ws.py:270-344`: `listen()` só sai por `CancelledError` — connect em `try/except Exception` + `_backoff` que nunca levanta (`:263-268`, teto 30 s), leitura idem (`:322-327`), `_close_quietly` engole (`:346-350`); `MAX_RECONNECT_FAILURES` removido; `attempt=0` ao conectar (`:296`). O corpo do `async for` em `event_gate.py:82-94` só pode levantar em `handle_reconnect` (`event_gate_eval.py:313`, sessão de banco num reconnect) — cai em (c). (b) `rpc_ws.py:306`: `timeout=None` com `_specs` vazio; `test_idle_timeout_is_skipped_with_zero_subscriptions` (`:247`) passa; após o `slotSubscribe` (`event_gate.py:129-140`) há sempre 1 assinatura com frames a cada ~0,4 s. (c) `main.py:290` roda `run_event_gate_forever` (`event_gate.py:187-195`): `except Exception` pega o `ExceptionGroup` do `TaskGroup` interno, dorme 5 s e reinicia; `CancelledError` re-levantada — o `TaskGroup` de `main.py:223` nunca vê a exceção. `test_connect_retries_forever_across_repeated_refusals` passa. **Residual 1 (BAIXO):** `event_gate.py:82` — se o corpo do `async for` levantar (só `handle_reconnect` com banco fora), o gerador `listen()` fica suspenso no `yield` sem `aclose()`; o finalizador de asyncgen roda o `finally` (`rpc_ws.py:328-341`) concorrente com o novo `listen()` do reinício e pode fazer `self._connection=None`/`_connected.clear()` depois de a conexão nova já estar conectada ⇒ frames chegam (a leitura usa o `connection` local) mas todo `subscribe_*`/`unsubscribe` falha ("no live connection"/timeout) até a próxima queda real do WS; assinatura no heartbeat: `ws_state=disconnected` com `events_60s>0`. Fix: `try/except Exception` + `logger.warning` em volta do corpo do `async for` e `finally: await aiter.aclose()`. **Residual 2 (BAIXO):** reinício do portão não chama `mark_gap` (`listen()` novo começa com `first=True`, `reconnects` não incrementa) ⇒ janelas em memória atravessam o buraco de ≥ 5 s sem invalidação (drawdown/rising um pouco mais permissivos logo após um crash). |
| F3 creator_sold | **FIXED** | `event_gate_rows.py:142-150`: `True if base.creator_sold else …` — base `True` vence sempre e nunca é sobrescrita; `False` só sobe para `True`; `None` usa a regra da pista (`covered_from_birth`→`False`, senão `None`), exatamente o fix pedido. |
| F4 top10 | **FIXED** | `event_gate_rows.py:129-130`: literalmente `base.top10_share`/`base.top10_reason` (hoje `None` ⇒ `top10_unknown`, igual à pista de 15 s). |
| F5 curva completa | **FIXED** | `event_gate_rows.py:117`: `completed_at=base.completed_at or (as_of if state.complete else None)`. |
| F6 sessão | **FIXED** | `grep role_session` no caminho de evento: só `event_gate_eval.py:215` (`flush_pending_trail`, só com `due` não vazio — em `shadow` `pending_trail` nunca é populado, `:264` retorna antes de `:267`), `:271` (`evaluate_mint`, só em `on` e só após `to_insert` não vazio, `:268-269`) e `:313` (`handle_reconnect`, 1 por reconexão, também em `shadow` — não é por avaliação). `shadow` sai em `:264` sem tocar o banco. |
| F7 trilha | **FIXED** | `shadow`: `:256-258` `continue` antes de `_trail_row`; `on`: candidatos vão para `rt.pending_trail[mint]` (`:267`, último vence) e são escritos ≤ 1×/mint/60 s (`:190-197`, `TRAIL_COOLDOWN_S=60`) na sessão do insert (`:283`) ou pelo `_trail_flush_loop` de 15 s (`event_gate.py:117-126`). |
| Corrida | **PARTIAL** | Reserva-antes-do-insert existe nas duas pistas com liberação em 0 inseridos (`proposal_race.py:46-53`; `lab_fast.py:130`; `event_gate_eval.py:274`). Mas a reserva não está no mesmo trecho síncrono da leitura do guarda: na pista de evento o guarda é lido em `event_gate_eval.py:246` e a marca só acontece dentro de `insert_proposals_reserved` (`:274`), depois do `await` de `async with role_session` (`:271`). Cenário: evento passa no set S para o mint M e suspende em `:271` esperando conexão do pool (2+2, a via rápida segura uma); o tique de 15 s volta do `await open_mints_for` (`lab_fast.py:104`), lê `recently_proposed_mints` (`:106`, M ausente), avalia, marca e insere (`features_end_time` = fim do balde); o evento retoma, marca por cima e insere com `features_end_time=as_of` ⇒ índice único não bloqueia ⇒ duas linhas `proposed` para (M, S) — o cenário do §2 (recompra em < 60 s após saída da posição 1). Na pista de 15 s o mesmo buraco existe a partir do 2º rascunho do lote (`proposal_race.py:48-49`: a marca do rascunho N vem depois do `await insert` do N−1). Fix (3 linhas): em `evaluate_mint`, `caches.mark_proposed` para cada `(spec, draft)` antes de `:271` (e `insert_proposals_reserved` só desmarca em 0 inseridos); em `lab_fast`, marcar todos os rascunhos antes do primeiro `await`. `test_proposal_race.py` não exercita a intercalação com o `role_session`. |
| Métricas | **PARTIAL** | `rt.slot` agora é alimentado (`event_gate.py:129-140` + `event_gate_eval.py:126`) e `shadow_proposals_total` dedupa por `(mint, set)` (`:175-177`). Porém `event_to_proposal_s_p50/p95` só é registrado em `on` (`:278-281`, dentro do `if inserted`) — em `shadow` continua `""`, logo o critério `p50 < 1 s` segue inverificável em sombra. `shadow_agree_mints` (`:168-170`) conta qualquer avaliação de mint já proposto pela pista de 15 s, mesmo que o evento o recusasse (`already_open` já esvazia `drafts`) ⇒ "concordância" inflada; `shadow_only_event_mints` mistura "evento chegou antes" (bom) com "porta nova" (residual F3/F4/F5) — o mesmo mint entra em `only` e, quando a pista de 15 s o propõe, em `agree`. Falta a versão por mint (`would_propose` × `proposed_at` da 15 s) que o §5 pedia. |

**Veredito:** **SAFE_FOR_SHADOW = sim** (F1/F2/F6/F7 fechados; `shadow` não abre sessão por avaliação, não escreve, memória com teto; residuais de F2 só degradam o próprio portão). **SAFE_FOR_ON = não** — corrida do §2 ainda aberta na pista de evento (marca depois do `await role_session`) e latência não observável em sombra. Antes de `on`, além do fix da corrida, Everton deve ver em ≥ 1 h de sombra no pico: `event_gate_ws_state=connected` com `reconnects ≤ 2/h` e `dropped=0`; `cache_base_rows ≤ 2×max_mints` estável; `no_base_row_60s / evaluations < 10 %`; `shadow_only_event_mints ≤ shadow_agree_mints` na janela; e, offline, para cada mint distinto do log `meme_event_gate_would_propose`, uma linha em `meme_proposals` da pista de 15 s para o mesmo set com `proposed_at` ≤ 60 s depois — cobertura ≥ 90 % e os restantes explicados um a um (0 "portas novas"). `event_to_proposal_s_p50` só existirá em `on`: registrar a latência também em `_record_shadow` para poder exigir `p50 < 1 s` antes de ligar.
