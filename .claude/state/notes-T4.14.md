# Notas T4.14 — o executor real (`services/meme-executor/`), o motor `hunter_risk_meme`, `meme_proposals.mode` e as ordens/posições reais

Execução: 2026-09-12, início ~15:2x BRT (18:2x UTC). Papel: risk-engine guardian / engenheiro de execução.
Brief: `.claude/state/brief-T4.14-executor-real.md`. Sem commit. Nenhum `.env*` lido ou escrito. Nenhuma chave real:
só chaves de teste geradas em memória (RNG semeado) e descartadas. **Nenhum `sendTransaction` na mainnet.**
`ENABLE_MEME_LIVE_TRADING` não aparece como `true` em arquivo nenhum deste repositório.

## 0. Leitura (o que o código tinha ao começar)

- Migração mais nova **no disco**: `0027_meme_wallets` (T4.12, ainda não rastreada pelo git). T4.11 não criou
  migração nenhuma até o momento da leitura (`ls infra/migrations/versions/`). **A desta tarefa é `0028_meme_live`.**
  `packages/core/tests/integration/test_migrations.py` ainda dizia `HEAD_REVISION = "0026_meme_lines"` (a T4.12 não
  bumpou); esta tarefa bumpa para `0028_meme_live` — se a T4.12 bumpar para `0027` em paralelo, o orquestrador resolve
  a favor de `0028`.
- T4.8 entregou o caminho de assinatura inteiro e inerte: `tx.py` (instruções byte a byte iguais às reais), `quote.py`
  (cotação inteira em lamports, `quote_buy_for_budget`), `verify.py` (§9.1, reconstrói a mensagem e compara bytes),
  `tx_rpc.py` (`send_transaction` recusado sem `allow_send=True`), `trade_event.py` (fill = `TradeEvent`),
  `hunter_core.execution.meme.{gates,signer,journal,submit}` (portões, chave lida uma vez, diário, máquina de estados
  `submitted_unconfirmed/confirmed/failed`). O `MemeSubmitter` é **síncrono** (RPC `httpx.Client`, `time.sleep`).
- T4.6/T4.7: `meme_proposals` (status `proposed → approved → filled|unfilled`), `decision` jsonb
  `{size_sol, target_x, trailing_pct, max_hold_s, note}` escrito pela API; o laço de papel preenche `approved` na
  fotografia seguinte. `hunter_app` só tem `UPDATE` nas 4 colunas de decisão de `meme_proposals`.
- `docs/RISK_ENGINE_MEME.md` §13 propõe `packages/risk-core/hunter_risk_meme/` como pacote irmão **nunca importado por
  `hunter_risk`** (e vice-versa) — é o que esta tarefa constrói, com teste de fronteira.

## 1. Decisões de desenho (registradas antes de codar)

1. **`hunter_risk_meme` em `packages/risk-core/hunter_risk_meme/`** (e não em `hunter_core/execution/meme/admission.py`):
   a doutrina §13 pede pacote puro irmão, sem importar `hunter_risk`; `hunter_core.execution.meme` é o caminho de
   assinatura (efeitos), e o motor puro não pode morar ao lado de quem assina. Base própria (`MemeModel`: frozen,
   `extra="forbid"`, recusa `float`) copiada de `hunter_risk.base` em vez de importada, para a fronteira valer.
2. **Dois TTLs, os dois nomeados.** `MEME_LIVE_APPROVAL_TTL_S` (default 30 s): uma aprovação da mesa mais velha que isso
   nunca é executada (regra de restart do guardião). `reservation_ttl_s = 5` (doutrina §9.5): entre a admissão e a
   assinatura, `ApprovedSubmission.expires_at = admitted_at + 5 s`; o submitter recusa `reservation_expired`.
3. **O executor não depende de `meme_proposals.status` continuar `approved`**: o laço de papel (sombra) move a proposta
   para `filled`/`unfilled` na fotografia seguinte. O candidato live é `mode='live' AND status IN ('approved','filled',
   'unfilled') AND decided_at >= now − TTL AND NOT EXISTS meme_live_orders(proposal_id, side='buy')`. `rejected`
   (cancelada pelo operador) nunca executa.
4. **Diário durável em Postgres com escrita síncrona entre assinar e enviar.** O `MemeSubmitter` roda numa thread
   (`asyncio.to_thread`); o `PostgresOrderJournal` faz cada escrita via `asyncio.run_coroutine_threadsafe(...).result()`
   no loop principal, com sessão e commit próprios — a assinatura fica gravada em `meme_live_orders.signatures`
   **antes** do `sendTransaction`, então um crash entre os dois deixa uma linha que `reconcile` acerta na volta
   (VM5/VM8), nunca uma segunda assinatura.
5. **`sell_now` real não passa por `meme_operator_commands`** (o CHECK exige `bet_id`, e a posição real não é aposta):
   `meme_live_positions.sell_requested_at/by` recebem `UPDATE` do `hunter_app` por
   `POST /meme/live/positions/{id}/sell-now` (TRADER+, `Idempotency-Key`), e o laço de saídas trata como gatilho
   acima de qualquer regra.
6. **Kill switch efetivo = mais restritivo de** (a) `SYSTEM_KILL_SWITCH` do ambiente, (b) Redis `meme:kill`
   (`ACTIVE|WARNING|TRADING_DISABLED|EMERGENCY`, escrito à mão — "desligar em 5 s"), (c) arquivo `MEME_KILL_FILE`
   (existe ⇒ `EMERGENCY`), (d) a trava diária **durável** em `meme_live_kill_switch` (latched pelo executor quando a
   perda do dia ≥ `MEME_DAILY_LOSS_CAP_SOL`; só sai por `UPDATE` manual do dono, documentado). Relido a cada 10 s
   com ou sem evento e de novo dentro do passo que aplica efeito.
7. **`meme_auto_close_on_emergency` default false** (`MEME_AUTO_CLOSE_ON_EMERGENCY`): `EMERGENCY` bloqueia entradas;
   fecha posições só com a variável ligada, e cada fechamento é uma venda normal (verificada, simulada, assinada).
8. **Migração pós-graduação:** a T4.8 não cobre `sell` no PumpSwap (sem construtor nem verificador para o `pAMM…`).
   Posição cujo mint migrou ⇒ recusa nomeada `pumpswap_sell_not_implemented`, posição fica `open` com
   `exit_intent` `blocked_migrated` e alerta no heartbeat; antes da migração, `complete=true` dispara venda na curva
   enquanto ela aceita (`sell` ainda executa até o `migrate`).
9. **Portão "teste pequeno autorizado por escrito"** (`gates.py`, extensão): `meme_gates.json` pode trazer
   `small_test_authorization {authorized_by, scope{max_sol_per_trade, max_trades, max_total_sol}, expires_at,
   decision_note}` no lugar de A/B `passed=true`; `decision_note` tem de apontar para `obsidian/06-DECISIONS/…`
   existente. O escopo vira teto adicional do motor (`min` com o `.env`) e contador de trades no executor.

## 2. Linha do tempo e comandos (incremental)

- 15:2x BRT — leitura: brief, RISK_ENGINE.md, RISK_ENGINE_MEME.md, PIPELINE §7–8, ARCHITECTURE §6, T4.8/T4.6/T4.7/T4.12/
  T4.13 notes, código T4.8, meme-worker (`main/config/wiring/lab_repo/paper_engine`), DDL 0022/0027, API meme_lab/
  meme_desk, runtime/entrypoint/compose. `git status --porcelain` na partida: modificados de outras tarefas
  (`apps/web/**`, `app.py`, `models/__init__.py`, `meme_lab_views.py`, `rpc.py`, `config.py`/`context.py` do
  meme-worker, `api.d.ts`) e novos da T4.12/T4.13 — nada meu.

## 3. Retomada (2ª sessão, 12/09/2026 13:5x–14:3x BRT / 16:5x–17:3x UTC) — o que estava no disco e o que faltava

Ponto de partida: `git status --porcelain` com os arquivos da §2 já no disco (motor, migração `0028`, modelo, API,
executor, testes) mais os das T4.11/T4.12 (não tocados). Verificações iniciais: risk-core meme + executor unit
**106 passed**; `apps/api/tests/unit -k meme` **não coletava** (`hunter_core.errors` não existe).

Feito nesta sessão, na ordem:

1. **API volta a coletar**: `LivePositionNotFoundError(HunterError)` em `services/meme_live.py` (404 problem+json,
   a forma de `ProposalNotFoundError`); o router importa dela. Tipagem de `order_out` fechada (`_refusals`).
2. **`mode = live` na mesa**: `enforce_live_mode(body, live_enabled)` em `services/meme_desk_common.py` (422
   `meme_live_disabled` sem a flag da API; devolve o modo a persistir); `_decide`/`approve_proposal`/
   `file_manual_proposal` recebem `live_enabled` e gravam `mode` (`decide_proposal(mode=…)`, `ProposalRow.mode`);
   `routers/meme_desk.py` injeta `Settings` (`get_settings`) e passa `settings.enable_meme_live_trading`.
   Testes `TestLiveMode` (4) em `test_meme_desk_service.py`: default `paper`; `live` sem flag ⇒ recusa nomeada e
   `decide_calls == 0` (nada decidido); `live` com flag ⇒ `mode == "live"`; manual idem.
3. **Kill switch relido entre a admissão e a assinatura** (`entries.py`): depois de `insert_order(status=admitted)`
   e antes de `_submit_and_record`, `ctx.kill.refresh()`; se bloqueia ⇒ `refuse_admitted_order(…, reason=
   "kill_switch_blocked_before_signing")` (novo em `repo.py`: `UPDATE … WHERE status='admitted' AND signing_at IS
   NULL`), nada assinado. Teste no testcontainer: `FakeRedis.get` devolve `ACTIVE` na 1ª leitura e
   `TRADING_DISABLED` na 2ª ⇒ linha `refused` com `admission.approved = true`, `signatures = []`, `rpc.sent == []`.
4. **Orçamento de 350 linhas**: `repo.py` (437) dividido em `repo.py` + `repo_positions.py` (re-exportado);
   `exits.py` 352 → docstring encurtado; `meme_vm.py` 361 → 349 (docstring, `ENGINE_MISSING`, `SimulationResult`
   real no fake, alias `verify_message`); `hunter_core/settings.py` 352 → 350 (o hunk `Role` da T4.14 tinha
   empurrado 2 linhas; reflow do docstring do módulo, sem mudança de comportamento).
5. **Trava diária re-armável**: `_LATCH` exigia `latched_at IS NULL`; depois da soltura manual do dono
   (`released_at` preenchido) o teto do dia seguinte **nunca travaria de novo**. Agora
   `WHERE latched_at IS NULL OR released_at IS NOT NULL` (e a trava limpa `released_*`). Teste
   `test_the_daily_latch_can_bite_again_after_the_owner_released_it`.
6. **Testes 0028** em `test_migrations.py` (a 1ª sessão só tinha criado as constantes): coluna defaultada +
   CHECK, 3 tabelas, grants (`hunter_app`: SELECT + `UPDATE(sell_requested_at, sell_requested_by)` +
   `UPDATE(mode)` — e **não** `status`/`tokens`/`exit_at`/`mark_sol`/`mint`), seed `wallet:ACTIVE`, 7 CHECKs de
   ordem + 5 de posição por nome, as duas chaves de idempotência (`uq_…_one_buy_per_proposal`,
   `uq_…_tx_signature`), descida recusada com proposta `live` **e** com ordem (mensagem com as contagens),
   reversão limpa e volta com re-seed. **3 passed em 33,8 s.**
7. **`evaluate.py`**: `sizing=sizing if approved else sizing` → `sizing=sizing` (o painel sempre vê o tamanho).
8. **`pnpm gen:types`** regenerado (`meme/live` presente em `api.d.ts`).

Comandos e saídas (todos em primeiro plano, `timeout 290`/`590`):

```
uv run ruff check <arquivos T4.14>            -> All checks passed!
uv run ruff format --check (via format)       -> 0 reformats pendentes ao final
uv run pyright services/meme-executor packages/risk-core/hunter_risk_meme packages/risk-core/tests/unit/meme
   apps/api/hunter_api/{routers,services,repositories,schemas}/meme_live.py apps/api/hunter_api/services/meme_desk*.py
   apps/api/hunter_api/routers/meme_desk.py packages/core/hunter_core/db/models/meme_live.py
   packages/core/hunter_core/settings.py infra/scripts/meme_vm*.py packages/core/hunter_core/execution/meme/gates.py
   apps/api/tests/unit/test_meme_desk_service.py           -> 0 errors, 0 warnings, 0 informations
uv run pytest packages/risk-core/tests/unit/meme services/meme-executor/tests/test_config_boot.py -q -> 101 passed
uv run pytest apps/api/tests/unit -q -k meme               -> 113 passed, 602 deselected
uv run pytest services/meme-executor/tests/test_live_persistence.py -q   (testcontainer, sozinho) -> 8 passed in 37.29s
uv run pytest packages/core/tests/integration/test_migrations.py -k 0028 -q (testcontainer)      -> 3 passed in 33.80s
bash infra/scripts/forbidden_patterns.sh --self-test       -> self-test: all patterns detected, clean/exempt fixtures pass
uv run python infra/scripts/check_file_size.py --baseline infra/scripts/file_size_baseline.txt -> scanned 812 files; 0 over budget
uv run python infra/scripts/meme_vm.py                     -> VM1 PASS VM2 PASS VM3 PASS VM4 PASS VM5 PASS VM6 PENDING(c: papel)
                                                              VM7 PASS VM8 PENDING(Postgres: testcontainer) VM9 PENDING(idem) 9.1 PASS
pnpm gen:types                                             -> api.d.ts regenerado
```

Boot-refusal (brief 4e), `services/meme-executor/tests/test_config_boot.py` (9 testes, incluídos nos 101 acima):
flag ligada sem `MEME_GATES_FILE` ⇒ `gates_file_not_configured`; com portões e sem política ⇒ `policy_missing`
(nomeia `MEME_WALLET_MAX_SOL`…); sem `SOLANA_RPC_URL` ⇒ `rpc_url_missing`; URL devnet com cluster mainnet ⇒
`rpc_url_cluster_mismatch`; sem chave ⇒ `secret_key_missing` (por último, a chave nunca é tocada antes); tudo
presente ⇒ live e a variável **removida do ambiente**; teste pequeno sem `decision_note` em `obsidian/06-DECISIONS/`
⇒ `small_test_without_decision_note`; flag desligada ⇒ inerte com `meme_paper_v0`.

## 6. O que a mesa (`apps/web`, não tocado nesta tarefa) precisa renderizar

Fonte de tudo: `GET /api/v1/orgs/{org}/meme/live` (`MemeLiveOut`, tipos já em `packages/shared-types` via
`pnpm gen:types`) e o campo `mode` das propostas.

1. **Botão "Aprovar (REAL)"** na proposta `proposed`, visível **só** quando `MemeLiveOut.api_live_enabled = true`
   (a cópia da flag na API). Ao clicar: confirmação dupla (1ª: os quatro parâmetros e o rótulo "REAL — dinheiro da
   carteira dedicada"; 2ª: digitar o `size_sol` de novo). O POST é o mesmo `…/proposals/{id}/approve` com
   `"mode": "live"` no corpo e `Idempotency-Key`. 422 `meme_live_disabled` ⇒ toast nomeado, nunca silencioso.
   O mesmo em `…/proposals/manual`.
2. **Rótulo REAL** permanente (`MemeLiveOut.label`) em toda linha vinda de `meme_live_*`; nunca misturar com as
   apostas de papel na mesma tabela sem o selo. A proposta `live` continua aparecendo no papel (sombra) — a linha
   de papel mostra "sombra de uma ordem REAL" quando `proposal.mode == "live"`.
3. **Painel do executor** (`MemeLiveOut.executor`): `status` (`alive` · `stalled` · `never` · `heartbeat_missing`
   · `redis_unavailable`), `live_enabled`, `cluster`, `wallet_pubkey` (público), `wallet_sol_balance` +
   `wallet_read_at`, `kill_switch` + `kill_switch_sources` (`system`/`redis`/`file`/`wallet`) + `kill_switch_latched`
   + `kill_switch_latch_reason`, `gates` (datas ou o escopo do teste pequeno com `decision_note`), `policy`
   (os cinco tetos), `orders_by_state`, `positions_open`, `blocked_exits`, `last_signature` (link para o
   explorer), `last_refusal`, `day_start_sol_equity`/`equity_sol`/`daily_loss_sol`, `auto_close_on_emergency`.
4. **Ordens** (`MemeLiveOut.orders`): `status` com cor (`refused`/`failed` vermelho, `submitted_unconfirmed`
   âmbar com "reconciliando", `confirmed` verde), `reason`, `first_refusal`, `binding_constraint`, `sol_final`,
   `tx_signature`, `fill` (SOL gasto real = `buy_total_lamports`, tokens, taxas, `holder_rewards`).
5. **Posições** (`MemeLiveOut.positions`): marca honesta (`mark_sol`/`mark_source`/`mark_reason`), `high_water_sol`,
   `exit_intent` (mostrar `blocked: pumpswap_sell_not_implemented` como "presa após migração — vender no site"),
   botão **"Vender agora (REAL)"** quando `can_sell_now` ⇒ `POST …/meme/live/positions/{id}/sell-now`
   (confirmação simples; 202 com `already_requested`), PnL/R no fechamento.
6. **Desligar**: link para `docs/DEPLOYMENT.md` §3.7 (arquivo `meme.kill`); a tela não precisa (nem deve) ter um
   botão que escreva no Redis — a API não tem esse grant e é assim de propósito.

## 7. O que o Everton precisa digitar/decidir para ligar (a lista exata; `docs/ACTIVATION.md` §9b)

1. Decidir e escrever os cinco números: `MEME_WALLET_MAX_SOL`, `MEME_MAX_SOL_PER_TRADE`, `MEME_DAILY_LOSS_CAP_SOL`,
   `MEME_MAX_OPEN_POSITIONS`, `MEME_COOLDOWN_S` (§3.1, coluna live — hoje vazia).
2. Decidir o teste pequeno por escrito (Portões A/B estão vermelhos): `obsidian/06-DECISIONS/AAAA-MM-DD-teste-
   pequeno-meme-real.md` com `max_sol_per_trade`, `max_total_sol`, `max_trades`, validade.
3. Escrever `/opt/project-hunter/run/meme/meme_gates.json` (`gate_c_owner.enabled = true`, `signed_by`,
   `valid_until`, `small_test_authorization` apontando para o arquivo do item 2).
4. Criar a carteira Solana **dedicada**, depositar ≤ `MEME_WALLET_MAX_SOL`, e no `.env` da VPS:
   `ENABLE_MEME_LIVE_TRADING` ligada, `SOLANA_WALLET_SECRET_KEY=…`, `SOLANA_RPC_URL=<RPC próprio>`,
   `MEME_GATES_FILE=/run/hunter/meme_gates.json`, os cinco do item 1, e (só se quiser) `MEME_AUTO_CLOSE_ON_EMERGENCY=true`.
5. `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update` e conferir `hb:meme:executor`/`GET /meme/live`.
6. Aprovar com `"mode": "live"` (HTTP, até a tela existir — §6) e acompanhar; desligar em 5 s com
   `touch /opt/project-hunter/run/meme/meme.kill`.

**E o que precisa acontecer ANTES de qualquer um desses passos valer dinheiro — ver §4/§8:** a paridade do
construtor com o programa da pump.fun **atualizado hoje** (conta restante `bonding_curve_v2`; erro 6074 na
simulação). Sem isso o executor recusa cada compra na simulação (`failed: simulation_failed:…6074`) — falha
fechado, mas não opera.

## 4. Prova de rede (brief 4c) — 12/09/2026 14:09–14:2x BRT (17:09–17:2x UTC), tudo somente leitura

Script: `.claude/state/tmp/meme_live_probe_T4.14.py` (chave descartável gerada em memória com RNG semeado pelo
relógio, nunca gravada; cliente RPC construído com `allow_send=False` — `sendTransaction` recusado pelo próprio
cliente, `SendDisabled`). **Nenhum `sendTransaction` em rede nenhuma.**

```
== probe start 2026-09-12T17:09:48 (UTC)
== throwaway pubkey (never funded, key discarded at exit): 9eoCKjVtEzehnnJSv9yYEwSSkYPANrxUZRq7U4HWpvzN
== devnet requestAirdrop refused: ExchangeError: Solana RPC error during requestAirdrop: code=-32603 message=Internal error
   (2ª tentativa 17:18 UTC: "Solana RPC rate limited during requestAirdrop") -> sem devnet, como na T4.8
== mainnet sendTransaction refused by the client: sendTransaction refused: this RPC client was not built with allow_send=True
== live curve now: mint=4VuVdrUZk4TnZt5BDTYZekkojQn4D6ZMN9DX9pempump slot=446484447 vsol=34888442484 complete=False
== simulate buy [empty_throwaway] ok=False err=AccountNotFound            (pagador sem lamports: a cadeia recusa)
== simulate buy [funded_unsigned] ok=False err={'InstructionError': [3, {'Custom': 6074}]} units=66152 slot=446484451
     Program log: AnchorError thrown in programs/pump/src/sell.rs:133. Error Code: InvalidBondingCurveV2.
     Error Number: 6074. Error Message: bonding_curve_v2 remaining account is missing or invalid.
```

Antes disso, a 1ª execução (17:09 UTC) morreu em `trade_events_from_transaction`: **`ValueError: TradeEvent has 16
trailing bytes`** ao decodificar uma transação real de hoje. Dois achados, ambos do **upgrade do programa da pump.fun
publicado hoje entre ~08:00 UTC (fixtures da T4.8) e 17:09 UTC**:

**Achado A — `TradeEvent` ganhou 16 bytes (`holder_rewards_bps`, `holder_rewards`).** Confirmado pela IDL `main`
do GitHub baixada às 17:13:54 UTC (34 campos contra 32 da IDL on-chain guardada de manhã; `ETag d8a4b9d2…`;
guardada em `.claude/state/tmp/pump_idl_main_20260912.json`). Cenário de falha que isso abria no executor: a
compra **já enviada e confirmada**, `_settle_landed` chama `decode_fills` → exceção não tratada → o laço morre,
a linha fica `simulated` com assinatura (fora da consulta de reconciliação, que só via `submitted_unconfirmed`) e a
posição existe na cadeia sem existir no livro. **Corrigido em três camadas:** `trade_event.py` decodifica o par
como opcional (`None` na forma antiga; qualquer outro comprimento estranho continua recusado — teste
`test_the_2026_09_12_layout_appends_holder_rewards_and_nothing_else_is_tolerated`); `submit.py` trata exceção de
decodificação depois do envio como `submitted_unconfirmed:fill_decode_failed:<Tipo>` (nunca crash; teste
`test_a_fill_that_cannot_be_decoded_after_the_send_is_unconfirmed_never_a_crash`: reconciliação posterior com
decodificador correto confirma com a **mesma** assinatura, `sent == 1`, `signer.calls == 1`); `repo._UNCONFIRMED`
passa a cobrir `simulated` com assinatura e `main.reconcile_once` isola falha por linha. **Além disso**, `sol_spent`
de uma posição passou a ser o **delta real de saldo do pagador** (`meta.preBalances[0] − postBalances[0]`), com a
aritmética do evento guardada ao lado (`event_buy_total_lamports`): no fixture de compra real da T4.8 a carteira
perdeu 1.003.518.840 lamports contra 990.088.500 do evento (13.430.340 do roteador do site); na venda do bot,
715.497.919 contra 715.558.030 (tip). A cadeia é a verdade (§9.6), não a nossa soma.

**Achado B — `buy`/`sell` exigem uma conta restante nova, `bonding_curve_v2` (erro 6074), e a lista de contas
restantes mudou.** Reconhecimento somente leitura (`.claude/state/tmp/meme_v2_recon{,2}_T4.14.py`, 9
`getTransaction` no total) sobre trades reais de hoje:
- venda (`63WEZU62nu9r7rZNUxDE…`, mint `Dnek5…pump`): 16 contas = 14 declaradas + **2** restantes:
  `[Bn1LdXew… = PDA ["bonding-curve-v2", mint] sob 6EF8…, 5cjcW9wE…]`; a conta `4CLQ…` da T4.8 **não** está
  mais lá e `user_volume_accumulator` também não;
- compra (`4Evzff8i…`, mint `BTL9ge6b…pump`): 18 contas = 16 declaradas + **2** restantes:
  `[5kjMaiRL… (somente leitura, não deriva de "bonding-curve-v2"/mint — candidata: `quote_control`, erro 6075),
  EHAAiTxc… (gravável) = Global.buyback_fee_recipients[5]]`; flags declaradas `rwrwwwwrrwrrwwrr`.
- as 16/14 contas **declaradas** de `buy`/`sell` não mudaram na IDL; a mudança é toda nas contas restantes, que a
  IDL não descreve (como a `4CLQ…` de manhã). Instruções novas: `update_holder_reward_config`,
  `distribute_fee_to_holders`, `*_quote_control_*`; estado novo `QuoteControl`.

**Consequência, declarada:** o construtor da T4.8 (`tx.py`) e o verificador §9.1 (que reconstrói pelo mesmo
construtor) continuam **byte a byte iguais ao programa de manhã** e **incompatíveis com o de hoje à tarde**. O
executor **falha fechado**: cada compra morre na simulação (`failed: simulation_failed: …6074`), gravada por nome
em `meme_live_orders`, sem assinar, sem enviar. Mas ele **não compra**. Corrigir é uma tarefa própria (T4.8b):
observar mais compras/vendas de hoje, derivar a segunda conta (`quote_control`?), atualizar `build_buy/sell_
instruction`, regravar os fixtures de paridade (`rpc_tx_buy_raw`/`rpc_tx_probe_raw` são pré-upgrade) e reprovar a
simulação mainnet com pagador financiado sem assinatura (`Instruction: Buy` ok). Não fiz isso aqui: chutar contas
restantes no caminho do dinheiro é exatamente o que o verificador existe para impedir.

O item (c) da prova ("submitter recusa antes de assinar com `allow_send=False`") ficou provado só em unidade
(`test_live_disabled_raises_before_signing`, VM4/VM5), porque na mainnet a simulação recusa antes de chegar lá —
o que é a ordem certa.

## 5. Arquivos da T4.14 (estado final; `git status --porcelain` filtrado — nada commitado)

Novos (`??`): `packages/risk-core/hunter_risk_meme/` (11 módulos), `packages/risk-core/tests/unit/meme/` (7),
`services/meme-executor/` (pyproject, README, `hunter_meme_executor/{__main__,config,context,main,admission,build,
chain,entries,exits,heartbeat,journal_db,kill_switch,repo,repo_positions}.py`, `tests/{conftest,test_build_and_fills,
test_config_boot,test_live_persistence}.py`), `infra/migrations/versions/0028_meme_live.py`,
`infra/migrations/ddl/meme_live.py`, `packages/core/hunter_core/db/models/meme_live.py`,
`apps/api/hunter_api/{routers,repositories,schemas,services}/meme_live.py`, `infra/scripts/meme_vm_engine.py`,
`.claude/state/notes-T4.14.md`.

Modificados (` M`) só com hunks da T4.14: `packages/risk-core/pyproject.toml`, `packages/config/ruff.toml`,
`pyproject.toml` + `uv.lock` (workspace `services/meme-executor`), `packages/core/hunter_core/settings.py`
(`Role` + reflow do docstring), `packages/core/hunter_core/execution/meme/{__init__,gates,submit}.py`,
`packages/core/tests/unit/execution/meme/test_meme_submit.py`,
`packages/exchange-adapters/hunter_exchanges/pumpfun/{trade_event,tx_rpc}.py`,
`packages/exchange-adapters/tests/unit/test_pumpfun_trade_event.py`, `apps/api/hunter_api/app.py`
(`meme_live_router`), `apps/api/hunter_api/settings.py`, `apps/api/hunter_api/{routers,services}/meme_desk.py`,
`apps/api/hunter_api/services/meme_desk_common.py`, `apps/api/tests/unit/test_meme_desk_service.py`,
`infra/docker/{docker-compose.yml,entrypoint.sh}`, `infra/vps/{compose.sh,docker-compose.prod.yml}`,
`infra/scripts/meme_vm.py`, `docs/{DATABASE,DEPLOYMENT,ACTIVATION,RISK_ENGINE_MEME}.md`,
`docs/plans/T4-MEME-RADAR.md`, `packages/shared-types/src/generated/api.d.ts` (regenerado).

Modificados compartilhados com outras tarefas (só ADD): `apps/api/hunter_api/schemas/meme_desk.py`
(`ProposalMode` + `DeskParamsIn.mode` — os hunks `MarkSource`/`mark_source`/`mark_stale_s`/`exit_on_migration`/
`dead` são da T4.11 e `real_observed` da T4.12), `packages/core/hunter_core/db/models/__init__.py` (T4.12 + T4.14),
`packages/core/tests/integration/test_migrations.py` (constantes + `test_0028_*` no fim; 0027 da T4.12 e 0029 da
T4.11 intactos), `packages/core/tests/integration/test_schema_privileges.py` (T4.12 + T4.14). `.claude/launch.json`
(`web-dev-8000`) não é meu — estava no disco; não toquei.

## 8. Concerns (para o orquestrador e para o Everton)

1. **BLOQUEANTE para ligar — paridade pós-upgrade (§4, achado B).** O programa da pump.fun mudou hoje; `buy`/`sell`
   exigem contas restantes novas (`bonding_curve_v2` + uma segunda ainda não identificada; `4CLQ…` sumiu). O
   executor falha fechado na simulação e não compra. T4.8b antes de qualquer SOL: regravar fixtures de hoje,
   atualizar `tx.py`, reprovar `Instruction: Buy` na simulação mainnet, atualizar `docs/PUMPFUN-ONCHAIN.md`.
2. **Venda pós-migração (PumpSwap) não existe** — posição que migrar fica `open` com `blocked:
   pumpswap_sell_not_implemented`; sair é pelo site, na mão. `max_hold_s` curto reduz a exposição a isso.
3. **`GET /meme/live` expõe `wallet_pubkey`** (VIEWER+ da organização, autenticado). RISK_ENGINE_MEME §3.3 pede
   "não em resposta pública de API"; o brief pede a carteira pública no `/meme/live`. Mantive o brief: a resposta
   já publica `tx_signature`, que entrega a carteira a quem olhar o explorer; a rota não é pública. Decisão do
   Everton se quiser esconder.
4. **Sem `risk_events` nem tabela de transições do kill switch meme** (§13 do contrato propunha): a recusa inteira
   vai para `meme_live_orders.admission`, a trava para `meme_live_kill_switch`, o resto para log + heartbeat.
5. **`sol_by_daily_cap` é conservador de propósito:** o compromisso das posições abertas entra pelo **SOL gasto**,
   não pela marca; com uma posição desvalorizada a perda não realizada conta duas vezes (na perda do dia e no
   compromisso). Nunca mais permissivo; pode recusar cedo demais. Ajustar só com decisão registrada.
6. **Devnet não exercida** (faucet `-32603` e depois rate-limited, como na T4.8). A prova de ponta a ponta com
   envio real continua pendente até haver um RPC/faucet de devnet que funcione — ou o teste pequeno na mainnet.
7. **`docs/RISK_ENGINE_MEME.md:713/714/770` e `docs/decisions/0006…:84` (commitados por T4.4/T4.8) contêm o
   literal que `forbidden_patterns.sh` recusa** (a flag meme com o valor ligado escrito por extenso, em prosa). Não são meus e não os
   toquei; o meu (`main.py`, DEPLOYMENT, ACTIVATION, estas notas) foi reescrito sem o literal. Uma varredura completa
   ficaria vermelha por eles antes de mim.
8. `checks 10–12/21` recusam todo mint sem `bundled_share`/volume orgânico medidos — hoje **todos** (o radar não
   mede `bundled_share`). Não é defeito; é a doutrina. Sem T4.2's bundled_share o executor aprova zero compras.
