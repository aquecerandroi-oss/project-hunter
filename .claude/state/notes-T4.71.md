# Notas T4.71 — `0055_meme_operator6_desk`: a segunda mesa real (`operator/6`)

Data: 2026-09-19. Escopo: `infra/migrations/ddl/meme_operator_6.py` (novo), `infra/migrations/versions/0055_meme_operator6_desk.py`
(novo), `packages/core/tests/integration/test_migration_0055.py` (novo), `test_migrations.py` (HEAD, contagem 20 → 21, dez
asserções da mesa no `head`), `test_migration_0049.py` (posicionado em `0049`), `docs/DATABASE.md` §62,
`docs/RISK_ENGINE_MEME.md` §3 (parágrafo), `obsidian/03-TRADING/Meme/Mesa-operator-6.md` (novo). Nada em
`services/meme-worker/hunter_meme_worker/event_*.py`, nada em `.env*`, nenhum commit.

## 1. A semente

- `operator/6` (`01994d00-6c1a-7000-8000-000000000019`, `kind = operator`, `exp_ref NULL`, `status active`) =
  `FLOW_V2_PARAMS` (a constante da `0030` que plantou `flow_v2/1`) `||` `OPERATOR_6_OVERRIDES` (12 chaves: `exit_key`,
  `target_x "1.15"`, `trailing_pct "10"`, `trailing_arm_x null`, `max_hold_s 300`, `exit_on_line_break true`, `size_sol`/
  `max_sol_per_bet`/`max_exposure_per_mint_sol "0.07"`, `max_open_positions 2`, `ttl_s 180`, `pedigree_repeat_dumper true`).
- **Lida do seed do DDL, não da linha viva** (o brief pedia isso quando `flow_v2/1` pudesse ter sido editado por
  `--set-param`); dito na docstring da migração e do módulo. `max_loss_pct "50"`, `wallet_max_sol "2.0"`,
  `daily_loss_cap_sol "0.20"`, `fee_pct "1.75"`, `clock "15s"`, `exit_version 1` ficam os do `flow_v2/1`.
- Nada aposentado. Downgrade: recusa em `meme_live_orders` e `meme_live_positions` (via `proposal_id IN (SELECT id FROM
  meme_proposals WHERE rule_set_id = …)`) **antes** de `meme_proposals`, `meme_paper_bets`, `meme_rule_set_param_history`,
  `meme_gate_refusals_by_mint`.

## 2. Confirmado no código

- `services/meme-executor/hunter_meme_executor/auto_approve.py:_OPERATOR_PROPOSED` — `WHERE rs.kind = 'operator' AND
  rs.status = 'active'`, sem nome/versão → qualquer operator ativo chega ao executor. `repo_tape.pending_operator_mints` idem.
- `packages/risk-core/hunter_risk_meme/checks_wallet.py` — `limits.max_open_positions` e `limits.daily_loss_cap_sol`
  (`MemeLimits`, env `MEME_MAX_OPEN_POSITIONS`/`MEME_DAILY_LOSS_CAP_SOL`) contam sobre todas as posições, sem `rule_set`.
  Teste `test_the_executor_opens_any_active_operator_set_and_the_brakes_are_shared` lê o fonte.
- Saída real: `exit_common.exit_params` lê `target_x`/`trailing_pct`/`max_hold_s` de `meme_live_positions.params`
  (= `decision` = `suggested` do conjunto); trailing sempre armado → `trailing_arm_x null` é o comportamento do executor.

## 3. Desvio declarado (DATABASE.md §62, RISK_ENGINE_MEME §3)

- A invariante "exatamente um `operator` ativo" (0033/0034/0039, §45.3) acaba. Vive só dentro daquelas revisões; o
  downgrade da 0055 remove `operator/6` antes de elas rodarem → cadeia reversível (provado pelo `-k "reverses"`).
- `MemeDeskRepository.get_operator_rule_set` (API) pega a **maior versão ativa** → compra **manual** da mesa passa a ser
  arquivada sob `operator/6` (teto `max_sol_per_bet "0.07"`). `meme_rule_set.py --deprecate` deixa uma das duas sair.
- `test_migration_0049.py` rodava no `head` e asseria `desk == ["operator/5"]`: agora se posiciona em `0049` e roda o
  `alembic check` num banco próprio no `head` (formato da `0050`+).

## 4. Paralelo: `0056_meme_spot_swaps` (T4.73) pousou em cima da `0055` durante esta tarefa

Outro agente criou `0056` com `down_revision = 0055_meme_operator6_desk` e bumpou `HEAD_REVISION = "0056_meme_spot_swaps"`
em `test_migrations.py` (a minha docstring e as dez asserções sobreviveram). `test_migration_0055.py` se posiciona em
`0055` por nome, então `"-1"` continua sendo o passo desta revisão. O round trip pela CLI abaixo já foi feito com a
`0056` no `head`.

## 5. Comandos

- `uv run pytest packages/core/tests/integration/test_migration_0055.py` → 10 passed (41 s).
- `uv run pytest packages/core/tests/integration/test_migration_0049.py test_migration_0054.py` → 16 passed (68 s).
- `uv run pytest packages/core/tests/integration/test_migrations.py -k "0022 or head or autogenerate or reverses"` →
  45 passed (359 s) — antes de a `0056` pousar.
- `uv run pytest packages/core/tests/integration/test_migrations.py -k "0033 or 0034 or 0039 or 0044 or 0029"` → 18 passed.
- `uv run pytest packages/core/tests/integration/test_schema_rls.py -k "each_org_sees_only_its_own or cannot_read_or_edit_another
  or without_current_org or another_orgs_id_fails"` → 4 passed (RLS: org A não lê org B).
- CLI num container limpo (script no scratchpad): `alembic upgrade head` → `0056_meme_spot_swaps (head)`; `alembic check` →
  exit 0; `alembic downgrade -1` → `0055_meme_operator6_desk`; `alembic upgrade head`; `alembic check` → exit 0.
- `uv run ruff check`/`format --check` nos arquivos tocados → limpo; `uv run pyright` (4 arquivos) → 0 erros;
  `uv run python infra/scripts/check_file_size.py` → 0 over budget.

## 6. Concerns

- Compra manual sob `operator/6` (acima). Se o Everton quiser que a manual continue sob `operator/5`, é uma linha na API
  (`OPERATOR_RULE_SET`/`get_operator_rule_set`), fora desta tarefa.
- As duas mesas competem pelas mesmas 2 vagas reais: quando propõem a mesma moeda no mesmo tique, a segunda recusa
  `duplicate_position`/`max_open_positions`; esperado, conta no balanço (vault, §2).
- Os valores do `operator/5` na tabela do vault são os da VPS conforme a decisão de 19/09 02:10 (não lidos do banco);
  a nota manda conferir com `--history operator/5`.
