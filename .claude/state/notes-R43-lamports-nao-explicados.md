# R43 — os 2 860 040 lamports não explicados da primeira compra real

Data: 2026-09-16. Escopo: leitura (cadeia + `SELECT` na VPS) + teste unitário em arquivo novo.
Nada do executor foi tocado (T4.45 está editando `services/meme-executor/**`).

## 1. A transação de compra, instrução por instrução

`SwjKQmyw…cjEyK7` (buy, TAXCOIN `7s4dKmpv…GAxi8`, `fee = 9 000`, CU consumidas 95 520):

| # | programa | instrução |
|---|----------|-----------|
| 0 | ComputeBudget | `SetComputeUnitLimit` |
| 1 | ComputeBudget | `SetComputeUnitPrice` |
| 2 | AssociatedToken | `createIdempotent` da ATA `oP37bN43…fxTA` (Token-2022) |
| 3 | Pump `6EF8rrec…wF6P` | `Buy` (18 contas) |

Deltas de lamports (pré → pós):

| conta | delta | o que é |
|-------|-------|---------|
| `ARsuJEag…6Dr4` (payer) | **−52 659 524** | a carteira do operador |
| `AG8t1o98…3Jss` | +49 175 786 | bonding curve — o `sol_amount` do evento |
| `62qc2CNX…fNgV` + `5YxQFdt3…vxeD` | +233 585 + 233 585 = 467 170 | taxa de protocolo (`fee`) |
| `EEsvEqfw…xCuC` | +147 528 | `creator_fee` |
| `oP37bN43…fxTA` | **+1 513 840** | aluguel da ATA do token (`createAccount`, 170 bytes, Token-2022 com `immutableOwner`) |
| `BY3qA3VV…Mben` | **+1 346 200** | aluguel do PDA `user_volume_accumulator` (`createAccount`, 137 bytes, dono = programa Pump) |
| — | −9 000 | taxa de rede queimada/validador (5 000 base + 4 000 de prioridade) |

**Conta fechada:** 49 175 786 + 467 170 + 147 528 + 9 000 = 49 799 484, e
49 799 484 + 1 513 840 + 1 346 200 = **52 659 524** = o delta do payer, ao lamport.

> Os 2 860 040 = 1 513 840 (aluguel da ATA) + 1 346 200 (aluguel do
> `user_volume_accumulator`). **Não** é taxa de prioridade (essa está dentro de `meta.fee`,
> os 4 000 lamports acima dos 5 000 de base), **não** é slippage (o `sol_amount` do evento é
> exatamente o que a curva recebeu) e **não** é tip de Jito (não há transferência a validador
> fora da taxa).

Duas correções ao que o brief supunha:
1. o aluguel da ATA é **1 513 840**, não 2 039 280 — a moeda é Token-2022 (`TokenzQdB…xuEb`) e
   a conta tem 170 bytes (`immutableOwner`), à taxa atual de 5 080 lamports/byte (128 + espaço);
2. metade do resíduo **não é por moeda**: o `user_volume_accumulator` é PDA de semente
   `["user_volume_accumulator", wallet]` (confirmado por `tx.user_volume_accumulator_address`),
   criado **uma vez por carteira**. As próximas compras pagam só o aluguel da ATA.

## 2. O resíduo entra no PnL? Sim

`entries.py:313` grava `sol_spent_lamports = fill.buy_total_lamports`, e `buy_total_lamports` é
`−payer_delta` (não `event_buy_total_lamports`). A linha da VPS confirma:

```
meme_live_positions: sol_spent_lamports=52659524  sol_received_lamports=42895712
                     pnl_sol=-0.0097638120  entry->>unexplained_lamports=2860040  exit=0
```

Carteira: 717 439 933 → 707 676 121 = **−9 763 812** = PnL gravado, ao lamport. (O
−9 764 060 do brief está 248 lamports acima; a fonte boa é a linha acima.)
Ou seja: o dinheiro está contabilizado — só está **sem nome**, e o PnL de uma operação
carrega um custo de infraestrutura (aluguel) como se fosse custo de negociação.

Já a leitura do *watcher* (`wallet_fills.py`) perde o resíduo: `sol_spent_lamports` = 49 799 484
(só evento + taxas). Executor e `meme_wallet_trades` discordam em 2 860 040 por compra.

## 3. O aluguel volta? Sim para a ATA — e o executor não o pega

A venda `k6nBHehm…81ETg` tem 3 instruções (2 ComputeBudget + `Sell`), zero `closeAccount`,
`unexplained = 0`, e o `postTokenBalance` da carteira é **0**. A ATA fica aberta com
1 513 840 lamports presos. `CloseAccount` só existe no repo para a WSOL do PumpSwap
(`packages/exchange-adapters/hunter_exchanges/pumpswap/tx.py:161`), nunca para a ATA do memecoin.

Custo: **0,00151384 SOL presos por moeda comprada** (não 0,002). Com 5 compras, ~0,0076 SOL;
com 100 compras/dia, ~0,15 SOL/dia parados — dinheiro recuperável que não volta ao caixa.
O aluguel do `user_volume_accumulator` (1 346 200) é uma vez só e fica; o programa expõe
`close_user_volume_accumulator` (PUMPFUN-ONCHAIN.md §…), mas fechá-lo derrubaria o cashback.

## 4. Conclusão (4 linhas)

1. Os 2 860 040 lamports são **aluguel**: 1 513 840 da ATA Token-2022 + 1 346 200 do
   `user_volume_accumulator`; a soma fecha a transação ao lamport. Nada de prioridade,
   slippage ou tip.
2. O resíduo **está** no `sol_spent_lamports` (caminho do payer delta) e o PnL −9 763 812 bate
   com a carteira; o watcher (`wallet_fills`) é que o **perde** — divergência de 2 860 040/compra.
3. O aluguel da ATA é **recuperável** e o executor **não** o recupera: a venda não emite
   `closeAccount`, então ~0,0015 SOL ficam presos por moeda.
4. O aluguel do acumulador é **uma vez por carteira** — a segunda compra em diante terá
   `unexplained = 1 513 840`, não 2 860 040.

### Correção proposta (para o dono do executor, T4.45 em diante)

- **Rotular**: `FillRecord.as_json()` passa a emitir `ata_rent_lamports` e
  `account_rent_lamports` lidos das `createAccount` internas que o payer financiou
  (`system::createAccount`, `info.source == wallet`) — função pura sobre o mesmo payload, já
  escrita como `_rent_funded_by` em
  `packages/exchange-adapters/tests/unit/test_wallet_fills_r43.py`. `unexplained_lamports`
  vira o que sobra depois disso (deve ser 0) e o PnL pode reportar
  `pnl_trading = pnl + ata_rent` separado do caixa.
- **Recuperar**: anexar `CloseAccount` (Token-2022, destino = carteira) à venda **quando a
  venda zera o saldo de tokens**, com a mesma trava de verificação do PumpSwap
  (só a ATA da própria carteira, destino = carteira). Alternativa sem tocar no caminho quente:
  uma varredura periódica que fecha ATAs de saldo 0.
- **Alinhar o watcher**: `wallet_fills.py` deveria somar o mesmo aluguel (ou expor
  `payer_delta_lamports`) para que `meme_wallet_trades` e `meme_live_positions` não divirjam.

## 5. Achado lateral (severidade média)

`packages/exchange-adapters/hunter_exchanges/pumpfun/wallet_fills.py:114` —
`_account_keys` faz `str(key)` sobre as chaves; com `encoding: jsonParsed` (chaves são objetos
`{pubkey, signer, …}`) nada casa: o programa Pump não é encontrado, a carteira não é encontrada,
e a função devolve `side='unknown'`, `reason='no_known_venue'` **sem erro**. Cenário de falha:
alguém aponta o watcher para um RPC/wrapper que devolve `jsonParsed` (é o encoding recomendado
na documentação da Solana) e todas as fills viram `unknown` silenciosamente — o painel mostra
"nenhuma operação" para carteiras que estão negociando. Correção de uma linha: aceitar
`key["pubkey"]` quando `key` for `dict`. Coberto por
`test_json_parsed_payload_decodes_as_unknown` (fixa o comportamento atual, para não passar
despercebido).

## Comandos

```
pytest packages/exchange-adapters/tests/unit/test_wallet_fills_r43.py \
       packages/exchange-adapters/tests/unit/test_pumpfun_wallet_fills.py -q   # 15 passed
```

Fixtures (resultados reais de `getTransaction`, capturados do RPC público):
`packages/exchange-adapters/tests/fixtures/pumpfun/rpc_tx_r43_real_buy_raw.json` (jsonParsed),
`…/rpc_tx_r43_real_buy_json_raw.json` (json), `…/rpc_tx_r43_real_sell_raw.json` (jsonParsed).
