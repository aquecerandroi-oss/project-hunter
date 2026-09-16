# Notas T4.29c — `FeeConfig` decodificado (taxas por tier) + venda simulada em curva com *holder rewards*

Execução: 2026-09-16, 18:00–18:40 UTC (15:00–15:40 BRT). Papel: engenheiro de integração com exchanges.
Nenhum `.env*` lido ou escrito. Nenhuma chave gerada ou lida. **Zero `sendTransaction`** em qualquer
script desta tarefa (o cliente RPC é construído com `allow_send=False` e, no roteiro novo, ainda
embrulhado por `SimulateOnlyRpc`). Nenhum arquivo de outro agente tocado (`build.py`, `exits.py`,
`chain.py` estão modificados na árvore por T4.29a — **não** entram no meu commit).

## 1. Fontes (nada de memória)

| O quê | Fonte | sha256 |
|---|---|---|
| Layout de `FeeConfig` | `pump-fun/pump-public-docs`, commit `81091419e4457566469d4e2a27f64ed84d42419c` (2026-09-14), `idl/pump_fees.json` | `d87b52305fd6b2ec487d4ba1e08a49990c23fa9b8b76092b2097df0164fa3859` |
| Regra do tier (`calculate_fee_tier`) e market cap da curva | mesmo commit, `docs/FEE_PROGRAM_README.md` | `c03c0cc79970456f9af1a54283d56bf8f752667dd95511640f42a4fb743cd72d` |
| "Nada muda nas instruções de trade em moeda HR" | mesmo commit, `docs/HOLDER_REWARDS_README.md` | `ce2a57883f342aa7f4142058e58f93e639efd64fed426b2f1f2d63d21f4cc6a1` |
| Contas de `buy`/`sell` hoje | mesmo commit, `idl/pump.json` | `ffe966c42f1af41652ee753fe2f1e3f7cd4077d7e6f49faf3138959c8b56064b` |
| IDL **on-chain** do programa de taxas | conta `6hgWp61YgGzJ9QmvxyFtLnGfA8MYgx93Hby6fdq8gG31`, slot 447 586 137 | canônico `37729b75d0891479c8cfb2d99857ad4fb5402dd1c3d28bf2aec74615292d99af` |

Regra citada, literal (`FEE_PROGRAM_README.md`, `/// rust reference: pump-fees-math::calculate_fee_tier()`):
`if (marketCap.lt(firstTier.marketCapLamportsThreshold)) return firstTier.fees;` seguido de
`for (const tier of feeTiers.slice().reverse()) if (marketCap.gte(tier.marketCapLamportsThreshold)) return tier.fees;`
— **vence o maior limiar `<=` o market cap**; a borda pertence ao tier de cima (`gte`). Market cap da
curva = `virtualSolReserves * mintSupply / virtualTokenReserves` (piso).

## 2. Captura (só leitura, RPC público, 8 chamadas)

Scripts: `.claude/state/tmp/t429c_capture{,2}.py` (6 + 2 chamadas). Nada enviado.

```
FeeConfig PDA ["fee_config", 6EF8rre…] sob pfeeUxB… = 8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt (bump 253)
rpc[1] getAccountInfo len=4097 disc=8f3492bbdb7b4c9b slot=447586137 owner=pfeeUxB…
rpc[2] getBlockTime(447586137) = 2026-09-16T18:03:47Z
rpc[3] IDL on-chain do programa de taxas: 29 instruções, SEM exotic_flat_fees (atrasada vs. GitHub)
rpc[5] programdata do programa de taxas: último deploy slot 446465969 = 2026-09-12T15:41:00Z (o upgrade do KB-0094)
pass 2: FeeConfig da PumpSwap (pAMMBay…) = 5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx, 25 tiers, slot 447586368
```

**O achado que muda a leitura do assunto:** a `FeeConfig` **da curva** tem **um único tier, limiar 0,
lp 0 / protocolo 95 / criador 30**. Na curva a taxa **não escalona** por market cap hoje — a tabela de
25 tiers da `fees.png` (420/1470/… SOL) está na `FeeConfig` **da PumpSwap**, para pools. Ou seja: a
constante datada `BONDING_CURVE_FEE_TIER_2026_05_20` estava certa; o que faltava era um jeito de
perceber o dia em que ela parar de estar. O PDA foi conferido contra o índice 12 do `sell` real de
15/09 (`t48c_rpc_tx_sell_raw.json`) — mesma conta, sem fé. Campo novo desde a T4.0d:
`exotic_flat_fees: Fees` no fim (presente nos bytes vivos e no IDL do GitHub; ausente do IDL on-chain).

## 3. Venda simulada em curva HR — o concern nº 1 da T4.8c, fechado

Rodei `infra/scripts/meme_simulate_trade.py` na mainnet (16/09 18:21 UTC). Moeda HR ainda na curva achada
pela REST (`is_holder_reward=true`, `complete=false`, quote SOL): `Bo5vHuDBfcm2bou5YobKeNR1XvgFyBzpVETndv8hUL2u`.
Detentor **real** achado na fita pública (`swap-api.pump.fun/v2/coins/{mint}/trades`), impersonado só
por `sigVerify=false` — nunca assinado, nunca enviado, exatamente como T4.8b/T4.8c.

```
fee_config 8Wf5TiAh… slot=447589440 tiers=1 [{'threshold': 0, 'fees': {lp 0, protocol 95, creator 30}}]
curve complete=False is_holder_reward=True layout=with-holder-reward-125b
token account exists=True amount=1075853044455 selling=1075853044455
verify ok=True
simulateTransaction SELL ok=True err=None units_consumed=53041 slot=447589469
   Program log: Instruction: Sell / GetFeesWithQuoteMint / TransferChecked
rpc calls=8 sendTransaction=0
```
(fixture `t429c_simulation_proof_hr_sell_raw.json`; também simulei um `buy` na moeda HR da T4.8c,
104 600 CU, idêntico ao de 15/09.)

Dois achados dentro dessa simulação:

1. `Program return: pfeeUxB… AAAAAAAAAABfAAAAAAAAAB4AAAAAAAAA` = lp 0 / protocolo 95 / criador 30 —
   **a cadeia devolveu exatamente o tier que o meu decodificador seleciona**. Checagem cruzada
   independente da regra de tier.
2. O `TradeEvent` emitido tem `holder_rewards_bps = 30` e `holder_rewards = 112 933` **iguais** a
   `creator_fee_bps`/`creator_fee`. Ou seja: **`holder_rewards` não é taxa a mais** — é a taxa do
   criador, reportada duas vezes, mudando só quem recebe. `quote_sell` com 95 + 30 bps reproduz
   `sol_amount`, `fee` e `creator_fee` **ao lamport**. Isso responde o concern nº 2 da T4.8c
   ("não sei se um valor não-zero sai da carteira do trader"): sai da mesma fatia, não de uma nova.

`sell` continua com as mesmas 14 contas do IDL (+2 *remaining* já conhecidas) numa moeda HR — como o
`HOLDER_REWARDS_README.md` afirma e agora a cadeia confirma.

## 4. O que mudou no código

| Arquivo | Mudança |
|---|---|
| `packages/exchange-adapters/hunter_exchanges/pumpfun/fee_config.py` | **novo**: `Fees`/`FeeTier`/`FeeConfig`, `decode_fee_config`, `fee_config_address` (PDA), `fees_for_market_cap` (regra exata), `bonding_curve_market_cap_lamports`, `curve_fee_bps` + `FEE_CONFIG_UNAVAILABLE_EVENT` |
| `…/pumpfun/quote.py` | docstring do `BONDING_CURVE_FEE_TIER_2026_05_20` continua a constante datada, agora explicitamente o **fallback**; o derivador mora em `fee_config.py` (quote.py estava a 358 linhas com ele dentro, acima do teto de 350) |
| `infra/scripts/meme_simulate_trade.py` | **novo**: o roteiro de simulação da T4.8c produtizado, `--simulate-only` obrigatório, `SimulateOnlyRpc` sem caminho para envio, lê `FeeConfig` e loga `meme_fee_config_unavailable` quando não dá |
| `packages/exchange-adapters/tests/unit/test_pumpfun_fee_config.py` | **novo**, 25 testes (round-trip na conta real, recusas, fronteiras de tier na tabela real da PumpSwap, fallback, a prova HR acima) |
| `infra/scripts/tests/test_meme_simulate_trade.py` | **novo**, 9 testes — inclusive o estático por AST: nenhuma chamada a `send_transaction` no módulo |
| Fixtures novas | `rpc_fee_config_raw.json`, `t429c_rpc_fee_config_amm_raw.json`, `t429c_rpc_fee_program_idl_raw.json`, `t429c_rpc_fee_programdata_raw.json`, `t429c_simulation_proof_hr_sell_raw.json` |
| `docs/ACTIVATION.md` §9b item 10, `docs/RISK_ENGINE_MEME.md` §9, `docs/PUMPFUN-ONCHAIN.md` §1.4b | comando, "o que é ok", correção da nota da T4.0d que dizia que a PDA não tinha sido derivada |

## 5. O gancho que **não** fiz (arquivo de outro agente)

`services/meme-executor/hunter_meme_executor/build.py` é da T4.29a nesta leva. O executor continua
usando `build.fee_bps(global_account)` (piso datado). O gancho, quando alguém puder editar `build.py`:

```python
# build.py
def fee_bps(global_account: GlobalAccount, *, fee_config: FeeConfig | None = None,
            market_cap_lamports: int = 0) -> FeeBps:
    fees, source = curve_fee_bps(fee_config, market_cap_lamports=market_cap_lamports,
                                 floor=BONDING_CURVE_FEE_TIER_2026_05_20)
    if source == FEE_CONFIG_UNAVAILABLE_EVENT:
        logger.warning(FEE_CONFIG_UNAVAILABLE_EVENT)      # hoje ninguém loga isso em produção
    return FeeBps(protocol=max(fees.protocol, global_account.fee_basis_points), creator=fees.creator)
```
e, em `chain.py`, um `fee_config()` com TTL (a conta muda em escala de meses, como o `Global`). Enquanto
a curva tiver **um** tier de limiar 0, `market_cap_lamports` pode ser 0 sem mudar o resultado — o que
evita uma leitura de `getTokenSupply` por trade (custo de latência, prioridade nº 1 do Everton). Se um
dia a conta ganhar um segundo tier, aí sim o market cap tem de ser real (e `mint_supply` vem do mint,
não de `BondingCurve.token_total_supply` — os dois divergem se alguém queimar).

## 6. Comandos e saídas

```
$ uv run --package hunter-exchanges pytest packages/exchange-adapters/tests -q -x -m "not live"
681 passed, 12 skipped, 7 deselected (a árvore é compartilhada; outro agente somou testes na mesma leva)
$ uv run pytest infra/scripts/tests/test_meme_simulate_trade.py services/meme-executor/tests -q -m "not live"
92 passed, 19 skipped
$ uv run ruff check <arquivos>           -> All checks passed!
$ uv run ruff format --check <arquivos>  -> 5 files already formatted
$ uv run pyright <arquivos>              -> 0 errors, 0 warnings, 0 informations
$ uv run python infra/scripts/check_file_size.py -> scanned 887 files; 0 over budget
```

## 7. Concerns

1. **Não rodei — e não posso rodar — a simulação com a carteira dele.** Não tenho carteira nem posição;
   a prova de venda HR é com um detentor **real de terceiro**, impersonado por `sigVerify=false`. A
   venda a partir do saldo dele continua sendo o item 10 do §9b, que só ele executa.
2. **`build.py` ainda não lê `FeeConfig`** (§5). Enquanto isso o executor cobra 95/30 por constante —
   que hoje é o que a conta diz, então não há erro de custo agora; há um alarme que ainda não toca.
   `meme_fee_config_unavailable` só é logado pelo roteiro de simulação, não pelo executor.
3. **`market_cap` não é exercitado em produção.** Com um tier de limiar 0, qualquer market cap dá o
   mesmo tier; as fronteiras testadas usam a tabela real da **PumpSwap** e configs sintéticas. Se a
   pump.fun ligar tiers na curva, é preciso decidir de onde vem `mint_supply` antes de confiar.
4. **`stable_fee_tiers`/`exotic_flat_fees` decodificados mas não usados** — a curva usa `fee_tiers`.
   Qual *quote mint* o programa considera "stable" não foi determinado (não há doc pública disso).
5. **O IDL on-chain do programa de taxas está atrasado** em relação ao GitHub (sem `exotic_flat_fees`,
   sem `set_exotic_flat_fees`). Segui os bytes vivos + o IDL do GitHub; se um dia a conta on-chain for
   republicada com outro layout, o teste de round-trip é quem vai acusar.
6. **A conta tem 3 920 bytes de zeros no fim** (4 097 alocados, 177 usados). Interpretei como folga
   pré-alocada para mais tiers; não tenho prova disso além do fato de serem zeros.
7. `getTokenLargestAccounts` continua limitado (429) no RPC público — achei o detentor pela fita da
   `swap-api`, não por RPC. Mesma limitação que a T4.8b/T4.8c documentaram.
