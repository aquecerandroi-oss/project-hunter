# Notas T4.8 — caminho de assinatura na curva do pump.fun, completo e INERTE

Execução: 2026-09-12, 04:30–05:25 BRT (07:30–08:25 UTC). Papel: risk-engine guardian.
Status: **DONE_WITH_CONCERNS**. Nenhum commit. Nenhum `.env*` lido ou escrito. Nenhuma chave real
gerada, colada ou logada. **Nenhuma transação enviada em rede nenhuma** (mainnet: só
`simulateTransaction` com `sigVerify=false`; devnet: faucet recusou). `ENABLE_MEME_LIVE_TRADING`
não aparece como `true` em arquivo nenhum.

## 1. Arquivos

| Arquivo | O que é |
|---|---|
| `packages/exchange-adapters/hunter_exchanges/pumpfun/solana_codec.py` (349 l.) | base58, PDA com checagem ed25519 real, ATA, `Message` legado (compile/serialize/deserialize/decompile), ComputeBudget; v0 recusado |
| `…/pumpfun/global_state.py` | decodificador da conta `Global` (25 campos) — listas de fee recipients lidas da cadeia |
| `…/pumpfun/tx.py` (item 1) | `build_buy_instruction`/`build_sell_instruction` pela IDL + as *remaining accounts* que a IDL não lista; `build_trade_message` com CU limit/price **obrigatórios**; `create_ata_idempotent`; `jito_tip_transfer`; `decode_trade_instruction` |
| `…/pumpfun/quote.py` (item 2) | cotação local inteira em lamports (fórmulas verificadas contra dois fills reais), `FeeBps` como insumo, slippage explícito e limitado, `quote_buy_for_budget`, `/global-params` + progresso |
| `…/pumpfun/trade_event.py` | `TradeEvent` Borsh (32 campos, 359/359 bytes consumidos) das inner instructions ou dos logs; tx com `meta.err` ⇒ nenhum fill |
| `…/pumpfun/verify.py` (item 5) | verificador §9.1: classifica, reconstrói a **mensagem inteira** pela intenção e compara bytes; 20+ recusas nomeadas |
| `…/pumpfun/tx_rpc.py` | RPC síncrono: simulate/send/statuses/getTransaction/blockhash/account; `send_transaction` recusado sem `allow_send=True`; preflight sempre ligado |
| `packages/core/hunter_core/execution/meme/{base58,gates,signer,journal,submit,__init__}.py` (itens 3–4) | portões §12 (`meme_gates.json`), signer (chave lida **uma vez** e removida do ambiente; nunca em repr/pickle/copy/vars), diário (uma linha por proposta, assinaturas, trava), submitter (verify → simulate → sign → send → confirm por `TradeEvent`; estados `submitted_unconfirmed`/`confirmed`/`failed` com motivo; Jito como parâmetro off) |
| `infra/scripts/meme_vm.py` (item 7) | VM1–VM9 + prova adversarial §9.1; `PENDING` nomeado para o que depende do pacote de risco |
| `infra/scripts/forbidden_patterns.sh` (item 7) | 2 padrões novos: chave Solana base58 87–88 chars atribuída; array JSON de 64 inteiros; 6 fixtures no `--self-test` |
| `packages/core/pyproject.toml`, `uv.lock` | `cryptography>=43` declarada (estava só transitiva via `pyjwt`) |
| `pyproject.toml` | marker `live_devnet` |
| Testes: `packages/core/tests/unit/execution/meme/{conftest,test_meme_gates,test_meme_signer,test_meme_submit}.py`; `packages/exchange-adapters/tests/unit/test_pumpfun_{codec,quote,trade_event,tx_parity,verify}.py`; `packages/exchange-adapters/tests/live/test_live_pumpfun_simulation.py` (item 6) | 97 testes (56 core + 41 adapter) + 2 live (skip sem `HUNTER_LIVE_DEVNET=1`) |
| Fixtures `packages/exchange-adapters/tests/fixtures/pumpfun/` | `rpc_global_account_raw.json`, `rpc_signatures_global_raw.json`, `rpc_tx_probe_raw.json` (sell real), `rpc_tx_buy_raw.json` (buy real via roteador do site), `rpc_account_4CLQ_raw.json`, `idl_pump_onchain_raw.json` (IDL da conta on-chain do programa, 40 instruções, `buy` 16 / `sell` 14 contas — mesmo conteúdo da `main` do GitHub, lida na sessão e não guardada por ser só a versão pretty-printed), `swap_api_trades_5ejA_raw.json`, `swap_build_probe4_raw.txt` (tx v0 + cotação do site), `simulation_proof_mainnet_raw.json`, `devnet_tx_{4tHDPdzf,3oJwZpCi}_raw.json` |
| Docs (item 8) | `docs/RISK_ENGINE_MEME.md` §9 (bloco "Implementado em"), `docs/PUMPFUN-ONCHAIN.md` §6b, `docs/DEPLOYMENT.md` (3 linhas: flag, `MEME_GATES_FILE`, chave) |

## 2. O que foi provado

1. **Paridade byte a byte (item 1).** `test_pumpfun_tx_parity.py`: nosso `buy` == CPI interno do
   roteador do site (`3R1GksCq…`, slot 446373814, 18 contas, dados 24 bytes) e nosso `sell` == `sell`
   direto de um bot (`5sLxc4wP…`, 17 contas), contas, flags e dados. Reconciliação lamport a lamport
   do vendedor: `delta = sol_amount − fee − cashback − taxa de rede − tip`.
2. **Achado que a IDL não documenta:** o programa exige remaining accounts
   `[4CLQeN5wrddJ9adY3GJGSTyu1AEKD4Ta14RffSy5aHud (read-only, inexistente on-chain), buyback_fee_recipient]`
   (`sell`: `user_volume_accumulator` antes). Sem a conta: `BuybackFeeRecipientMissing` (6062) na
   simulação. Nem a IDL `main` do GitHub nem a IDL on-chain (mesmas 40 instruções e listas de contas) a nomeiam; não
   é PDA sob os 4 programas nem ATA de nada envolvido. Guardada como `UNDOCUMENTED_REMAINING_ACCOUNT`.
3. **Cotação (item 2).** Fórmulas reproduzem os dois fills reais exatamente (`buy`:
   `⌊a·vsol/(vtok−a)⌋+1`; taxas `ceil` por componente 95+30 bps; cashback sai da carteira). Contra o
   `swap-build` do site (0,01 SOL exact-in, 07:46:38 UTC): site 233 388 476 471 tokens, nós
   233 388 4xx (diferença < 1e-5, teste `test_site_swap_build_quote_within_1e5`). Corpo do
   `swap-build` descoberto: `mint`, `denomination ∈ {sol, usdc}`, `amount_in`, resto tolerado.
4. **Simulação na mainnet (item 6), nunca enviada** — `simulateTransaction`, `sigVerify=false`,
   pagador real sem assinatura, 07:59:27 UTC, slot 446378553: `buy_full` ok (65 345 CU),
   `sell_full` ok (55 284 CU), `max_sol_cost − 1` ⇒ `TooMuchSolRequired` (6002) — a cotação bate o
   limiar exato do programa. Devnet: programa, `pfee` e `Global` existem, com `create_v2` às 08:01 UTC;
   `requestAirdrop` ⇒ `-32603 Internal error` (08:04 UTC) ⇒ **sem envio na devnet**; o teste
   `live_devnet` roda a simulação mainnet e, com `MEME_DEVNET_RPC_URL` + chave descartável fundada,
   o submitter real na devnet.
5. **Não-vazamento (item 3):** `repr/str/format`, heartbeat JSON, `structlog.capture_logs`, tracebacks
   de duas exceções, grafo do GC (3 saltos) — nenhum marcador da chave; pickle/copy/deepcopy/vars
   recusados; variável removida do ambiente na leitura; segunda leitura ⇒ `SecretKeyMissing`.
6. **Recusa de boot (item 3):** flag `true` sem `MEME_GATES_FILE` / arquivo inválido / portão
   vermelho / vencido / sem assinatura ⇒ `MemeLiveTradingRefused(<motivo>)` **antes** de tocar na
   chave (o env ainda a contém após a recusa).
7. **Adversarial (item 5):** amount, `max_sol_cost`, fee recipient trocado, transfer para destino
   desconhecido, tip acima do teto, programa estranho, segundo signatário, payer errado, CU acima do
   teto, blockhash zero/diferente, duas trades/nenhuma, ATA de outro dono, tx v0 do site, intenção de
   venda contra mensagem de compra — todos recusados por nome.
8. **Submitter (item 4):** 15 casos em `test_meme_submit.py` (replay por `proposal_id`, replay por
   assinatura no stream, `MemeLiveTradingDisabled` antes de assinar, expiração, transporte após envio ⇒
   `submitted_unconfirmed` + reconcile, preflight ⇒ failed, timeout ⇒ blockhash vencido ⇒ failed,
   erro on-chain, fill sem evento, trava de assinatura, Jito parâmetro, duas sessões ⇒ uma assinatura).

## 3. Comandos e saída (todos em primeiro plano, `timeout 290`)

```
$ uv run ruff format --check <32 arquivos T4.8>      → 32 files already formatted
$ uv run ruff check <arquivos T4.8>                  → All checks passed!
$ uv run pyright packages/exchange-adapters/hunter_exchanges/pumpfun packages/core/hunter_core/execution/meme infra/scripts/meme_vm.py
  → 0 errors, 0 warnings, 0 informations
$ uv run pytest packages/core/tests/unit/execution/meme packages/exchange-adapters/tests/unit/test_pumpfun_{codec,quote,verify,trade_event,tx_parity}.py packages/exchange-adapters/tests/live/test_live_pumpfun_simulation.py -q
  → 97 passed, 2 skipped in 1.76s   (skips: HUNTER_LIVE_DEVNET=1 não definido)
$ uv run pytest packages/exchange-adapters/tests -q  → 466 passed, 9 skipped in 8.57s (sem regressão)
$ bash infra/scripts/forbidden_patterns.sh --self-test
  ok - solana secret key (base58 keypair) detected in wallet_env.py (exactly one hit)
  ok - solana secret key (base58 keypair) detected in wallet.yaml (exactly one hit)
  ok - solana secret key (64-int array) detected in wallet_array.py (exactly one hit)
  ok - no hit for pubkey_only.py / disc_array.py / sig_list.py
  self-test: all patterns detected, clean/exempt fixtures pass
$ uv run python infra/scripts/check_file_size.py     → scanned 717 files; 0 over budget, 0 grandfathered
$ uv run python infra/scripts/meme_vm.py  (08:18 UTC)  exit=2
VM1   PENDING  sizing / binding_constraint / tied_limits / counterfactuals: hunter_risk_meme (RISK_ENGINE_MEME section 13) not built by any task yet
VM2   PENDING  caps per trade, mint, wallet and day: hunter_risk_meme (…) not built by any task yet
VM3   PENDING  latched daily kill switch, resume by OWNER, 10 s re-read: hunter_risk_meme (…) not built by any task yet
VM4   PASS     1 signature for 2 submits (1 send); stream event redelivered -> replayed; new blockhash = new proposal by construction (signature = f(message))
VM5   PASS     timeout after send -> submitted_unconfirmed:rpc_unreachable_after_send:RpcDown; retry -> replayed (no blind resend, 1 signature); reconcile -> confirmed
VM6   PENDING  (a) max_sol_cost short -> TooMuchSolRequired 6002, no position: True; (b) fill = TradeEvent token_amount 22628881309131, cost 990000000 lamports (event, not quote): True; (c) paper 'no later snapshot -> no fill': PENDING (paper simulator, T4.5/T4.6)
VM7   PENDING  rug during hold -> forced exit, mint ban, wallet cooldown: hunter_risk_meme (…) not built by any task yet
VM8   PENDING  rows rebuilt -> reconcile confirmed with the same signature, nothing re-sent: True; expired approval -> reservation_expired; position rebuild + chain reconciliation of meme_positions: PENDING (T4.6/T4.7 tables)
VM9   PENDING  two sessions, one signature: True (second -> signing_locked); kill switch re-read inside the effect transaction + lock order system->org->wallet: PENDING (hunter_risk_meme …)
9.1   PASS     tampered max_sol_cost refused: trade_instruction_differs_from_intent
```

Prova de simulação (script de captura, 07:59 UTC; saída completa em `simulation_proof_mainnet_raw.json`):
```
== buy_full: ok=True err=None units=65345 slot=446378553   (Instruction: Buy → GetFeesWithQuoteMint → TransferChecked → event CPI)
== buy_without_undocumented_account: ok=False err={'InstructionError': [2, {'Custom': 6062}]}  BuybackFeeRecipientMissing
== buy_idl_only_16_accounts: ok=False err={'InstructionError': [2, {'Custom': 6062}]}
== sell_full: ok=True err=None units=55284 slot=446378554
== buy_max_sol_cost_one_lamport_short: ok=False err={'InstructionError': [2, {'Custom': 6002}]}  TooMuchSolRequired
```

Varredura real do `forbidden_patterns.sh` (todos os arquivos rastreados) **não terminou em 290 s**
(4m50s, Git Bash/Windows spawna ~8 greps por arquivo × 717 arquivos; lentidão pré-existente, +2 greps
por arquivo agora). Em vez disso, `scan_file` foi aplicado a cada arquivo de produção do T4.8 pela
mesma função do script: `hits=0`.

## 4. Chamadas de rede (todas read-only)

Mainnet RPC público: 15 (`getHealth` 1, `getSignaturesForAddress` 2, `getAccountInfo` 4 —
`Global`, `4CLQ…`, conta IDL, curva —, `getTransaction` **3** (≤ 10), `simulateTransaction` 5).
Devnet RPC: 7 (`getAccountInfo` 3, `getSignaturesForAddress` 1, `getTransaction` 2, `requestAirdrop` 1
— recusado). HTTP: `swap-api.pump.fun` trades 1; `blockchain-swap.pump.fun/transactions/swap-build`
**4** (≤ 5; 422 → 422 → 400 → 200); `raw.githubusercontent.com` IDL `main` 2 (a 1ª gravação falhou por
encoding do console; refeita). Nenhum `sendTransaction`.

## 5. O que ficou de fora e por quê

- **Envio na devnet:** faucet público recusou (`-32603`). O caminho está pronto e testado
  (`test_devnet_send_when_a_funded_throwaway_key_is_provided`), mas não foi exercido em rede.
- **VM1, VM2, VM3, VM7** (sizing, caps, kill switch latched, rug): dependem do pacote
  `hunter_risk_meme` proposto na §13 do contrato, que nenhuma tarefa construiu (T4.6/T4.7 fazem a Mesa
  de papel; `paper_engine.py` tem tetos por aposta, não o motor §4–§7). O script diz `PENDING` em vez de
  fingir; partes on-chain de VM6/VM8/VM9 passam.
- **`buy_v2`/`sell_v2` (USDC/Token-2022 unificados):** fora, de propósito — o site usa `buy`/`sell`
  legados hoje e o contrato é só-SOL (§1 `unsupported_quote`).
- **Cliente Jito HTTP:** só o protocolo `BundleSender` + verificação do tip; sem implementação de
  rede (§9.3: bundle só quando duas instruções precisam ser atômicas — hoje nenhuma).
- **Composição num serviço** (`services/meme-executor/`): fora do brief; `hunter_core` não importa o
  adapter (dependência é adapter → core), então verificador, RPC e decodificador são injetados.

## 6. Concerns (cada um com cenário de falha)

1. `packages/exchange-adapters/hunter_exchanges/pumpfun/tx.py:76` — MÉDIO — `UNDOCUMENTED_REMAINING_ACCOUNT`
   é uma constante observada, não uma derivação. Cenário: o programa muda o que espera nesse slot
   (p.ex. passa a exigir a `sharing_config` real); nossa tx começa a falhar na simulação com um erro
   novo — falha fechada (nunca assina sem simulação ok), mas a compra não acontece até alguém
   reler a IDL/transações reais. Mitigação: `test_pumpfun_tx_parity.py` quebra na próxima
   recaptura de fixture; a simulação obrigatória impede dinheiro perdido.
2. `infra/scripts/forbidden_patterns.sh` (varredura completa) — BAIXO — não termina em 290 s neste
   ambiente. Cenário: o gate é pulado localmente por lentidão e uma chave só é apanhada no CI (Linux,
   onde roda em segundos). O `--self-test` e o `scan_file` por arquivo passaram aqui.
3. `packages/core/hunter_core/execution/meme/submit.py:174` — BAIXO — o submitter aceita qualquer
   `verify` callable; um serviço que injetar `lambda _: None` assinaria sem verificar. Cenário: erro de
   composição no futuro `meme-executor`. Mitigação proposta: o executor deve exigir
   `hunter_exchanges.pumpfun.verify.verify_trade_message` por construção (teste de composição na
   tarefa do serviço).
4. `docs/RISK_ENGINE_MEME.md` §9.4 regra 3 ("retentativa reusa o mesmo blockhash") — nota: o
   `journal` guarda `last_valid_block_height`, e `reconcile` declara `blockhash_expired_never_landed`
   quando a altura passou; a validade em slots continua "a fixar em T4.6 contra solana.com/docs"
   como o contrato já dizia.
5. Árvore compartilhada: `models.py`, `rest.py`, `test_pumpfun_clients.py`, `sol_price_raw.json` e
   `infra/scripts/meme_diary*.py` aparecem modificados/novos e **não são desta tarefa** (T4.6/T4.7 em
   paralelo); a suíte do adapter passou com eles presentes.
