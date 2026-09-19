# T4.73 — troca à vista (spot) genérica pela Jupiter, compra na Solana por sinal da Binance

## Pedido
Everton, 19/09/2026 10:2x BRT: usar a Binance como fonte de sinal e **comprar na Solana pela
carteira** via Jupiter — "faça um teste". Generaliza a tesouraria USDC→SOL (T4.54/T4.54b,
`hunter_meme_executor.treasury*.py`, **intocada**) para qualquer par de mints, como ferramenta
manual e auditada (não é um laço automático do executor).

## O que foi feito
- `packages/exchange-adapters/hunter_exchanges/jupiter/spot.py` (62 linhas): `resolve_mint`,
  `quote`, `swap_tx` sobre `client.py` (já aceitava qualquer par desde a T4.54); exportado em
  `hunter_exchanges.jupiter` (`resolve_mint`, `spot_quote`, `spot_swap_tx`).
- `services/meme-executor/hunter_meme_executor/spot_verify.py` (337 linhas, módulo **novo**,
  `treasury_verify.py` não foi tocado): `verify_spot_swap_tx(message, intent=SpotSwapIntent(...))`
  — a mesma disciplina instrução a instrução da T4.54b, generalizada: ATAs de qualquer um dos dois
  mints pelo programa Associated Token; embrulhar/desembrulhar SOL nativo só na ATA WSOL própria e
  só quando um dos lados é SOL; rota `JUP6` com origem/destino derivados do par pedido; qualquer
  outra coisa é recusada por nome. Limite documentado: assume Token program clássico para derivar
  as ATAs (Token-2022 em qualquer ponta é recusado, não aceito por engano).
- `infra/scripts/meme_spot_swap.py` + `meme_spot_swap_{rules,plan,send,db,kill}.py` (todos < 350
  linhas): o script auditado, dry-run por padrão, `--apply` só via `compose.sh ops`. Ver "Comandos"
  abaixo para o round trip de 0,02 SOL.
- `infra/migrations/ddl/meme_spot_swaps.py` + `infra/migrations/versions/0056_meme_spot_swaps.py`:
  duas colunas `text` anuláveis (`input_mint`/`output_mint`) em `meme_treasury_swaps` — nenhum
  CHECK da `0051` nomeava USDC/SOL por valor, só por rótulo de coluna, então a tabela é reaproveitada
  (decisão tomada depois de ler a DDL da `0051`: nenhuma migração de tabela nova). ORM espelhado em
  `packages/core/hunter_core/db/models/meme_treasury.py`. `HEAD_REVISION` de
  `packages/core/tests/integration/test_migrations.py` **já estava** em `"0056_meme_spot_swaps"`
  quando eu cheguei nele (commit `7850a89c`, T4.71, previu o número desta tarefa) — a minha edição
  não teve diff porque já batia; a `0056` real (arquivos de migração) é a que este commit adiciona.
- `docs/RISK_ENGINE_MEME.md` §16.4 e `docs/ACTIVATION.md` §9i (usage). **`docs/RUNBOOK.md` não
  existe no repo** — usei `docs/ACTIVATION.md` (o doc de "o que o Everton digita e decide", onde
  `meme_simulate_trade.py` já está documentado) em vez dele; se um `RUNBOOK.md` for criado depois,
  mover a §9i para lá.
- Testes: `services/meme-executor/tests/test_spot_verify.py` (5, síntese de mensagens),
  `infra/scripts/tests/test_meme_spot_swap_rules.py` (8, matemática pura),
  `infra/scripts/tests/test_meme_spot_swap_plan.py` (3, contra a cotação real gravada),
  `infra/scripts/tests/test_meme_spot_swap.py` (4, CLI fim a fim com fakes).
  `packages/core/tests/integration/test_migration_0056.py` foi escrito por analogia ao
  `test_migration_0051.py` mas **não rodei** (precisa de Postgres via testcontainers; fora do
  comando de teste mandatado desta tarefa, e Docker tem histórico de travar nesta máquina —
  ver memória "Subagent stalls on background Bash").
- Fixture real: `packages/exchange-adapters/tests/fixtures/jupiter/quote_sol_to_wif_real.json`
  (`GET lite-api.jup.ag/swap/v1/quote`, SOL → WIF, 0,02 SOL, capturada nesta sessão, 19/09/2026).

## O que NÃO foi provado ao vivo (mesma lacuna que a T4.54 registrou)
- Nenhuma chave foi usada ou procurada nesta sessão (a instrução do brief foi seguida à risca).
- O verificador genérico foi provado contra transações **sintéticas** (mesmo método que a suíte da
  T4.54 já usa para `shared_accounts_route` — construídas em processo, formato de wire conhecido),
  não contra uma transação real de "SOL como entrada" com a chave pública da carteira.
- `simulateTransaction` com `accounts` contra a RPC real, e o caminho assinar → enviar → confirmar,
  nunca rodaram nesta sessão.

## Comandos para o teste real de 0,02 SOL ida e volta (fazer nesta ordem, na VPS)

1. **Prova mínima antes de confiar** (a §6 da revisão da T4.54, repetida para o par escolhido):
   cotação real + transação real não assinada (só a chave pública) + `simulateTransaction` com
   `accounts` conferindo o invariante de saldos. Pode ser feito com o próprio dry-run:
   ```bash
   bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
       --from SOL --to EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm --amount 0.02 \
       --reason "T4.73 prova SOL->WIF" \
       --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4
   ```
   "ok" é: `amount_cap: ok`, `impact_cap: ok`, `verify: OK`.

2. **Dry-run do round trip** (compra + cotação de venda de volta, sem tocar a carteira):
   ```bash
   bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
       --from SOL --to EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm --amount 0.02 \
       --round-trip --reason "T4.73 round trip SOL->WIF" \
       --user ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4
   ```
   Confere `round_trip_cost_fraction` (esperado: pequeno, na casa de slippage + taxa da rota).

3. **Só o Everton aplica de verdade** — interruptor de emergência `ACTIVE`, saldo de SOL cobrindo
   0,02 + taxas:
   ```bash
   bash infra/vps/compose.sh ops python infra/scripts/meme_spot_swap.py \
       --from SOL --to EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm --amount 0.02 \
       --round-trip --apply --reason "T4.73 teste real ida e volta"
   ```
   Conferir depois: as duas linhas em `meme_treasury_swaps` (`status = confirmed`,
   `input_mint`/`output_mint` preenchidos), a assinatura no Solscan, `system_events`.

## Comandos rodados nesta sessão (saída real)
```
timeout 590 uv run pytest packages/exchange-adapters/tests services/meme-executor/tests \
  infra/scripts/tests -q -p no:cacheprovider -m "not live" -k "jupiter or spot or treasury or swap"
288 passed, 1307 deselected in 35.99s

uv run ruff check <arquivos tocados>          -> All checks passed!
uv run ruff format --check <arquivos tocados> -> (após --fix/format) sem diffs
uv run pyright <arquivos tocados>             -> ver relatório final da tarefa
uv run python infra/scripts/check_file_size.py -> ver relatório final da tarefa
```

## T4.73b — correção dos 7 achados da revisão (`.claude/state/review-T4.73.md`) + segunda opinião

Guardião do motor de risco, 19/09/2026. TDD: teste falhando primeiro para cada achado, depois o
mínimo de código. Nenhum commit; nenhum `.env*` lido; nenhuma chave procurada; testes só com fakes.

### O que cada achado virou
1. **`_send.py` invariante lê a simulação** — `simulated_balances(simulation.accounts)` (parser de
   `treasury_send`, uma fonte): `accounts[0].lamports` → `sol_after`, `accounts[1]…tokenAmount.amount`
   → `token_after`; `None` → `simulation_accounts_unreadable`. Prova contra o código antigo
   (`git show 8fc9dcbe:…_send.py` carregado no scratchpad, mesmos fakes): `buy 0.02 SOL, fixture
   threshold 10402273, pós-estado OK -> ('refused', 0) refused:simulation_token_short`; novo →
   `confirmed`, `filled = 10402273` (`test_buy_leg_end_to_end_confirms_and_commits_every_step`).
2. **Timeout de confirmação** — `pending` após `CONFIRM_ATTEMPTS` (ou erro em
   `getSignatureStatuses`) → `LegResult("submitted", 0, signature)`, linha fica `submitted`, o
   script imprime a assinatura, sai com **66** e a volta nunca dispara. Prova do antigo (20 ×
   `None`): `('confirmed', 0)`, linhas `['confirmed', 'COMMIT', 'event']`.
3. **Commit por passo** — `meme_spot_swap_db.*` faz `await conn.commit()` depois de cada escrita;
   `_apply` abre `engine.connect()` **sem** `begin()`; `record_event` também commita. Teste: erro
   de RPC após `mark_submitted` deixa `['submitted', 'COMMIT']` e o resultado é `submitted`.
4. **Teto duro 0,10 + piso de carteira** — `HARD_CAP_SOL_EQUIVALENT = 0.10` checado antes do teto
   brando e ignorando `i_know` (`amount_above_hard_cap`); `classify_wallet_floor`:
   `carteira − amount − 0,01 ≥ MEME_WALLET_MIN_SOL_AFTER_SWAP` (padrão 0,30; inválido →
   `wallet_floor_invalid`), aplicado em `apply_with` na perna de compra, lido da cadeia antes da
   cotação. Dois testes antigos que codificavam "`--i-know` levanta tudo" foram ajustados.
5. **Volta com teto de impacto e releitura do interruptor** — `classify_impact_cap` roda dentro de
   `run_apply_leg` (toda perna); `apply_with` relê `read_effective_kill_switch_state` depois de
   `--hold-s`; a volta é saída (tabela da §7 de RISK_ENGINE_MEME: saídas permitidas em todo
   estado), então prossegue com o estado impresso e logado. `filled = 0` pula a volta.
6. **`spot_verify._create_ata`** — `mint is None or ata is None` → `ata_account_via_lookup_table`.
7. **`plan.verify_reason`** — `apply_with` recusa por `amount_cap_refusal`, `impact_refusal` **e**
   `verify_reason` antes do segundo `POST /swap` (teste: `swap_calls == 1`, nenhuma perna).

Refatoração necessária para testar: `_apply` virou fiação (engine/Redis/RPC/Jupiter) e a lógica
foi para `apply_with(args, *, conn, redis, chain, client, load_signer, env)`; `run_apply_leg`
devolve `LegResult(status, filled, signature)`.

### Segunda opinião da Astra (`.claude/state/astra-review-review-T4.73b-send-path.md`)
Confirmou 1–3 e o commit-as-you-go; levantou quatro pontos. Três fechados no escopo:
- **Envio ambíguo virava `failed` sem assinatura** → a assinatura é `b58encode` dos bytes ed25519
  (o id da transação Solana é exatamente isso) e `mark_submitted` acontece **antes** de
  `sendTransaction`; exceção no envio → `submitted` com assinatura, código 66
  (`test_the_signature_is_persisted_before_the_broadcast_and_a_send_error_keeps_it`).
- **`filled` da venda medido no lado errado** (delta do token, negativo → 0) → na venda,
  `filled = lamports_depois − lamports_antes` (`test_sell_leg_end_to_end_measures_the_fill_in_lamports`).
- **`refused`/`failed` saíam com 0** → 65 / 67 (`test_apply_exits_non_zero_when_the_buy_leg_is_refused_or_failed`).
- **NÃO fechado (fora do escopo de edição, `services/meme-executor/hunter_meme_executor/treasury_db.py`),
  e bloqueia o primeiro `--apply`:** `_SOL_INFLOW`, `_USDC_24H` e `_SUBMITTED` não filtram por
  mint; uma compra spot confirmada gravaria 10 402 273 átomos de WIF em `sol_out_filled` e o freio
  de perda diária (§16.3, `treasury_inflow_once`, roda a cada tick do `reconcile` mesmo com a
  tesouraria desligada) leria 10,4 M de "SOL" de entrada — trava diária nunca arma. Correção:
  `AND input_mint IS NULL` nas três consultas + teste. Registrado em RISK_ENGINE_MEME §16.4.

Observação: durante a chamada da Astra o `git status` mostrou `.env.example` e
`services/meme-worker/hunter_meme_worker/config.py` modificados por outra frente (árvore
compartilhada); não toquei em nenhum dos dois.

### Comandos rodados (saída real)
```
timeout 590 uv run pytest infra/scripts/tests services/meme-executor/tests/test_spot_verify.py -q -p no:cacheprovider -k "spot"
49 passed, 321 deselected in 3.35s          # eram 20 na T4.73

timeout 590 uv run pytest packages/exchange-adapters/tests services/meme-executor/tests infra/scripts/tests \
  -q -p no:cacheprovider -m "not live" -k "jupiter or spot or treasury or swap"
317 passed, 1307 deselected in 33.23s       # eram 288

uv run ruff check <9 arquivos tocados>           -> All checks passed!
uv run ruff format --check <9 arquivos tocados>  -> 9 files already formatted
uv run pyright <9 arquivos tocados>              -> 0 errors, 0 warnings, 0 informations
uv run python infra/scripts/check_file_size.py   -> scanned 1014 files; 0 over budget, 0 grandfathered
  (meme_spot_swap.py 317, meme_spot_swap_send.py 262, spot_verify.py 340 linhas)

uv run python <scratch>/prove_before.py    # fixture buy contra o _send.py de 8fc9dcbe
OLD (8fc9dcbe) buy 0.02 SOL, fixture threshold, simulated post-state OK -> ('refused', 0) ['insert:quoted', 'COMMIT', 'refused:simulation_token_short', 'COMMIT']
uv run python <scratch>/prove_before2.py   # 20x pending contra o _send.py de 8fc9dcbe
OLD (8fc9dcbe) 20x pending -> ('confirmed', 0) | status_calls = 20 | rows: ['confirmed', 'COMMIT', 'event']
```

