# T4.57 — "Carteira real" no topo de `/meme/mesa`

## Pedido
Everton, 18/09/2026: "a carteira precisa estar mostrando o resultado real agora do dinheiro que
temos e o que estamos fazendo no dia e perdendo no dia". Um painel único, no topo da mesa, em
português, horário de Brasília: dinheiro agora (SOL/USDC/US$/R$, travado × reserva), hoje (compras,
vendas, ganhas/perdidas, PnL realizado e aberto, taxas+aluguel, trocas da tesouraria, os dois freios),
desde o início (agregados + maior ganho/perda + equity inicial), e as listas compactas do dia.

## API (`apps/api`)
- `hunter_api/services/fx_rate.py` (novo) — `UsdBrlRateCache`: `GET api.frankfurter.dev/v1/latest?base=USD&symbols=BRL`,
  cache de 1 h, timeout de 3 s, cai para a última leitura boa (`reason="stale"`) numa falha, ou
  `None`/`"no_fx_quote"` antes do primeiro sucesso. Nunca bloqueia a página além do timeout curto.
  Instância única (`usd_brl_cache`), mesma convenção do `JwksCache`.
- `hunter_api/repositories/meme_live_wallet.py` (novo) — `MemeLiveWalletRepository.wallet_summary()`:
  5 `SELECT`s limitados (agregados com `FILTER`, `ORDER BY ... LIMIT 1` para maior ganho/perda,
  leitura de linha única para a âncora do dia e a primeira troca da tesouraria) sobre
  `meme_live_positions`, `meme_live_orders` (taxas: `fill->>'fee'`/`network_fee_lamports`, aluguel:
  `ata_rent_lamports`/`account_rent_lamports` − `ata_rent_refund_lamports`), `meme_treasury_swaps`,
  `meme_live_kill_switch`. Nenhum laço Python somando todas as linhas.
- `hunter_api/schemas/meme_live_wallet.py` (novo) — `WalletSummaryOut` e os quatro blocos
  (`WalletNowOut`/`WalletTodayOut`/`WalletAllTimeOut` + listas compactas); todo valor que a leitura
  não sustenta é `None` com um `*_reason` nomeado ao lado, nunca zero.
- `hunter_api/services/meme_live_wallet.py` (novo) — `build_wallet_summary()`: combina o heartbeat do
  executor (`hb:meme:executor`, reaproveitando `read_executor` para status/wallet/policy/gates/perda do
  dia) + o heartbeat do radar (`hb:meme:radar.lab_sol_usd`, via `resolve_sol_usd`) + a cotação de câmbio
  + o `WalletSummaryRow`. Escolhe a equity inicial entre a âncora do dia (`meme_live_kill_switch`) e a
  primeira troca da tesouraria, a que for mais antiga, nomeando a fonte.
- `hunter_api/routers/meme_live.py` (editado) — `GET /meme/live/wallet-summary` (VIEWER+); `_heartbeat`
  passou a receber a chave como parâmetro (reaproveitado para `hb:meme:executor` e `hb:meme:radar`).
- `hunter_api/repositories/meme_live.py` (editado) — nenhuma mudança de contrato; o agregado saiu daqui
  para `meme_live_wallet.py` só para caber no orçamento de 350 linhas (ficou em 248).

## Web (`apps/web`)
- `lib/api/meme-live-wallet-types.ts` / `meme-live-wallet-actions.ts` (novos) — aliases do OpenAPI
  gerado + Server Action `pollWalletSummaryAction` (componente cliente não pode chamar `apiFetch`
  direto, mesma regra do `sellNowLiveAction`).
- `hooks/useWalletSummaryPoll.ts` (novo) — poll a cada 10 s, pausa com a aba oculta, mantém a última
  leitura boa na tela numa falha (só atualiza o motivo).
- `components/meme-live/wallet-summary-format.ts` + `wallet-summary-{now,today,all-time,lists,view,panel}.tsx`
  (novos) — painel dividido em blocos pequenos (48–95 linhas cada) para caber no orçamento de arquivo;
  `wallet-summary-view.tsx` é puro (props apenas) e concentra os testes de estado vazio; `wallet-summary-panel.tsx`
  é o único arquivo `"use client"` que chama o hook de poll.
- `app/(app)/[orgSlug]/meme/mesa/page.tsx` (editado) — `<WalletSummaryPanel orgId={orgId} />` logo
  abaixo do cabeçalho da mesa, acima das abas (topo da página, como pedido).
- `packages/shared-types/{openapi.json,src/generated/api.d.ts}` — regenerados (`pnpm gen:types`
  equivalente, offline, sem banco/Redis).

## Testes e checagens (saída real)
- `uv run pytest apps/api/tests -q -p no:cacheprovider -k "meme_live or wallet"` → **32 passed**
  (inclui os 15 novos: 5 em `test_fx_rate.py`, 10 em `test_meme_live_wallet_service.py`).
- `uv run ruff check apps/api` → All checks passed!
- `uv run ruff format --check apps/api` → 304 files already formatted.
- `uv run pyright <arquivos novos/editados>` → 0 errors.
- `uv run python infra/scripts/check_file_size.py` → 0 over budget.
- `pnpm --filter web typecheck` → limpo.
- `pnpm --filter web lint` → limpo (dois avisos pré-existentes em arquivos que não toquei).
- `pnpm --filter web test -- --run` → **1623 passed** (inclui os 2 novos arquivos: `wallet-summary-format.test.ts`
  e `wallet-summary-view.test.tsx`, cobrindo formatação, "sem posições hoje", heartbeat ausente e
  câmbio ausente).

## Pendências / decisões tomadas sem perguntar (documentadas para revisão)
- Sem harness Playwright/e2e neste repo (`grep` não achou `tests/e2e` nem dependência `playwright`) —
  nenhum screenshot spec foi adicionado; a checagem visual real (Clerk/localhost) fica para a rotina de
  Playwright já usada no projeto, fora do escopo desta tarefa.
- Equity inicial: como `meme_live_kill_switch` guarda só a âncora do dia **atual** (não histórico), a
  "equity desde o início" é honestamente rotulada por fonte (`kill_switch_anchor` ou
  `first_treasury_swap`) em vez de fingir um "dia 1" que o banco não registrou.
- Conversão de PnL acumulado (todo o histórico) para BRL usa a cotação SOL/USD **atual** do radar — a
  mesma aproximação que `meme_lab_goal.build_goal` já usa para `capital_usd`, não um cálculo novo.
