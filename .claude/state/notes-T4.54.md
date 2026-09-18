# T4.54 — Tesouraria USDC → SOL (Jupiter)

## Pedido
Everton, 17/09/2026: "eu quero deixar atualizado para usar outra moeda". A carteira do robô
(`ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4`) tinha 21,33 USDC além de ~0,67 SOL; o pump.fun só
compra com SOL. Pedido: quando o SOL cair abaixo de um piso, o executor troca USDC → SOL sozinho,
dentro de tetos, com auditoria.

## Desenho (o que foi implementado)
- **Pacote novo** `packages/exchange-adapters/hunter_exchanges/jupiter/` (`client.py`, `models.py`,
  `versioned_tx.py`, `__init__.py`): cliente HTTP público da Jupiter v6 (`GET /quote`,
  `POST /swap`), sem chave, sem retry em 4xx, timeout 5 s, dataclasses tipadas com `Decimal`. Mais
  um decodificador de transação **versionada (v0)** — `hunter_exchanges.pumpfun.solana_codec`
  recusa v0 de propósito (nossas próprias transações nunca usam *lookup table*); a Jupiter sempre
  devolve v0, então esse decode ficou num módulo à parte, e resolve só as contas estáticas —
  qualquer `program_id` atrás de uma *lookup table* fica `None` (nunca resolvido, nunca confiado).
- **Regras puras** `services/meme-executor/hunter_meme_executor/treasury_rules.py`: tamanho do
  swap (duas passadas: teto ingênuo, depois encolhe para o que falta até o alvo ao preço da
  cotação), classificação de recusa da cotação (rota vazia, impacto de preço > 1 %), o verificador
  de lista branca (`JUP6…`, Token, Token-2022, ATA, System, ComputeBudget; carteira é o único
  signatário/*fee payer*) e `should_attempt` (liga/desliga, live, assinante, kill switch, piso,
  intervalo mínimo, teto diário) — tudo sem rede, sem banco, sem assinatura, 100 % testável.
- **Orquestração** `treasury.py` + `treasury_db.py`: uma vez por tique do kill switch (10 s), depois
  do saldo de SOL já ter sido relido. Lê o USDC da ATA pela `ChainReader` já existente, cota,
  redimensiona, monta a transação pela Jupiter, **verifica antes de assinar**, simula
  (`simulateTransaction`, `sigVerify=false`), assina com o `MemeSigner` de sempre, envia só se
  `allow_send=True` (isto é, `live` ligado) e confirma por `getSignatureStatuses`. Uma linha em
  `meme_treasury_swaps` por tentativa, do primeiro `quoted` até `confirmed`/`failed`/`refused`.
- **Migração** `0051_meme_treasury_swaps` (`down_revision = 0050`), tabela nova, sem RLS (padrão
  `meme_wallet_trades`), `DELETE` para ninguém, downgrade recusa com linha existente. Modelo ORM
  espelhado em `packages/core/hunter_core/db/models/meme_treasury.py`. `HEAD_REVISION` de
  `test_migrations.py` foi para `0051`; os testes de `test_migration_0050.py` agora sobem só até a
  própria revisão (`REVISION`, não `head`) antes do `downgrade -1`, porque `0051` passou a existir
  em cima dela — a checagem `alembic check` contra o *head* completo ganhou seu próprio banco
  isolado nesse arquivo, sem interferir na sequência de downgrade.
- **Config**: 7 flags `MEME_TREASURY_*` (`config.py`, mesmo padrão `parse_flag`/`Decimal` do resto).
  Todas com fallback seguro em valor ilegível (nunca recusam o boot — são parâmetros de tamanho,
  não os cinco números de política).
- **Heartbeat**: campo `treasury` (json: `enabled`, `sol_floor`, `sol_target`, `last_swap_at`,
  `last_result`, `wallet_usdc`).
- **Fio único em `main.py`**: um `await treasury_once(ctx)` dentro de `kill_switch_once`, logo
  depois do `wallet_refresh_once` (do qual depende). Nada mais mudou em `main.py`/`entries.py`/
  `wake.py`.

## O que é fail-closed
- Desligada por padrão (`MEME_TREASURY_ENABLED=false`).
- Exige `live` ligado **além** da própria flag — nunca troca em papel.
- Kill switch travado (`TRADING_DISABLED`/`EMERGENCY`) barra a tentativa antes de qualquer leitura.
- Cotação vazia ou impacto de preço > 1 % é recusada antes de montar qualquer transação.
- Um `program_id` atrás de uma *lookup table* é recusado, nunca resolvido/confiado.
- Qualquer programa fora da lista branca é recusado (`program_not_allowed:<id>`).
- Mais de um signatário, ou *fee payer* diferente da carteira, é recusado.
- Falha de leitura, cotação, simulação ou confirmação nunca reenvia sozinha — a tentativa termina
  e o próximo tique (respeitando o intervalo mínimo) tenta de novo.
- `DELETE` em `meme_treasury_swaps` não existe para nenhum papel — cada linha é evidência.

## O que **não** foi testado contra a mainnet (limitação desta sessão)
Este sandbox não tem acesso de saída à rede (`curl` para `quote-api.jup.ag` deu conexão recusada).
Por isso:
- As fixtures de `packages/exchange-adapters/tests/fixtures/jupiter/` são **sintéticas** — no
  formato documentado da API v6 (que eu conheço do treinamento), não uma captura real de
  `GET /v6/quote`. Está marcado no próprio arquivo (`_fixture_note`).
- A transação versionada que os testes de `versioned_tx.py` decodificam é **construída em
  processo** pelo próprio teste (formato de wire do Solana v0, que eu tenho confiança de estar
  correto, mas não foi comparado byte a byte com uma resposta real da Jupiter). Nenhuma chave de
  carteira foi usada ou procurada para isso, como pedido.
- O caminho `simulateTransaction` → assinar → `sendTransaction` → confirmar nunca rodou contra uma
  RPC real nesta sessão — só a matemática de tamanho, a classificação de recusa e o verificador de
  lista branca foram provados (23 testes unitários puros, offline).
- **Recomendação antes de ligar em produção:** gravar pelo menos uma cotação real
  (`GET /v6/quote`, sem carteira, sem risco) para confirmar que o formato assumido bate, e rodar
  uma simulação (`--simulate-only`, no espírito do `infra/scripts/meme_simulate_trade.py`) com o
  endereço público da carteira antes de ligar `MEME_TREASURY_ENABLED=true` de verdade.
- Não toquei `docs/DATABASE.md` (deveria ganhar uma entrada para `meme_treasury_swaps`, não fiz por
  tempo — a tabela e as constraints estão documentadas na migração e no modelo ORM).

## As linhas exatas que o Everton adiciona no `.env` da VPS para ligar
```
MEME_TREASURY_ENABLED=true
# opcionais — os valores abaixo são o padrão, só escreva a linha para mudar:
# MEME_TREASURY_SOL_FLOOR=0.30
# MEME_TREASURY_SOL_TARGET=0.60
# MEME_TREASURY_MAX_USDC_PER_SWAP=25
# MEME_TREASURY_MAX_USDC_PER_DAY=50
# MEME_TREASURY_MAX_SLIPPAGE_BPS=50
# MEME_TREASURY_MIN_INTERVAL_S=600
# MEME_TREASURY_JUPITER_BASE_URL=https://lite-api.jup.ag/swap/v1   (T4.54b; com chave: https://api.jup.ag/swap/v1)
```
Subir com `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update`. Exige
`ENABLE_MEME_LIVE_TRADING` já ligada (a tesouraria nunca troca em papel). Desligar: apagar a
primeira linha (ou pôr `false`) + `compose.sh update`, ou `touch
/opt/project-hunter/run/meme/meme.kill` (para tudo, tesouraria incluída, na hora).

## Comandos e resultado (uv run pytest)
```
timeout 590 uv run pytest packages/exchange-adapters/tests/unit/test_jupiter_client.py \
  packages/exchange-adapters/tests/unit/test_jupiter_versioned_tx.py -q -m "not live"
14 passed

timeout 590 uv run pytest services/meme-executor/tests/test_treasury_config.py \
  services/meme-executor/tests/test_treasury_rules.py \
  services/meme-executor/tests/test_treasury_db.py -q -m "not live"
12 + 23 + 5 passed

timeout 590 uv run pytest packages/core/tests/integration/test_migration_0051.py -q
9 passed
timeout 590 uv run pytest packages/core/tests/integration/test_migration_0050.py -q
8 passed
timeout 580 uv run pytest packages/core/tests/integration/test_migrations.py -q
(full file) passed

timeout 590 uv run pytest services/meme-executor/tests packages/exchange-adapters/tests \
  packages/core/tests/integration/test_migration_0050.py \
  packages/core/tests/integration/test_migration_0051.py -q -m "not live"
990 passed, 2 skipped, 7 deselected

uv run ruff check <touched files>          -> All checks passed
uv run ruff format <touched files>         -> formatted (pure reformatting)
uv run pyright <touched production files>  -> 0 errors
uv run python infra/scripts/check_file_size.py -> 0 over budget (935 files scanned)
```

## T4.54b — correções da revisão de risco (`.claude/state/review-T4.54.md`, veredito BLOCK → A–E)

Sessão de 18/09/2026, sem commit. Esta sessão **tinha rede**: gravei a cotação real e a transação
real não assinada da Jupiter (só a chave pública `ARsuJEagSE2p…`; nada assinado, nada enviado, a
chave privada não foi usada nem procurada). `quote-api.jup.ag/v6` **não resolve mais** (DNS, curl
exit 6); `lite-api.jup.ag/swap/v1` e `api.jup.ag/swap/v1` respondem 200 com o mesmo formato v6.

### O que a Jupiter realmente emite (USDC → SOL, `wrapAndUnwrapSol`, 1 USDC)
`ComputeBudget.SetComputeUnitLimit(122885)`, `ComputeBudget.SetComputeUnitPrice(813768)` (= 0,0001
SOL de prioridade), `AssociatedToken.CreateIdempotent` da ATA WSOL própria (mint atrás da ALT),
`JUP6.route` (`e517cb977ae3ad2a`; 19 bytes finais = `in_amount 1000000, quoted_out 9487602,
slippage_bps 50, platform_fee_bps 0`), `Token.CloseAccount(9)` da ATA WSOL → carteira. **Nenhuma
instrução System** — o `Transfer`+`SyncNative` do wrap só existe quando SOL é a entrada. Fixtures:
`services/meme-executor/tests/fixtures/jupiter_{quote,swap}_usdc_to_sol_real.json` e
`packages/exchange-adapters/tests/fixtures/jupiter/quote_usdc_to_sol_real.json`.

### Cada correção
- **A — verificador** (`hunter_meme_executor/treasury_verify.py`, novo; saiu de `treasury_rules`):
  instrução a instrução, como `pumpfun/verify.py`. System **recusado** (`system_program_not_allowed`);
  ComputeBudget só limite/preço, sem duplicata, `limite × preço ≤ 0,005 SOL`
  (`priority_fee_above_cap`); ATA só `Create`/`CreateIdempotent`, pagador e dono = carteira, ≤ 3;
  Token/Token-2022 só `CloseAccount`(9)/`SyncNative`(17)/`InitializeAccount*`(1/16/18) na ATA WSOL
  própria com destino/autoridade = carteira (discriminador decodificado; `Transfer`(3) →
  `token_instruction_not_allowed:3`); `JUP6` exatamente uma `route`/`shared_accounts_route`
  (discriminador Anchor conferido contra os bytes reais), autoridade = carteira, origem = ATA USDC,
  destino = ATA WSOL, sem destino de terceiro (`route_third_party_destination`), sem conta de taxa,
  `in_amount == usdc_atoms`, `quoted_out ≥ outAmount`, `slippage_bps ≤ teto`, `platform_fee_bps == 0`.
  **Limite documentado:** os args da `route` vêm depois de `Vec<RoutePlanStep>` (enum `Swap` com
  100+ variantes, impossível manter tabela) e são lidos do fim; o Anchor tolera bytes extras, então
  um builder hostil poderia anexar uma cauda falsa — por isso implementei também a **opção 2 da
  revisão**: `simulateTransaction` com `accounts=[carteira, ATA USDC]` (`jsonParsed`;
  `tx_rpc.simulate_transaction` ganhou o parâmetro `accounts` e `SimulationResult.accounts`) e o
  invariante puro `check_simulated_balances` (`USDC_depois ≥ USDC_antes − pedido`, `SOL_depois ≥
  SOL_antes + otherAmountThreshold − 0,01 SOL`), com saldos "antes" relidos na hora; violação →
  `simulation_usdc_overspent`/`simulation_sol_short`, nada assinado.
- **B — cotação** (`treasury_rules.validate_quote`, chamada em `treasury._quote` nas duas cotações):
  mints, `inAmount == pedido`, `slippageBps == cfg`, `otherAmountThreshold ≥ floor(out × (1 −
  bps/10000))` → `quote_mismatch:<campo>`. **Unidade de `priceImpactPct`: fração** (2 M USDC →
  `0.00333` com saída 0,34 % abaixo do spot; se fosse percentual leria `0.33`). Constante renomeada
  `MAX_PRICE_IMPACT_FRACTION = 0.01` (= 1 %), documentada; `config.py` corrigido (o slippage agora
  **é** decodificado da instrução; o teto diário conta `submitted`; o alvo é o efetivo).
- **C — teto diário e reconcile** (`treasury_db.usdc_committed_last_24h` soma `submitted` +
  `confirmed`; `submitted_swaps`; `treasury_reconcile.reconcile_once`, novo, roda no tique antes de
  qualquer tentativa nova): `getSignatureStatuses` em lote → `classify_submitted` puro
  (`confirmed`/`failed`/`pending`; sem status e > 180 s = `failed`); confirmado → relê a carteira e
  grava `sol_out_filled`/`wallet_sol_after`. O `_confirm` do envio agora espera no máximo
  `min(confirm_timeout_s, 20 s)` e **não** marca `failed` por estouro (fica `submitted`, contado);
  erro on-chain marca `failed` na hora.
- **D — flag antes de tudo** (`treasury.treasury_once`): `if not enabled: return` como primeira
  linha (sem sessão, sem RPC, sem HTTP — provado com um `session_factory` que levanta ao ser
  chamado); o resto em `try/except Exception` que loga `meme_treasury_tick_failed`, incrementa
  `rpc_errors` e nunca re-levanta para o `TaskGroup`. Sem `live`/assinante também não lê nada.
- **E — alvo** (`treasury_rules.effective_sol_target`): `cap = wallet_max_sol − max_sol_per_trade`
  (hoje 0,72 − 0,02 = 0,70); alvo configurado acima do cap é **recusado por nome**
  (`target_above_wallet_max`) antes de qualquer cotação (não silenciosamente reduzido — o operador
  vê no heartbeat e corrige o `.env`); e, depois da cotação, `wallet + out > wallet_max_sol` também
  recusa com o mesmo nome.
- **F — endpoint**: `MEME_TREASURY_JUPITER_BASE_URL` (padrão `https://lite-api.jup.ag/swap/v1`);
  `JupiterClient.DEFAULT_JUPITER_BASE_URL`; `main.build_context` passa a URL do config.

`treasury.py` foi dividido: `treasury.py` (tique, gates, tamanho, cotação), `treasury_send.py`
(verificar → simular+invariante → assinar → enviar → confirmar), `treasury_reconcile.py`,
`treasury_verify.py`, `treasury_rules.py` — todos ≤ 350 linhas.

### Testes (nomes)
- `test_treasury_verify.py` (25): `test_the_real_jupiter_transaction_verifies_and_is_decoded_by_name`,
  `test_the_anchor_discriminators_match_the_bytes_jupiter_emitted`,
  `test_the_real_transaction_has_no_system_instruction`,
  `test_a_system_transfer_to_a_foreign_key_is_refused`, `test_a_token_transfer_out_of_the_usdc_ata_is_refused`,
  `test_a_route_for_the_whole_balance_is_refused`, `test_a_route_with_ten_thousand_bps_of_slippage_is_refused`,
  `test_a_route_promising_less_than_the_quote_is_refused`, `test_a_route_with_a_platform_fee_is_refused`,
  `test_a_route_whose_destination_is_not_our_wsol_ata_is_refused`, `test_a_route_with_a_third_party_destination_is_refused`,
  `test_a_route_whose_authority_is_not_the_wallet_is_refused`, `test_an_unknown_route_discriminator_is_refused`,
  `test_a_close_account_paying_someone_else_is_refused`, `test_an_ata_created_for_someone_else_is_refused`,
  `test_a_priority_fee_above_the_cap_is_refused`, `test_a_second_route_instruction_is_refused`,
  `test_a_message_without_a_route_is_refused`, `test_a_foreign_program_is_refused_by_name`,
  `test_a_program_behind_a_lookup_table_is_refused_not_trusted`, `test_a_fee_payer_that_is_not_the_wallet_is_refused`,
  `test_more_than_one_signer_is_refused`, `test_a_zero_blockhash_is_refused`,
  `test_a_compute_budget_instruction_that_is_not_limit_or_price_is_refused`,
  `test_a_shared_accounts_route_is_decoded_by_its_own_layout`.
- `test_treasury_rules.py` (29): + `test_a_quote_that_matches_the_request_is_valid`,
  `test_the_real_quote_threshold_is_out_amount_times_one_minus_slippage_floored`,
  `test_a_quote_that_drifts_from_the_request_is_refused_by_name[5 casos]`,
  `test_a_target_below_the_wallet_ceiling_is_kept`, `test_a_target_above_the_wallet_ceiling_is_capped_and_named`,
  `test_a_simulation_that_spends_exactly_the_request_passes`,
  `test_a_simulation_that_drains_more_usdc_than_requested_is_refused`,
  `test_a_simulation_that_hands_back_less_sol_than_the_threshold_is_refused`.
- `test_treasury_tick.py` (17, novo): `test_with_the_flag_off_the_tick_opens_no_session_and_makes_no_call`,
  `test_a_failure_inside_the_tick_is_logged_and_counted_never_raised`, `test_without_live_or_signer_nothing_is_read_at_all`,
  `test_a_target_above_the_wallet_ceiling_is_refused_before_any_quote`,
  `test_the_size_is_capped_by_the_effective_target_not_the_configured_one`,
  `test_a_quote_for_another_amount_is_refused_before_the_builder`,
  `test_the_reconcile_settles_a_submitted_row_from_the_chain[5 casos]`,
  `test_simulated_balances_reads_the_json_parsed_pair`, `test_simulated_balances_refuses_anything_it_cannot_read[5]`.
- `test_treasury_db.py` (integração): `test_usdc_committed_last_24h_counts_submitted_and_confirmed_in_the_window`
  (confirmed 12 + submitted 5 = 17; quoted/failed/30 h fora; `submitted_swaps` devolve só a pendente).
- `test_treasury_config.py`: `test_the_jupiter_base_url_defaults_to_the_keyless_lite_endpoint`.
- `test_jupiter_client.py`: `test_the_default_base_url_is_the_live_keyless_endpoint`,
  `test_quote_parses_the_real_capture_and_its_price_impact_is_a_fraction`.

### O que ainda precisa da prova ao vivo (§6 da revisão)
1. `simulateTransaction` da transação real **com `accounts`** contra a RPC de produção, sem assinar:
   conferir que `value.accounts` vem `jsonParsed` no formato que `simulated_balances` lê (carteira:
   `lamports`; ATA: `data.parsed.info.tokenAmount.amount`), que o USDC cai exatamente 1,000000 e o
   SOL sobe ≥ `otherAmountThreshold` − 0,01. Se a RPC pública não devolver `accounts`, o invariante
   recusa tudo (`simulation_accounts_unreadable`) — fechado, mas a feature não troca.
2. A primeira troca real de ~1 USDC com `MEME_TREASURY_MAX_USDC_PER_SWAP=1`,
   `MEME_TREASURY_MAX_USDC_PER_DAY=1`, `MEME_TREASURY_SOL_FLOOR=0.70`, `MEME_TREASURY_SOL_TARGET=0.70`
   (alvo ≤ cap 0,70 — `0.72` seria recusado por nome agora), conferindo assinatura no Solscan, linha
   `confirmed`, e o reconcile numa linha `submitted` forjada por estouro.
3. Rota `shared_accounts_route` real (a captura de hoje veio como `route`): o layout de contas está
   de acordo com o IDL v6, mas só foi exercido com uma mensagem sintética.

### Comandos (T4.54b)
```
timeout 590 uv run pytest services/meme-executor/tests packages/exchange-adapters/tests -q -p no:cacheprovider -m "not live"
1068 passed, 2 skipped, 7 deselected in 143.77s (0:02:23)   # inclui test_treasury_db (Docker)
uv run ruff check <16 tocados> -> All checks passed ; ruff format --check -> 16 already formatted
uv run pyright <produção + testes tocados> -> 0 errors, 0 warnings
uv run python infra/scripts/check_file_size.py -> scanned 946 files; 0 over budget
```
Árvore compartilhada: `config.py` foi refatorado em paralelo pelo agente da T4.55 (`config_env.py`,
`send_tuning.py`) — as minhas linhas (`treasury_jupiter_base_url`, docstrings) sobreviveram; nada
dele foi tocado por mim.
