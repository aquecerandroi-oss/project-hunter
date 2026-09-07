# Notas da T3.1/T3.1b — a `0006_paper_wallet` depois da revisão de segurança

**Autor:** database-architect, 2026-09-06. **Para:** Sexta-feira, T3.3, T3.4, T3.6 e T3.12.
**Eu não editei `services/**`, `apps/**`, `packages/core/hunter_core/{portfolio,risk,execution}/**`
nem `packages/risk-core/**`** (deste último eu só importo).

Entrada: `.claude/state/review-T3.1-security.md` (security-reviewer, 2 bloqueantes, 5 "deve
corrigir", 5 sugestões). A `0006` **nunca foi aplicada a banco persistente** — VPS e stack local em
`0005_baseline_lock_grant`, verificado antes de editar —, então a correção foi **na própria
revisão**, não numa `0007`. O contrato inteiro está em `docs/DATABASE.md` §18; aqui fica só o que
outra tarefa precisa saber para não quebrar.

## 1. O que muda para quem escreve kill switch (T3.6, e T3.4 no fechamento por kill switch)

`portfolios_kill_switch_is_audited` (e agora `organizations_kill_switch_is_audited`) exige, no
COMMIT, **duas** coisas da transição que explica o movimento:

1. ela é a **mais recente** de `(scope, scope_id)` por `ORDER BY created_at DESC, id DESC`, com
   `from = OLD.kill_switch_state` e `to = NEW.kill_switch_state`;
2. ela foi escrita **nesta transação** (`xmin = pg_current_xact_id()::xid`).

Três consequências operacionais:

- **Nada de `SAVEPOINT` entre a transição e o `UPDATE`.** Uma linha inserida dentro de um savepoint
  carrega o xid da subtransação, e `pg_current_xact_id()` devolve o do topo (medido). O efeito é uma
  **recusa falsa**, nunca uma aprovação falsa, mas é uma recusa. `record_transition` hoje não usa
  savepoint; se alguém introduzir `session.begin_nested()` nesse caminho, isto quebra.
- **Um movimento por transação e por escopo.** Mover `ACTIVE → WARNING → TRADING_DISABLED` em dois
  `UPDATE` na mesma transação é recusado: a trigger adiada dispara duas vezes e as duas leem a mesma
  "última transição".
- **`created_at` importa.** `record_transition` passa `now` explicitamente. Se um chamador passar um
  instante **anterior** ao da última transição daquele escopo, a linha nova não é a mais recente e o
  movimento é recusado. Use o mesmo relógio monotônico da avaliação.

`organizations` passou a ter a mesma trigger com `scope = 'organization'` e
`scope_id = organization_id`. Quem mover `organizations.kill_switch_state` — hoje ninguém; a T3.6 lê
via `organization_kill_switch` — tem de escrever a transição junto. **O escopo `system` não tem
trigger** porque não tem linha (é configuração de processo).

`CHECK (actor_type <> 'system' OR evidence <> '{}'::jsonb)`: toda transição automática precisa de
`evidence` não vazia. `build_evidence` já produz uma; o que quebra é um caminho que grave
`actor_type='system'` sem chamar essa função — e há fixture de teste que quebrou por isso
(corrigidas: `test_schema_paper.py`, `test_schema_rls.py`).

## 2. O que muda para a T3.6: quem escreve o quê

Escrito explicitamente porque foi a implicação da decisão 5 da revisão:

| Quem | Escreve |
|---|---|
| `hunter_app` (API, retomada) | `kill_switch_transitions` + `portfolios.kill_switch_state` (+ `risk_events`) |
| `hunter_worker` (motor) | `portfolio_risk_state`: `trading_day`, `trading_day_start_utc`, `equity_day_start`, `day_reference_observed_at`, `peak_equity`, `peak_equity_at`, `last_admission_seq` |

**O grant do `hunter_app` em `portfolio_risk_state` mudou:** `SELECT`, `INSERT` e
`UPDATE (updated_at)` — só essa coluna. O `SELECT ... FOR UPDATE` de `load_locked_state` continua
funcionando (medido: um grant por coluna satisfaz o row mark e recusa toda escrita de valor,
Postgres 16.15; isso corrige uma afirmação errada da §17.2). Qualquer `UPDATE` do app que escreva
`peak_equity`, `equity_day_start`, `last_admission_seq` etc. agora falha com **permission denied**,
não com a mensagem do trigger. O trigger continua como defesa em profundidade e passou a testar
**pertencimento de papel** (`pg_has_role(current_user, 'hunter_worker', 'USAGE')`) em vez de
`current_user = 'hunter_app'`: a Astra atravessou o teste por nome com um papel que apenas herda
`hunter_app`. Provado nos dois sentidos em
`test_the_app_role_can_lock_the_wallet_row_and_never_write_it` e
`test_a_role_that_merely_inherits_the_app_cannot_write_the_lock_row_either`.

**Se algum caminho de vocês precisar mesmo escrever a linha de trava, rode-o como `hunter_worker`.**
Rodar como `hunter_app` não é mais uma questão de trigger: é privilégio.

Três invariantes novas no mesmo trigger, que valem para o **worker** também:

- `trading_day` **estritamente crescente**, e nunca volta a `NULL`;
- `equity_day_start` (com `day_reference_observed_at`) **uma vez por `trading_day`**; desconhecido →
  conhecido continua permitido, conhecido → outra coisa não;
- **`peak_equity` e `equity_day_start` ≤ equity observado**, definido como
  `greatest(max(portfolio_equity_snapshots.equity) da carteira, portfolios.initial_capital)` — mais,
  no `UPDATE`, o pico atual. Só avaliado quando um dos dois **sobe**. Consequência prática para a
  T3.5 e para o worker do dia: **grave o ponto da curva antes (ou na mesma transação que) o pico e a
  referência do dia**, senão a subida é recusada por não ter observação que a sustente.
  `equity_day_start` é *limitado* pelo teto e não faz parte dele — a Astra reproduziu um `INSERT` que
  declarava `peak = equity_day_start = 999999` e se autoautorizava.
- **O teto do `INSERT` é um segundo trigger, `portfolio_risk_state_opens_honestly`, adiado para o
  COMMIT.** Em `BEFORE INSERT` ele era escapável por uma CTE que escrevia a linha de trava antes da
  carteira (a FK só é verificada no fim do statement). Efeito para vocês: a violação aparece **no
  commit**, não no `flush()`.
- Índice novo `ix_portfolio_equity_snapshots_peak_lookup` em `(portfolio_id, equity)`, na pai
  particionada, para que esse teto seja um index scan e não uma agregação da curva inteira.

## 3. O que muda para a T3.3 (abertura da carteira)

- **A carteira principal é única por organização**, não por `(organização, workspace)`
  (`uq_portfolios_principal_paper` em `(organization_id) WHERE type='paper' AND NOT is_arena`).
  `open_paper_wallet` continua **seguro** — a segunda abertura em outro workspace da mesma
  organização perde no índice, a `IntegrityError` nomeia `uq_portfolios_principal_paper` e o `except`
  existente a converte em `WalletAlreadyOpen`. O que precisa mudar é cosmético e enganoso hoje:
  `PortfolioRepository.principal_paper_id(workspace_id)` pré-checa pelo workspace (nunca vai
  encontrar a carteira do workspace vizinho) e a mensagem diz "concurrent opening" para o que é uma
  carteira já aberta noutro workspace. **Ajuste sugerido:** escopar a pré-checagem pela organização e
  reescrever a docstring de `opening.py` e a de `WalletAlreadyOpen`.
- **A âncora confere o par da observação**: `fx_observations.pair` tem de ser
  `operating_currency || origin_currency` (`USDTBRL`) e ter `available_at`. `PAPER_FX_POLICY` já
  declara `pair="USDTBRL"`, então o caminho da T3.3 passa; o que passa a ser impossível é abrir
  com uma cotação de outro par por outro caminho.
- `packages/core/tests/integration/conftest.py::paper_ledger_db` tem docstring dizendo "unique per
  `(organization, workspace)`" — ficou desatualizada e é arquivo de vocês (estava sendo editado em
  paralelo enquanto eu trabalhava, então não toquei).

## 4. O que muda para a T3.4 / T3.12 (execução e admissão)

- `orders.position_id`, `trades.position_id` e `trades.proposal_id` passaram a FKs **compostas**
  `(id, organization_id, portfolio_id, market_id)`. Nenhuma assinatura Python muda; o que muda é que
  uma linha com escopo divergente agora levanta `IntegrityError` em vez de gravar.
- **`orders.exit_intent_id` exige `position_id`** (`ck_orders_an_exit_attempt_names_its_position`) e
  os dois têm de nomear a mesma posição (`fk_orders_exit_intent_matches_position`). Toda tentativa
  contra uma proteção durável precisa preencher `position_id`.
- **`participation_consumptions` com `kind='released'`**: `notional ≤ trade_proposals.
  reserved_notional` da própria proposta, e liberação contra proposta sem reserva quantificada é
  recusada.
- **Ciclo de reserva** (`consumed → held`) continua sendo invariante do serviço de admissão, não DDL
  — declarado em §18.3 com o motivo de não virar trigger.

## 5. O que muda para o seed / deploy

`infra/scripts/seed_reference.PAPER_V1_LIMITS` passou a ser
`hunter_risk.limits.PAPER_V1.model_dump(mode="json")`. **Nenhum valor da diretiva mudou.** O que
mudou é o conjunto de chaves: entram as seis que o motor exige e faltavam
(`max_entry_deviation_pct`, `max_price_age_s`, `max_book_age_s`, `max_volume_age_s`,
`max_beta_age_s`, `day_timezone`) mais `profile`, e saem as quatro que `RiskLimits` não tem
(`participation_reference`, `market_types`, `auto_close_on_emergency`, `regime_size_multiplier`).
O destino de cada uma está na §18.8.

**Consequência de deploy:** um banco onde o `paper_v1` já foi semeado com o JSON antigo **para o
seed** na próxima execução (`_refuse_diverging_preset`), com a lista de chaves divergentes. Isso é a
política funcionando (§17.8: conteúdo publicado é congelado), e a saída é apagar a linha
`risk_profiles` de preset `paper_v1` com `organization_id IS NULL` e reexecutar o seed —
deliberadamente, sabendo que nenhuma organização copiou esse preset ainda. Em banco de hoje isso é
zero: `paper_v1` nunca foi semeado em lugar nenhum, porque a `0006` nunca rodou.

**Pendência declarada, fora deste diff:** `docs/RISK_ENGINE.md` §2 ainda lista
`participation_reference` e `regime_size_multiplier` como chaves do perfil `paper_v1`, e
`RiskLimits` não tem campo para nenhuma das duas — o motor do M3 não implementa a gramática de
multiplicador por regime. Fechar isso é decisão do dono de `docs/RISK_ENGINE.md` e de
`packages/risk-core/**` (acrescentar os campos ou remover as linhas da tabela).

## 6. Onde estão as provas

`packages/core/tests/integration/test_schema_paper.py`, seção "T3.1b" no fim do arquivo: um teste
por achado, todos executando o SQL como o papel real e provando a recusa. Os nomes começam por
`test_a_banked_transition_...`, `test_a_transition_banked_in_an_earlier_transaction_...`,
`test_an_organization_cannot_move_its_kill_switch_unaudited`,
`test_a_new_workspace_does_not_free_a_second_principal_wallet`,
`test_a_row_cannot_claim_another_organizations_position`,
`test_a_trade_cannot_claim_another_organizations_proposal`,
`test_an_exit_attempt_and_its_intention_must_name_the_same_position`,
`test_the_app_role_can_lock_the_wallet_row_and_never_write_it`,
`test_the_peak_may_not_be_set_above_the_equity_that_was_observed`,
`test_a_wallet_cannot_open_with_a_peak_it_never_reached`,
`test_the_trading_day_only_advances_and_its_reference_is_set_once`,
`test_an_anchor_refuses_an_observation_of_another_currency_pair`,
`test_a_participation_release_cannot_exceed_its_own_reservation`,
`test_a_release_against_a_proposal_that_reserved_nothing_is_refused`,
`test_an_automatic_transition_must_carry_its_evidence`,
`test_the_kill_switch_trail_outlives_the_tenant`,
`test_the_teardown_orphan_is_still_invisible_to_every_other_tenant`,
`test_the_seeded_paper_profile_has_exactly_one_source`.
