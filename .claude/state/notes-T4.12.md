# Notas T4.12 — a carteira observada (12/09/2026, início ~14:5x BRT)

Árvore limpa em `e096c0c` (T4.2f + T4.10a). Migração seguinte livre: **`0027_meme_wallets`**
(o brief dizia 0028; a 0027 é o próximo número). Endereço público a semear em
`MEME_WATCH_WALLETS`: `6nAh8drzAYfFZuTFFRgwRdV8tNndFiX1E8NGRAGzSk5F` (só endereço, nunca chave).

## 0. Leitura (o que o código já tinha)

- `hunter_exchanges.pumpfun.trade_event.trade_events_from_transaction(tx, program_id=PUMP_PROGRAM_ID)`
  decodifica o `TradeEvent` da curva (inner instructions ou logs), inclusive via roteador com
  lookup table (fixture `rpc_tx_buy_raw.json`, user `AsRQ…`, buy 977 777 777 lamports +
  fee 9 288 889 + cashback 2 933 334 + rede 88 500) e a venda direta (`rpc_tx_probe_raw.json`,
  user `sssss…` — bot público, 724 716 993 − 6 884 812 − 2 174 151 − 100 000).
- **Não existia** `getSignaturesForAddress`/`getTransaction` no `SolanaRpcClient` assíncrono
  (só o `SolanaTxRpcClient` síncrono do caminho de execução tem `get_transaction`); a fixture
  `rpc_signatures_global_raw.json` (15 entradas, mais nova primeiro, com `err`) veio da T4.0d.
- **Não existe** decodificador dos eventos `BuyEvent`/`SellEvent` da PumpSwap nem o layout
  deles no repo (só a lista de campos em `docs/PUMPFUN-ONCHAIN.md` §2.4). Decisão: um swap na
  PumpSwap é lido pelas **deltas de saldo da própria carteira** (`pre/postTokenBalances` com
  `owner = wallet`, `pre/postBalances` no índice da carteira, wSOL somado ao lado SOL), com
  `decode = 'balance_delta'` e `venue = 'pool'` só quando o programa `pAMM…` está nas contas.
  Nada é inventado: sem uma única mint com delta e um lado SOL de sinal oposto, a linha é
  `side = 'unknown'` com `raw`.
- `collect.forever` re-levanta falhas (o TaskGroup derruba o processo): o coletor de carteiras
  tem de engolir erros de RPC por ciclo, como `chain_once` faz.
- `lab*.py`/`proposals*.py`/`paper_engine.py` são só leitura para esta tarefa: o `lab_context`
  reutiliza `RuleSetSpec`, `entry_features_of`, `evaluate_entry` e `load_active_rule_sets`
  importando, com a leitura da linha de features duplicada em módulo próprio.

## 1. Desenho

- **`0027_meme_wallets`**: `meme_wallet_trades` (PK `(signature, event_index)`, dedupe por
  assinatura; `side ∈ {buy, sell, unknown}`, `venue ∈ {curve, pool}`, `decode ∈ {trade_event,
  balance_delta, none}`, `sol_lamports` = perna da curva/pool, `fee_lamports` = toda dedução
  (protocolo + criador + cashback + taxa de rede quando a carteira é a pagadora), `raw`,
  `lab_context`, `hype_score`, `line_reason`) e `meme_wallet_positions` (derivada, FIFO,
  `mark_source ∈ {curve_snapshot, tape}` + `mark_reason`, R com risco = SOL gasto,
  `unmatched_sell_tokens` para vendas sem compra observada). `meme_lab_scoreboard_v1` é
  recriada com `UNION ALL` de uma linha por carteira × dia (`wallet:<8>`, `kind =
  'real_observed'`, `pnl_usd NULL` — nunca um dólar que ninguém observou). Descida recusa com
  `meme_wallet_trades` povoada.
- Adaptador: `pumpfun/wallet_fills.py` (puro) + `SolanaRpcClient.get_signatures_for_address`
  / `get_transaction`.
- Worker: `wallets.py` (laço 30 s, bucket próprio 2 req/s), `wallet_positions.py` (FIFO puro),
  `wallets_repo.py`, `wallets_lab.py`; `MEME_WATCH_WALLETS` em `config.py`.
- API: `repositories/services/schemas/meme_wallets.py`; `MemeLabOut.real_observed` e
  `DeskListOut.real_observed` (campos novos, opcionais — nada renomeado).
- Diário: seção "2b. Operações reais (carteira observada)".
- Docs: DEPLOYMENT (`MEME_WATCH_WALLETS`), T4-MEME-RADAR §T4.12, DATABASE **§39** (o brief
  dizia §40; §39 é o próximo livre — anotado).

## 2. Comandos e saídas (incremental — horários em BRT = UTC − 3)

### 2.1 Leitura e fixtures (~15:0x BRT)
- `uv run python - < inspect_fixtures.py` → `rpc_tx_buy_raw.json`: slot 446369982, blockTime 1789197249,
  user `AsRQ…`, buy via `FLASHX…` (v0, lookup table 4+9); `rpc_tx_probe_raw.json`: slot 446373814,
  user `sssss…`, sell; `rpc_signatures_global_raw.json`: 15 entradas, mais nova primeiro, `err` presente.
- Decodificação real: buy `sol 977777777 fee 9288889 creator 0 cashback 2933334 quote_mint 1111…`,
  `meta.fee 88500`, pagador = user; sell `sol 724716993 fee 6884812 cashback 2174151 meta.fee 100000`.

### 2.2 Estático (~16:4x BRT)
- `uv run ruff check --fix <27 arquivos>` → `Found 1 error (1 fixed, 0 remaining)`; `ruff format` → 6 reformatados.
- `check_file_size.py` (1ª) → `wallets.py 380 > 350`, `rpc.py 367 > 350` → cortes: `wallets_state.py`
  (WalletsWatcher/build_wallets) e `rpc_wallet.py` (`WalletRpc` sobre `SolanaRpcClient.call`).
  Depois: `wallets.py 299`, `rpc.py 308`, `rpc_wallet.py 90`, `wallets_state.py 113`.
- `check_file_size.py` (final) → `4 over budget`, **nenhum meu** (`meme-executor/repo.py 437`,
  `meme_desk_out.py 355`, `meme-executor/exits.py 353`, `settings.py 352` — agentes paralelos).
- `uv run pyright <módulos + testes meus>` → `0 errors, 0 warnings` (após corrigir `_lab_context`
  com `cast` explícito e `gate_row_from(r: Mapping[Any, Any])`).
- `uv run ruff check` (repo) → `All checks passed!`; `ruff format --check` nos 33 arquivos meus →
  `33 files already formatted` (o `--check .` do repo acusa 10 arquivos de outros agentes).

### 2.3 Testes (~17:0x–17:5x BRT)
- `uv run pytest packages/exchange-adapters/tests/unit/test_pumpfun_wallet_fills.py -q` → **8 passed**
  (compra/venda reais lamport-exatas; carteira alheia → `unknown/no_trade_event_for_wallet`; tx falha →
  `()`; `{}` → `malformed_transaction`; bytes do evento truncados → `event_error`; PumpSwap sintético
  buy/sell por deltas; `sol_leg_sign_mismatch`/`no_token_delta`; `WalletRpc` offline: 3 requisições).
  1ª rodada falhou 1 (truncar a string base58 quebrava o discriminador; corrigido truncando os bytes).
- `uv run pytest services/meme-worker/tests/test_wallet_positions.py -q` → **6 passed** (FIFO 2,5 SOL,
  fecho, venda órfã/parcial, marca fita×curva×curva encerrada, `fee_pct_from_raw`, vazio).
- `uv run pytest apps/api/tests/unit/test_meme_wallets_service.py -q` → **5 passed** (1ª rodada);
  depois o `routers/meme_live.py` de outro agente (import `hunter_core.errors` inexistente) quebrou a
  coleta de `apps/api/tests`; `--noconftest` → **5 passed**.
- `uv run pytest infra/scripts/tests/test_meme_diary.py -q` → **5 passed** (1ª rodada falhou por
  esperar 7 casas; o diário arredonda a 6).
- Container (`timeout 590`): 1ª tentativa → `alembic … Multiple head revisions` (dois agentes criaram
  `0028_meme_live` e `0028_meme_moonshot` sobre a minha 0027). Prova independente com runner de rascunho
  em `0027_meme_wallets`: `PASS test_the_loop_appends_real_fills_dedupes_by_signature_and_derives_the_positions`,
  `PASS test_an_rpc_failure_is_counted_and_never_raised_and_the_app_role_only_reads`, `ledger rows: 3`,
  `guard refused: True`, descida limpa → `0026_meme_lines`, `wallet tables left: 0`, vista existe e não usa
  posições (`1 0`), volta → `0027_meme_wallets`, vista usa posições de novo (`1`), grants
  `hunter_app SELECT` / `hunter_worker INSERT,SELECT,UPDATE` nas duas tabelas.
  (1ª rodada do runner: a fita via `repo_tape.insert_trades` falhou porque o agente da moonshot acrescentou
  `program` ao `TradeRow` — o teste passou a inserir a fita por SQL das colunas da 0021.)
- Heads fundidas (0027 → 0028_meme_live → 0029_meme_moonshot):
  `uv run pytest services/meme-worker/tests/test_wallets_persistence.py -q` → **2 passed in 22.15s**
  (a asserção dos conjuntos virou invariante: todo conjunto `active` lido do banco recebeu veredito —
  a 0028/0029 aposentou `operator/1`).
- `uv run pytest packages/core/tests/integration/test_migrations.py -k 0027` → **3 passed** (após dois
  erros meus: string ISO num parâmetro `timestamptz` → `datetime(…, tzinfo=UTC)`; `signature` duplicada
  na chamada do helper); `-k 0026` (re-estagiados na própria 0026) → **3 passed**.
- `uv run pytest services/meme-worker/tests -m "not integration"` → **177 passed**;
  `packages/exchange-adapters/tests/unit -k pumpfun` → **148 passed**.

### 2.4 Tipos e estado (~17:2x BRT)
- `pnpm gen:types` → `openapi-typescript 7.13.0 … api.d.ts [445.8ms]`; `RealObservedOut`/
  `WalletPositionOut`/`real_observed` presentes (8 ocorrências); o diff do arquivo gerado inclui
  também os schemas dos outros agentes (arquivo partilhado).
- `git status --porcelain` dos meus arquivos: 19 `M` + 19 `??` (lista no relatório).

## 3. Concerns
- `test_migrations.py` é editado por três agentes ao mesmo tempo (HEAD_REVISION 0026 → 0028 → 0029;
  constantes `MEME_LINES_REVISION`/`MEME_WALLETS_REVISION` duplicadas por um instante — removi a minha
  cópia). O `pyright` do arquivo acusou `MEME_LIVE_REVISION` indefinido (linha do outro agente) numa
  rodada; na última rodada, `0 errors`.
- A API não coleta (`hunter_core.errors` inexistente, `routers/meme_live.py`) enquanto o agente da 0028
  não terminar; o meu teste passa com `--noconftest`. `pnpm gen:types` rodou **antes** desse import.
- PumpSwap: sem o layout de `BuyEvent`/`SellEvent` no repo, o `pool` é lido por deltas de saldo
  (`decode = 'balance_delta'`, sem taxas discriminadas) e provado só com transação **sintética**.
- `getSignaturesForAddress` com `until`: se uma carteira fizer mais de `MEME`-página (100) transações
  entre dois ciclos de 30 s, as mais antigas ficam fora (o nó devolve as 100 mais novas). Declarado.
- O `realized_today_sol` da seção Reais soma o PnL das posições com `last_trade_at` no dia (a posição é
  a unidade) — documentado no repositório.
