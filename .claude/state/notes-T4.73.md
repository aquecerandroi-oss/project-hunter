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
