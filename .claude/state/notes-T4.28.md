# Notas T4.28 — "liga sozinho no estágio 1": o executor abre a proposta da mesa sem clique, dentro do escopo pequeno

Execução: 2026-09-16, 01:2x–02:0x BRT (04:2x–05:0x UTC). Papel: risk-engine guardian.
Brief: `.claude/state/brief-T4.28-liga-sozinho-no-estagio-1.md`. Sem commit. Nenhum `.env*` lido ou escrito. Nenhuma
chave real (só chaves de teste geradas em memória, RNG semeado). **Nenhum `sendTransaction` em rede nenhuma** (os testes
usam o `FakeRpc` do executor; o caso "sem envio" roda com `allow_send=False`). Nem `ENABLE_MEME_LIVE_TRADING` nem
`MEME_LIVE_AUTO_APPROVE` aparecem ligadas em arquivo rastreado (os testes usam `"1"` em dicts de ambiente).
Nenhuma migração: `hunter_worker` já tem `SELECT/INSERT/UPDATE` inteiro em `meme_proposals` desde a `0022`
(`ddl/meme_lab.py::MEME_LAB_WORKER_UPSERT_TABLES`) e `decided_by` é texto livre — conferido antes de codar.

## 1. Leitura (o que o código tinha ao começar)

- `repo._CANDIDATES` só consome `mode = 'live' AND status IN ('approved','filled','unfilled')`; nada nascia assim sem o
  clique. A mesa nasce `proposed`/`paper` sob o conjunto `operator` ativo (`operator/5` na `0039`; a API lê por
  **nome + status**, `OPERATOR_RULE_SET` é documental e ainda diz `("operator", "4")` no disco — não toquei).
- A lógica do clique vivia só na API (`services/meme_desk.py::_decide` + `meme_desk_common.enforce_*` +
  `repositories/meme_desk.py::decide_proposal` com SQLAlchemy Core). O escopo pequeno só tinha o contador de trades
  (`count_live_buys`); `max_total_sol` só entrava como `min` no `wallet_max_sol`.
- `kind` é coluna de `meme_rule_sets`, não de `meme_proposals` — a consulta do robô faz o `JOIN`.

## 2. Desenho (registrado antes de codar)

1. **Regra compartilhada, não copiada:** `packages/core/hunter_core/execution/meme/approval.py` (novo, 178 l.) — as
   regras puras do clique (`proposal_state_refusal` → `not_proposed`/`expired`; `size_cap_refusal` →
   `exceeds_max_sol_per_bet`; `live_mode_refusal` → `meme_live_disabled`; `max_sol_per_bet_of`) e **a** escrita
   (`DECIDE_PROPOSAL`: `UPDATE meme_proposals … WHERE id = :id AND status = 'proposed'`, `ProposalDecision`,
   `decide_proposal`). A API passou a chamar as três regras e a executar a mesma statement
   (`repositories/meme_desk.decide_proposal` virou wrapper); `apps/api/tests/unit -k meme` continua em **122 passed**
   (os fakes das use cases não mudaram).
2. **Executor:** `auto_approve.py` (novo, 315 l.) — `plan_auto_approvals` **puro** (skips nomeados: `expired`, `too_old`,
   `mint_busy`, `suggested_incomplete`, `exceeds_max_sol_per_bet`, `hourly_cap`, `tick_cap`, `mint_repeated`),
   `auto_decision` (`decision = suggested + note`, `decided_by = executor:auto_stage1`, `mode = live`),
   `auto_approve_once` (uma por tique; lê candidatas → escopo → aprovadas na última hora → mints ocupados; kill switch
   bloqueando / programa divergente / escopo esgotado ⇒ passe vazio **antes** de abrir qualquer proposta), `reject_if_auto`
   (chamado por `entries._refuse` **e** pelo ramo `kill_switch_blocked_before_signing`, na mesma transação da ordem
   `refused`; guardado por `status = 'approved' AND mode = 'live' AND decided_by = robô` — proposta já preenchida em sombra
   pelo laço de papel não é tocada, o CHECK `filled ⇔ bet_id` fica intacto). `scope.py` (novo, 129 l.) — `ScopeUse`
   (`max_trades`/`max_total_sol` contra o ledger: `fill.buy_total_lamports` do confirmado, `intent.max_sol_cost_sol` do
   em voo; `exhausted`, `remaining_sol`, `requested_cap_sol`) e `requested_sol_of` (parse seguro: linha ruim ⇒ 0 ⇒
   `below_min_sol`, nunca crash do laço). `entries.py`: `auto_approve_once` antes de `live_candidates` (a proposta aberta é
   candidata **do mesmo tique**), o bloco do escopo troca `count_live_buys` por `read_scope_use`, o pedido é clampado
   (`proposal_from(requested_cap_sol=…)`) e `admission.small_test` grava o uso. `config.py`: `ENV_AUTO_APPROVE`,
   `auto_approve` (só com `mode.live`), `auto_approve_max_per_hour`, `small_test_max_total_sol`;
   `auto_approve_needs_small_test` **antes** de `boot_meme_execution` (a chave não é lida). `heartbeat.py`:
   `auto_approve`, `auto_approve_max_per_hour`, `auto_approved_1h`, `auto_refused_1h` (por motivo, das linhas),
   `auto_skipped` (por motivo), `auto_rejected_total`, `small_test_used_sol`, `small_test_trades_done`,
   `small_test_remaining_sol`, `small_test_exhausted`. `main.py`: log de boot e `status_details["auto_approve"]`.
3. **Por que pré-filtrar `mint_busy`/kill switch/escopo em vez de deixar a admissão recusar:** uma proposta aberta pelo
   robô e recusada vira `rejected` (regra (d) do brief) — some da mão do humano. Abrir o que a admissão certamente
   recusaria só queimaria a proposta e o teto por hora; deixá-la `proposed` é o comportamento honesto.
4. **Clamp em vez de recusa no `max_total_sol`:** "o teto é teto" — a última compra do escopo é admitida pelo que sobra
   (`requested_clamped = true` em `admission.small_test`), nunca acima; atingido ⇒ `small_test_scope_exhausted` com
   `exhausted = max_total_sol`. O `max_trades` continua contando compras enviadas (`submitted_unconfirmed` + `confirmed`).

## 2b. Achado bloqueante (pré-existente, T4.14) — corrigido aqui

`repo._FEATURES` selecionava `bundled_share` de `meme_features_1m`, coluna que **não existe** nessa tabela (só em
`meme_risk_snapshots`, `0023`, o `GET /in-memory-coin`). Todos os testes de persistência monkeypatchavam `token_context`,
então nunca apareceu. **Cenário de falha:** primeira candidata live na VPS → `token_context` levanta
`asyncpg UndefinedColumnError` → `handle_candidate` não captura → `forever("entries")` re-levanta → o `TaskGroup` derruba
o processo; com o estágio 1 ligado, cada boot abriria uma proposta (`approved/live`) e morreria em seguida — 5 propostas
queimadas por hora sem uma compra e sem uma linha `refused`. Provado sem fake em
`test_token_context_reads_the_real_schema_and_the_bundled_share_from_the_risk_read` (saída antes da correção:
`asyncpg.exceptions.UndefinedColumnError: column "bundled_share" does not exist`). Correção em `repo.py`: `_FEATURES` sem a
coluna; `_RISK` lê o `bundled_share` mais novo de `meme_risk_snapshots` dentro de `RISK_SNAPSHOT_MAX_AGE_S = 600` (2× o
`risk_min_interval_s` do leitor); ausente ou mais velho ⇒ `None` ⇒ `bundled_share_unmeasurable` (§8). Consequência
declarada: o leitor de risco só lê mints com aposta de papel aberta ou no board `graduating` — uma proposta nova
normalmente **não** terá `bundled_share` a tempo, e a admissão recusa por nome. É a doutrina, não um defeito novo.

## 3. Comandos e saídas (primeiro plano, `timeout 290`/`590`)

```
uv run pytest packages/core/tests/unit/execution/meme/test_meme_approval.py -q      -> 18 passed
uv run pytest services/meme-executor/tests -q -m "not live and not integration"     -> 48 passed, 17 deselected
   (test_auto_approve.py 18: planner 10, escopo 4, boot 4; test_config_boot 9; demais 21 — antes: 30)
uv run pytest services/meme-executor/tests/test_live_persistence.py -q (testcontainer) -> 17 passed in 69.50s
   (+ test_token_context_reads_the_real_schema…, §2b; test_stage_1_* 6 novos: abre→admite→compra em um tique + idempotente + heartbeat; recusa da admissão ⇒ ordem
    refused + proposta rejected com auto_refusal; >60 s fica proposed e executor sem flag não toca; teto de SOL fecha a
    torneira (robô pula, clique recusado small_test_scope_exhausted/max_total_sol); última compra clampada ao que sobra;
    allow_send=False: abre, admite, simula, failed:meme_live_disabled, rpc.sent == [], sem posição)
uv run pytest apps/api/tests/unit -q -k meme                                        -> 122 passed, 602 deselected
uv run pytest apps/api/tests/unit -q                                                -> 724 passed
uv run pytest packages/core/tests/unit -q                                           -> 1350 passed
uv run pytest packages/risk-core/tests/unit/meme -q                                 -> 92 passed
uv run ruff check / ruff format --check (arquivos tocados)                          -> All checks passed! / 32 files already formatted
uv run pyright services/meme-executor packages/core/hunter_core/execution/meme/approval.py apps/api/.../meme_desk*.py
   apps/api/hunter_api/repositories/meme_desk.py packages/core/tests/unit/execution/meme/test_meme_approval.py
                                                                                    -> 0 errors, 0 warnings, 0 informations
uv run python infra/scripts/check_file_size.py                                      -> scanned 878 files; 0 over budget
bash infra/scripts/forbidden_patterns.sh --self-test                                -> self-test: all patterns detected, clean/exempt fixtures pass
   (padrão novo: MEME_LIVE_AUTO_APPROVE ligada, formas shell e YAML; a substituição `${…:-false}` dos composes não dispara)
```

Nota: a varredura completa do `forbidden_patterns.sh` (self-test + caminhos) passou de 300 s e o harness a moveu para
segundo plano sozinha; terminou com exit 0. Os `print(` que ela lista em `meme_desk*.py` são o `fingerprint(` pré-existente.

## 4. Arquivos

Novos: `packages/core/hunter_core/execution/meme/approval.py`, `packages/core/tests/unit/execution/meme/test_meme_approval.py`,
`services/meme-executor/hunter_meme_executor/{auto_approve,scope}.py`, `services/meme-executor/tests/test_auto_approve.py`,
`.claude/state/notes-T4.28.md`.
Modificados: `services/meme-executor/hunter_meme_executor/{config,context,entries,admission,heartbeat,main,repo}.py`,
`services/meme-executor/tests/test_live_persistence.py` (+6 testes, harness com `auto`/`allow_send`, plantio de proposta
`operator`), `services/meme-executor/README.md`, `apps/api/hunter_api/services/{meme_desk,meme_desk_common}.py`,
`apps/api/hunter_api/repositories/meme_desk.py`, `infra/docker/docker-compose.yml`, `infra/vps/docker-compose.prod.yml`
(as duas variáveis, default `false`/`5`), `infra/scripts/forbidden_patterns.sh`, `docs/{ACTIVATION,RISK_ENGINE_MEME,
DEPLOYMENT,DATABASE}.md` (§9b item 9 + item 4; §3.5 novo + §12; §3.7; §40.1),
`obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md` (seção "Estágio 1 — sozinho (16/09)").
Não tocados: `apps/web/**` (T4.28b), `services/meme-worker/**`, `infra/migrations/**`, `.env*`.

## 5. O que fica com o Everton

`.env` da VPS: `ENABLE_MEME_LIVE_TRADING` (ligada), `SOLANA_WALLET_SECRET_KEY`, `SOLANA_RPC_URL`, `MEME_WALLET_MAX_SOL=0.30`,
`MEME_MAX_SOL_PER_TRADE=0.05`, `MEME_DAILY_LOSS_CAP_SOL=0.15`, `MEME_MAX_OPEN_POSITIONS=2`, `MEME_COOLDOWN_S=60`,
`MEME_GATES_FILE=/run/hunter/meme_gates.json`, `MEME_LIVE_AUTO_APPROVE` (ligada; opcional
`MEME_LIVE_AUTO_APPROVE_MAX_PER_HOUR`, padrão 5). `meme_gates.json` com `small_test_authorization.expires_at` e
`valid_until` ≥ 2026-09-18 (escopo 0,05 / 0,25 / 5). Carteira ≤ 0,30 SOL.
Orquestrador: `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update`; prova em duas leituras de
`hb:meme:executor` (`auto_approve=true`, `small_test_*`, `auto_skipped`); primeira ordem real observada de ponta a ponta.

## 6. Concerns

1. **A rejeição automática tira a proposta do humano.** Por desenho (brief (d)); mitigado pelos pré-filtros
   (`mint_busy`, kill switch, programa, escopo). Recusas que dependem da cadeia/radar (`bundled_share_unmeasurable`,
   `volume_unavailable`, `curve_state_stale`…) ainda rejeitam — hoje o radar não mede `bundled_share`, então **toda**
   proposta aberta pelo robô será recusada `bundled_share_unmeasurable` (T4.14 concern 8) e o teto de 5/h será consumido
   por rejeições. Não é defeito deste módulo; é a doutrina "insumo ausente não vira zero". O painel mostra o motivo.
2. `cancel` do operador não alcança uma proposta aberta pelo robô: o laço de papel aplica o comando no próximo snapshot
   (≤ 15 s) e o executor compra em ~1–2 s. Desligar é a flag/kill switch, não o cancel.
3. `auto_skipped` é contador em memória (zera no restart); `auto_approved_1h`/`auto_refused_1h` vêm das linhas.
4. `OPERATOR_RULE_SET` na API ainda diz `("operator", "4")` (documental; a leitura é por nome + status) — fora do escopo.
5. `apps/web` (painel "modo sozinho — estágio 1", `n/5 compras, x/0,25 SOL`, lista das aprovações do dia) é a T4.28b;
   os campos do heartbeat já existem (§2.2 acima). `GET /meme/live` ainda não os expõe tipados — a T4.28b decide.
