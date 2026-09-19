# T4.67b — Perfil de lançamento no executor real (EXP-M18)

**Data:** 19/09/2026. **Não commitado.** Nenhuma transação real enviada; tudo com fakes/fixtures gravadas.
Contrato: `docs/RISK_ENGINE_MEME.md` §18 "Perfil de lançamento"; operação: `docs/ACTIVATION.md` 9h.
Vault: `obsidian/05-EXPERIMENTS/EXP-M18-sniper-de-lancamento.md` (não tocado).

## O que existe (flag `MEME_LAUNCH_LANE=off|paper|on`, a mesma do radar; o executor age só em `on` + flag de real)

### Motor puro (`packages/risk-core/hunter_risk_meme`)
- `decision.py`: `CheckState.SKIPPED` (quarto estado; `passed` ⇒ `passed|skipped`; um `skipped` exige motivo e nunca
  carrega recusa), `skipped(name, reason)`, `MemeDecision.profile ∈ {full, launch}` (default `full`).
- `profile.py` (novo): `MemeLaunchProfile` (`ticket_sol`, `max_open`, `max_participation_pct`, `max_token_age_s`),
  `LAUNCH_SKIPPED_CHECKS` (10 `creator_behaviour`, 11 `bundled_share`, 12 `top10_share`, 26 `conviction`, cada um com
  o porquê), `LAUNCH_RELAXED_CHECKS` (7 `state_freshness` = `processed` aceito; 8 `token_age` sem mínimo, máximo da
  pista; 9 `curve_progress` sem mínimo; 21 `participation` = SOL real da curva, teto da pista; 23 `sizing` piso segue o
  bilhete), check 27 `launch_open_cap` / `launch_max_open_reached` (só `lane = launch`), `launch_floor`.
- `checks.py`: overrides por kwarg (`min_commitment`, `window_s`, `min_pct`, `note`); `coin_checks(..., launch=)`;
  `REFUSAL_NAMES` += `launch_max_open_reached`. `sizing.py`: teto `launch_ticket` em `CAP_ORDER` logo após
  `requested`; participação com o teto da pista; piso `launch_floor`. `evaluate.py`: `evaluate_meme_entry(..., launch=)`
  — com `launch` o check 26 é `skipped`, o 27 é acrescentado, `conviction` ignorada, `profile = "launch"`.
- `exits.py`: motivo `third_party_sell` (precedência logo depois de `creator_dump`), `decide_exit(..., third_party_sell=)`.
  `time_stop_s` já era **segundos** (`max_hold_s` também) — confirmado por teste (6 s dispara aos 6,0 s, não aos 5,9 s).
- `inputs.py`: `OpenMemePosition.lane`, `PendingMemeIntent.lane`.

### Núcleo (`packages/core`)
- `submit_types.SubmitPolicy.skip_simulation` (default `False`); `submit._attempt` pula o `simulateTransaction` só com
  ela ligada — o preflight do nó continua (`skipPreflight: false`).

### Executor (`services/meme-executor/hunter_meme_executor`)
- `launch_config.py` (novo): `LaunchConfig.from_env` — `MEME_LAUNCH_LANE`, `MEME_LAUNCH_MAX_OPEN` (2),
  `MEME_LAUNCH_TICKET_SOL` (0,01, `ticket(limits)` nunca acima de `max_sol_per_trade`),
  `MEME_LAUNCH_PRIORITY_FLOOR_MICRO_LAMPORTS` (1 000 000), `MEME_LAUNCH_BUY_SLIPPAGE_PCT` (10, teto 20),
  `MEME_LAUNCH_SKIP_SIMULATION` (false), `MEME_LAUNCH_MAX_PARTICIPATION_PCT` (0,10), `MEME_LAUNCH_MAX_AGE_S` (5).
  Constantes `BLOCKHASH_REFRESH_S = 5`, `LAUNCH_EXIT_TICK_S = 2`, `LAUNCH_RULE_SET_NAME = launch_v0`,
  `LAUNCH_SERIES = meme_launch_lane_v1`. Valor ilegível/fora da faixa ⇒ padrão com aviso, nunca recusa o boot.
- `launch_repo.py` (novo): `launch_candidates` (JOIN `meme_rule_sets` por **nome** `launch_v0`, `origin = rules`,
  `mode = paper`, sem ordem de compra, janela de 60 s; filtro em Python por `reasons[0].series`),
  `claim_launch_proposal` (`UPDATE … SET mode='live', decision ||= {launch_lane: {claimed_at, by}} WHERE mode='paper'`),
  `created_at_of` (`reasons[0].created_at` › `quote.created_at` › `features_end_time` — é onde a T4.67a carimba o
  `create`), `buy_submitted_at`.
- `launch_admission.py` (novo, puro): `launch_context` (idade com proveniência; denominador `meme_tokens` ›
  `reasons[0].initial_real_token_reserves` › `Global` só em curva padrão não-Mayhem; volume = `real_sol_reserves`;
  `extras` com `skipped_checks`/`skipped_reads`/`quote_commitment`/fontes), `launch_proposal` (pedido = `size_sol` do
  conjunto ou o bilhete, sempre `live`), `launch_position_params` (`lane`, `time_stop_s`, `max_hold_s`,
  `max_drawdown_from_peak_pct`, `trailing_pct`, `exit_on_first_third_party_sell`, `creator` da conta da curva,
  `creation_slot`, `known_buyers`; padrões 6 / 20 / true).
- `launch_send.py` (novo): `BlockhashCache` (fresco < 5 s, `usable` < 30 s, `for_signing` busca na hora e conta quando
  inutilizável, falha mantém o anterior), `launch_priority_fee` (puro: `min(max(escolha T4.55, piso), teto)` com a fonte
  nomeada `launch_floor`/`cap`), `launch_submit_policy` (poll 0,5 s, `skip_simulation`).
- `launch_entries.py` (novo): `launch_entries_once` (inerte fora de `on`+live: nenhuma consulta; renova o blockhash;
  relê o kill switch; uma passada por candidata) e `handle_launch_candidate`: `launch_proposal_stale` antes de qualquer
  RPC; `program_upgraded`/`kill_switch_blocked` antes das leituras; `gather(curva processed, saldo, taxa)` + `Global`
  em cache; posições/pendentes/participação numa sessão, `token_context` noutra (opcional); `ensure_anchor` (T4.60);
  `admit_launch`; latch em `daily_loss_cap_reached`; `admission["launch"] = extras + config`; claim + ordem
  (`admitted` ou `refused`) na **mesma transação** (claim perdido ⇒ nada escrito, `launch_claim_lost_total`); releitura
  do kill switch antes de assinar (`kill_switch_blocked_before_signing`); `build_buy` com blockhash do cache, taxa
  elevada, tolerância 10 %; `MemeSubmitter` com a política do lançamento; `proposal_to_submit_ms` do `submitted_at`
  real; posição com `launch_position_params`; `event_exits_wake.set()`.
- `launch_exits.py` (novo): tique de 2 s só para `lane = launch`, pela mesma `manage_position` (mesma trava).
- `launch_stats.py` (novo): `LaunchStats` + `launch_heartbeat_fields` (`launch_lane_mode`, `launch_open`,
  `launch_seen_total`, `launch_buys_total`, `launch_sells_total`, `launch_claim_lost_total`,
  `proposal_to_submit_ms_p50/p95`, `launch_refusals` JSON, `launch_config`, `launch_blockhash_*`).
- Tocados: `admission.py` (`admit_launch`, `wallet_from` com `lane`, `curve_from` usa o commitment da leitura),
  `chain.py` (`curve(mint, commitment=)`, `CurveRead.commitment`), `repo.py` (`PendingAttempt.lane` do `intent`),
  `config.py` (`ExecutorConfig.launch`), `context.py` (`ExecutorContext.launch`), `heartbeat.py`, `main.py` (tarefas
  `meme-launch-entries` e `meme-launch-exits` só em `on`+live; blockhash no tique do kill switch),
  `exit_common.py` (`exit_params` aceita `time_stop_s`/`max_drawdown_from_peak_pct`; `is_launch_position`),
  `exit_settle.py` (`launch_sells_total`), `event_exits_runtime.py` (`Watched.launch/third_party_rule/
  third_party_sell_seen/known_buyers/creation_slot`), `event_exits_watch.py` (`launch_watch_fields`: criador dos
  `params` quando `meme_tokens` não tem a linha), `event_exits_eval.py` (`note_third_party_sells`, puro;
  `third_party_sell=` no `_decide`), `event_exits_stats.py` (`event_exits_third_party_sells_seen`).
- Docs: `docs/RISK_ENGINE_MEME.md` §18; `docs/ACTIVATION.md` 9h; `.env.example`; `infra/vps/docker-compose.prod.yml`
  (serviço `meme-executor`).

## Decisões desta sessão (para o guardião de risco)

1. **`skipped` é um estado, não um `passed` com nota.** A tabela da §4 continua com os 26 nomes na mesma ordem (+27);
   a linha diz "não medido por desenho". Nenhum consumidor externo do `CheckState` foi encontrado (grep na API/web).
2. **A proposta é reclamada (`mode = 'live'`) na mesma transação da ordem.** O laço normal (`live_candidates`) lê
   `mode = 'live'` sem ordem de compra — nunca vê um lançamento reclamado sem a ordem, então não há dupla admissão.
   `decided_by` fica `rules` (a `_REJECT` do estágio 1 não toca nela). Uma recusa também reclama (evidência + a linha
   deixa de ser relida).
3. **Participação a 10 % (variável nova).** O 1 % do perfil exigiria 1 SOL na curva no primeiro segundo — a pista
   nunca compraria e a inércia seria silenciosa. `MEME_LAUNCH_MAX_PARTICIPATION_PCT=0.10` é um número inventado
   aqui, documentado como do dono; `launch_refusals.participation_above_cap` mede se ele morde.
4. **Piso segue o bilhete.** Com `MEME_MIN_TRADE_SOL` = 0,02 e bilhete 0,01 o check 23 recusaria tudo; no perfil o
   piso é `min(piso, bilhete)`. O custo fixo (~0,003 SOL ≈ 29 % do bilhete) fica em `sizing.fixed_costs_sol`; a
   EXP-M18 não contou o rent da ATA — `MEME_CLOSE_ATA_ON_FULL_SELL=1` recupera 0,002 na venda cheia.
5. **Cota `processed`, fill `confirmed`.** Só o perfil de lançamento aceita `processed` na admissão (`curve_from`
   passa o commitment real da leitura; o perfil completo recusa `commitment_too_weak`, provado). O fill continua sendo
   o `TradeEvent` da transação confirmada.
6. **Idade pelo carimbo da proposta.** A T4.67a escreve o instante do `create` em `features_end_time` (não em
   `reasons[0].created_at`); o executor lê os dois, depois `meme_tokens.created_at`, e por último `proposed_at`
   rotulado `lower_bound_on_age`. `launch_proposal_stale` por `proposed_at` corta antes de qualquer RPC.
7. **"Terceiro" = nem criador, nem esta carteira, nem `known_buyers`.** A T4.67a não escreve `creation_slot`/
   `known_buyers` hoje; sem eles, **toda** venda que não é do criador nem nossa dispara — o lado conservador. Buys
   vistos em slot ≤ `creation_slot` entram em `known_buyers` quando o slot existir.
8. **Sem novo teto de slippage de saída.** `third_party_sell`/`trailing`/`time_stop` usam os 5 % normais;
   `creator_dump` os 15 %. Uma venda de lançamento que morra por `6003` em curva derretendo aparecerá em
   `event_exits_sell_errors`/`blocked_exits` — se acontecer, é um número para o dono, não um padrão meu.
9. **Skip da simulação é opt-in e documentado com o risco** (assinatura gasta no journal; taxa paga se pousar com erro).

## Comandos rodados (saída real)

- `timeout 590 uv run pytest packages/risk-core/tests -q -p no:cacheprovider -m "not live"` → **428 passed in 8.46s**
  (394 antes; +34: `test_launch_profile.py` 28, `test_exits.py` +3, tabela +1, …)
- `timeout 590 uv run pytest services/meme-executor/tests -q -p no:cacheprovider -m "not live and not integration"`
  → **443 passed, 51 deselected in 6.41s** (402 antes; +41: `test_launch_config.py` 5, `test_launch_send.py` 5,
  `test_launch_admission.py` 8, `test_launch_entries.py` 11, `test_event_exits_launch.py` 12)
- `timeout 590 uv run pytest services/meme-executor/tests -q -p no:cacheprovider -m "integration and not live"`
  → **51 passed, 443 deselected in 176.16s** (47 antes; +4 em `test_launch_integration.py`, Postgres real)
- `timeout 590 uv run pytest packages/core/tests/unit/execution/meme -q -p no:cacheprovider` → **85 passed**
  (+3 `test_meme_submit_skip_simulation.py`)
- `uv run ruff check services/meme-executor packages/risk-core packages/core` → All checks passed!
- `uv run ruff format --check …` → 414 files already formatted; o único "would be reformatted" é
  `packages/core/tests/integration/test_migration_0053.py` (T4.67a, não meu)
- `uv run pyright services/meme-executor packages/risk-core packages/core/hunter_core/execution/meme …` → 0 errors
  (o erro pré-existente em `packages/core/tests/unit/execution/meme/test_meme_submit.py:281` não é desta tarefa)
- `uv run python infra/scripts/check_file_size.py` → scanned 1000 files; 0 over budget (`checks.py` 347,
  `launch_entries.py` 335)

## Pendências / ressalvas

- **Não medido em produção.** `proposal_to_submit_ms_p50` é o número que decide se a EXP-M18 está sendo testada de
  verdade; acima de ~1 000 ms a mesa compra a +2–3 s (KB-0136: 1,01×).
- A T4.67a ainda estava sendo escrita ao lado (`0053`, `launch_lane_*.py` do worker, `docs/RISK_ENGINE_MEME.md` §9,
  `.env.example`, compose). Meu §18 foi **anexado** ao fim do doc e as variáveis inseridas **depois** do bloco dela;
  se o outro agente reescrever esses arquivos por inteiro, conferir.
- `launch_max_open_reached` conta intenções pendentes pelo `intent.lane` — uma ordem `admitted` que morra antes do
  `record_send_result` continua contando até virar `refused`/`failed` (mesmo comportamento das reservas da §9.5).
- `test_event_exits.py` continua com 785+ linhas (isenta do gate); `test_launch_integration.py` reutiliza o
  `t452b` mint (`HMfRWjo6…`) porque `meme_tokens` não permite `DELETE` sem `app.meme_retention` — a asserção
  `count(*) = 0` protege a premissa "moeda sem linha".
- Arquivos de outros trabalhos já modificados na árvore e **não** tocados aqui: `.claude/launch.json`,
  `.claude/state/notes-T4.31-explain.txt`, `docs/DESIGN.md`, `docs/DATABASE.md`,
  `packages/core/tests/unit/test_settings.py`, `packages/core/hunter_core/db/models/meme_bets.py`,
  `packages/core/tests/integration/test_migrations.py`, `packages/indicators/**`, `services/meme-worker/**`,
  `infra/migrations/**0053*`.
