# Notas T4.29a — venda de uma posição migrada na PumpSwap (16/09/2026)

Execução: 2026-09-16, ~14:50–15:30 UTC (11:50–12:30 BRT). Papel: engenheiro de integração com
exchanges. Sem commit (pedido do brief é só implementar + reportar). Nenhum `.env*` lido ou escrito.
Nenhuma chave gerada ou usada. **Nenhum `sendTransaction`** — só leituras públicas (`getAccountInfo`,
`getMultipleAccounts`, `getTokenAccountBalance`, `getSignaturesForAddress`, `getTransaction`,
`getTokenLargestAccounts` — este último recusado com 429) contra `api.mainnet-beta.solana.com` e
`frontend-api-v3.pump.fun` (GET público, sem chave), mais `raw.githubusercontent.com`/`api.github.com`
para a IDL. `ENABLE_MEME_LIVE_TRADING` não aparece ligada em arquivo nenhum tocado.

## 0. Gatilho

`obsidian/06-DECISIONS/2026-09-12-teste-pequeno-meme-real.md`, item "O que continua fora": uma
posição que migra para a PumpSwap ficava `open` com `blocked: pumpswap_sell_not_implemented` — o
único bloqueador nomeado para o estágio 2 (US$ 1 000/operação).

## 1. O que foi lido, nesta ordem

1. `docs/PUMPFUN.md`, `docs/RISK_ENGINE_MEME.md` (§1 escopo, §9 execução, §10 papel), `docs/PUMPFUN-ONCHAIN.md`
   (§2 PumpSwap completo, §5 limites de RPC).
2. `packages/exchange-adapters/hunter_exchanges/pumpfun/{decode,global_state,quote,tx,verify,
   solana_codec,trade_event}.py` — o molde que este pacote inteiro imita.
3. `services/meme-executor/hunter_meme_executor/{exits,build,chain}.py` — o caminho de saída da
   curva e onde `pumpswap_sell_not_implemented` era emitido.
4. `services/meme-worker/hunter_meme_worker/pool_mark.py` +
   `packages/indicators/hunter_indicators/meme/pool.py` — o "tape mark" de papel do T4.11 (EXP-M4);
   não reutilizável diretamente para uma venda real (é baseado na fita `swap-api`, por participação,
   não numa leitura on-chain de reservas), mas confirmou a tabela de taxas por faixa de mcap que a
   PumpSwap documenta publicamente.
5. `.claude/state/notes-T4.8c.md` — a metodologia de captura (ler a IDL on-chain via
   `createWithSeed`, decodificar zlib, registrar sha256, tentar simular impersonando uma carteira
   real via `sigVerify=false`).

## 2. IDL — fonte e hash

- **On-chain, lida ao vivo** em 16/09/2026 (slot 447585704): conta
  `5fLnXNNoZcZt9Qku6HARM3un3Ttm2cGsR7gN9Zp1R7h3` (`createWithSeed(find_program_address([], pAMMBay...),
  "anchor:idl", pAMMBay...)`). Descomprimida (zlib): 51 167 bytes, **sha256
  `e16ac8008908911575241a25cad33bed8d2da2153f0d726790065fd467b90ff4`**. 27 instruções, 7 tipos de
  conta (`BondingCurve, FeeConfig, GlobalConfig, GlobalVolumeAccumulator, Pool, SharingConfig,
  UserVolumeAccumulator`). Fixture: `tests/fixtures/pumpswap/t429a_idl_pump_amm_onchain.json`
  (+ `t429a_rpc_idl_account_raw.json`, a resposta crua).
- **GitHub `pump-fun/pump-public-docs`, `idl/pump_amm.json`, `main`** no momento da leitura, commit
  `81091419e4457566469d4e2a27f64ed84d42419c` (16/09/2026), sha256
  `2091433899b07d003d98118ae6cd3c628960fd393b40710b6e15bce6d0e7f2d1`. Está à frente da conta
  on-chain (`boost_authority`/`boost_enabled`, `creator_fee_configurable`/
  `max_configurable_creator_fee_bps` em `GlobalConfig`; `virtual_quote_reserves`/`creator_fee_bps`/
  `can_edit_creator_fee`/`is_holder_reward` em `Pool`) — mesmo padrão "GitHub correu na frente" que
  T4.8/T4.8c já achou para o programa Pump.
- Também lido, para comparar: o mesmo arquivo no commit `9c82f61cb711b044a17f770ab8ce9f9bdf78f333`
  (o commit que `docs/PUMPFUN-ONCHAIN.md` original citou), sha256
  `6b5c7ec4e5ef9742fa99dc57b0d75b1031b379bba02a7e1b3c5a4cad68d77e56` — já tinha `GlobalConfig`/`Pool`/
  `sell` no mesmo formato, então nada nesta tarefa depende de uma diferença entre esses dois commits
  do GitHub, só entre "GitHub" e "on-chain".

**Decisão de qual usar para decodificar:** a conta **on-chain**, porque é o que as transações reais
checam hoje; `decode.py` documenta os 4 campos extra do GitHub `main` e os lê quando o espaço da
conta permitir (confirmado: todos os 3 pools reais já têm esse espaço — ver §3).

## 3. Fixtures gravadas (mints reais, leituras ao vivo, 16/09/2026)

Mints descobertos via `GET frontend-api-v3.pump.fun/coins?complete=true&sort=created_timestamp&order=DESC&limit=10`
(REST pública, sem chave — 1 requisição) e o mint já conhecido do pacote `pumpfun`
(`frontend_api_v3_coin_graduated_raw.json`):

| mint | pool (derivado e confirmado contra a REST) | achado |
|---|---|---|
| `9tiUg9bDHpEgE3rQU8kmdMJMvMfwM81ph6WuyTapump` | `2KJ15ekBMtR2FW2esGeJrptrYLx6V9v5KEeuD8imKEz6` | `virtual_quote_reserves = 17 584 505 289` |
| `DHcQCSZ2U8QTjNWWwyuqfJbBTLCZyvtFkSeYhEYGpump` (Mayhem) | `8EpQ5ihpebcsns3DdEDoiu1WXu4GJZY9o9kSjbXAgArE` | `virtual_quote_reserves = 0` |
| `5RFwNs16ShCeSNQY9Kf5iR5esbEMsnYm7PbWGQAwpump` | `F5MkE4Yf73TkeSKLv3Mr3yrGJpFg3g7sspaCosVYyxaQ` | `virtual_quote_reserves = 17 584 505 291`; base mint é **Token-2022** |

Fixtures (`packages/exchange-adapters/tests/fixtures/pumpswap/`):
`t429a_rpc_pools_raw.json` (as 3 contas `Pool`, `getMultipleAccounts`, slot 447585957),
`t429a_rpc_globalconfig_tokens_raw.json` (`GlobalConfig` + os dois saldos de token do pool `F5Mk…`,
slot 447586178), `t429a_frontend_complete_raw.json` (a lista REST dos 10 mints), mais a IDL (§2).
Chamadas RPC totais: ~14 (bem abaixo de qualquer limite documentado em `docs/PUMPFUN-ONCHAIN.md` §5.1).

**Pool discovery verificado sem RPC:** `pool_authority = PDA(["pool-authority", mint], PUMP_PROGRAM_ID)`
(semente lida da IDL do programa Pump, instrução `migrate`, já capturada em
`tests/fixtures/pumpfun/t48c_rpc_idl_account_raw.json` — reuso read-only, sem chamada nova);
`pool = PDA(["pool", u16_le(0), pool_authority, mint, WSOL_MINT], PUMPSWAP_PROGRAM_ID)`. Bateu
byte a byte com o `pool_address` da REST nos 3 mints.

## 4. O que foi construído

| Arquivo | Conteúdo |
|---|---|
| `packages/exchange-adapters/hunter_exchanges/pumpswap/decode.py` | `GlobalConfig`, `Pool` (layout curto/estendido) |
| `.../pumpswap/pdas.py` | `pool_address`, `pool_authority_address`, `event_authority`, `fee_config_address`, `coin_creator_vault` |
| `.../pumpswap/quote.py` | `PoolReserves`, `SellQuote`, `quote_pool_sell` — produto constante + taxas de `GlobalConfig` |
| `.../pumpswap/tx.py` | `PumpSwapSellIntent`, `build_pumpswap_sell_instruction`, `build_create_wsol_ata_instruction`, `build_close_wsol_instruction`, `build_sell_message` |
| `.../pumpswap/verify.py` | `verify_pumpswap_sell_message`, `ExecutionCaps`, `UnverifiedTransaction` — mesma disciplina §9.1 |
| `.../pumpswap/sell_event.py` | `SellEvent`, `decode_sell_event`, `sell_events_from_transaction` — **não testado contra um fill real** |
| `services/meme-executor/hunter_meme_executor/chain.py` | `+PoolRead`, `ChainReader.pool()`, `ChainReader.pumpswap_global_config()` |
| `.../pumpswap_build.py` (novo) | `build_pumpswap_sell`, `BuiltPumpSwapSell`, `PumpSwapFillRecord`, `decode_pumpswap_fills` |
| `.../pumpswap_exit.py` (novo) | `handle_migrated_position` — o roteamento completo (verify→simulate→sign→send→journal) |
| `.../exit_common.py` (novo) | `mark_blocked`/`BACKOFF_S` extraídos de `exits.py` para quebrar um ciclo de import com `pumpswap_exit.py` |
| `.../exits.py` | `migrated` roteia para `handle_migrated_position` em vez de bloquear sempre; `curve_complete_awaiting_migration` só para "completa mas ainda não vista como migrada" |

## 5. Testes e resultado

```
$ uv run --package hunter-exchanges pytest packages/exchange-adapters/tests -q -m "not live"
681 passed, 12 skipped, 7 deselected

$ uv run pytest services/meme-executor/tests -q -m "not live"
83 passed, 21 skipped (Docker indisponível — 2 dos skips são os testes novos T4.29a)
```

Testes novos: `test_pumpswap_decode.py` (12), `test_pumpswap_quote.py` (8), `test_pumpswap_tx.py`
(10, inclui golden bytes do discriminador e refusals do verificador), `test_pumpswap_sell_event.py`
(7, síntese — sem fill real). Em `test_live_persistence.py`:
`test_a_migrated_position_sells_on_pumpswap` e
`test_a_migrated_position_without_a_pool_is_blocked_by_name` (estilo `FakeChain`, existem, pulam sem
Docker, mirando exatamente a instrução do brief).

## 6. Qualidade

```
$ uv run ruff check <arquivos tocados>          -> All checks passed!
$ uv run ruff format --check <arquivos tocados> -> 17 files already formatted
$ uv run pyright <arquivos de produção tocados> -> 0 errors, 0 warnings
$ uv run pyright <arquivos de teste tocados>    -> 0 errors, 0 warnings
$ uv run python infra/scripts/check_file_size.py -> scanned 891 files; 0 over budget
```

## 7. O que está provado e o que não está (resumo — detalhe em `docs/PUMPFUN.md` §8.6)

**Provado:** decode de `GlobalConfig`/`Pool` contra 3 pools reais; derivação do pool sem RPC contra
os mesmos 3 mints; instrução `sell` byte a byte (contas na ordem da IDL, discriminador confirmado);
round-trip construir→verificar; PDAs auxiliares (`event_authority`, `fee_config` da PumpSwap,
`coin_creator_vault_*`) confirmadas contra endereços reais na cadeia.

**Não provado:**
1. **Nenhuma venda foi simulada na mainnet** (`simulateTransaction`) nem enviada. Tentei achar uma
   carteira real com saldo do token para impersonar via `sigVerify=false` (o truque de T4.8/T4.8b/
   T4.8c): `getTokenLargestAccounts` voltou 429 (rate limit documentado, mesma falha que T4.8b/T4.8c
   já registraram) e o comprador achado via `getSignaturesForAddress` do pool não tinha saldo do
   token na leitura seguinte (ou era um `buy`, não um `sell`, e a ATA correspondente não existia
   ainda). **O que o dono deve rodar na VPS** (RPC próprio, sem os limites do RPC público): um script
   `--simulate-only` no molde de `.claude/state/tmp/t48c_simulate.py` — lê uma posição `migrated` real
   de `meme_live_positions`, chama `ChainReader.pool(mint)`, `pumpswap_build.build_pumpswap_sell`,
   `rpc.simulate_transaction(bytes, sig_verify=False)`; nunca `send_transaction`.
2. **Fórmula de cotação não confirmada contra um fill real** — é o formato de produto constante
   documentado (`PUMP_SWAP_README.md`), no mesmo molde da bonding curve, mas T4.8 confirmou a curva
   contra 2 transações reais lamport-exatas; aqui não há transação real para comparar.
3. **`SellEvent` nunca decodificado de uma transação real** — só um corpo sintético, byte a byte pela
   ordem que a IDL declara.
4. **Destinatário de `protocol_fee_recipient`** — o código usa `GlobalConfig.protocol_fee_recipients[0]`
   (mesmo padrão do `buyback_fee_recipients[0]` do pacote `pumpfun`); não confirmado que a cadeia
   aceita qualquer um dos 8 ou exige um específico por transação.
5. **`base_token_program`** é lido da conta do mint a cada venda (nunca hardcoded) — mas só 1 dos 3
   mints lidos foi conferido como Token-2022 vs. Token clássico; a amostra é pequena.
