---
tags: [knowledge, meme, pumpswap, pumpfun, decodificador, buyevent, reservas, versao-1, onda-1a, h-030]
tema: o BuyEvent da PumpSwap decodificado e as armadilhas medidas ao ler eventos de swap do programa inteiro (campos trocados, reservas de antes do trade, quote virtual, cashback, transação versão 1)
fonte: transações reais de terceiros lidas por getTransaction na RPC pública api.mainnet-beta.solana.com em 05/10/2026 (pós-redeploy de 02/10 15:47Z), guardadas em packages/exchange-adapters/tests/fixtures/t1a_* com proveniência em t1a_provenance.json
fonte_url: https://solana.com/docs/rpc/http/gettransaction
lido_em: 2026-10-05
evidencia: medição própria (100 transações da PumpSwap com swap, 115 do programa pump, 61 pares consecutivos de pool, 3 provas ao vivo na RPC) + duas rodadas da Astra
hipotese_testavel: não (é leitura de instrumento; serve ao H-030, onda 1c e onda 2)
astra: duas rodadas; 4 pontos obrigatórios da primeira tratados com teste, ver Revisoes-Astra/wallets-1a
status: vivo
owner: exchange-integration-specialist
updated: 2026-10-05
confiança: "backtest do autor"
tipo: leitura
hipotese: —
variavel: campos do BuyEvent, reservas de pool antes e depois do trade, reserva virtual de quote, cashback, versão da transação
populacao: PumpSwap e pump.fun, 100 transações com swap da PumpSwap (48 BuyEvent, 54 SellEvent) e 115 transações com sucesso do programa pump, segunda-feira 05/10/2026, noite UTC
efeito: —
ic: —
veredito: —
proximo_passo: o motor 1c (pricing.py) passa a cotar pool com a reserva virtual e a desfazer o trade com a taxa LP; o coletor (onda 2) consome SwapRecord
classe_de_perda: —
mercado: meme
---

# KB-0184 — O `BuyEvent` da PumpSwap e as armadilhas de ler eventos do programa inteiro (05/10/2026)

## O que afirma

O `BuyEvent` (36 % dos swaps do programa, [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]]) agora tem decodificador
(`packages/exchange-adapters/hunter_exchanges/pumpswap/buy_event.py`) e os três eventos de swap (`TradeEvent` da curva, `BuyEvent`,
`SellEvent`) viram **um** registro (`swap_record.py`, `program_logs.py`). Ler esses eventos tem **cinco armadilhas** que só a cadeia mostrou
(cada uma com fixture real e teste): o número que o código "óbvio" lê está errado em todas.

1. **O `buy_exact_quote_in` troca dois campos.** Das 48 compras de uma amostra de 100 transações da PumpSwap, **12** eram `buy` e **36** `buy_exact_quote_in`.
   No segundo o programa grava o **total que o usuário paga** em `quote_amount_in` e o **líquido** em `user_quote_amount_in`, o contrário do `buy`.
   O que não se move é `quote_amount_in_with_lp_fee`: o cofre da pool recebe exatamente isso (7 de 7 fixtures, por delta de saldo SPL). Daí
   `líquido = with_lp − lp_fee` e `total pago = with_lp + protocolo + criador + cashback`; o par cru fecha como **conjunto** em 48 de 48.
2. **As reservas de pool do evento são as de ANTES do trade** (a curva da pump.fun, ao contrário, reporta DEPOIS). Em **61 de 61** pares consecutivos de
   uma mesma pool (21 compra→compra, 5 compra→venda, 10 venda→compra, 25 venda→venda) as reservas do trade seguinte são as anteriores movidas pelo fluxo do
   cofre: compra soma `with_lp_fee` de quote e tira `base_amount_out`; venda tira `quote_amount_out − lp_fee` (a taxa LP fica na pool) e soma `base_amount_in`.
3. **A pool precisa da reserva virtual.** O preço executado só sai de `(quote + virtual_quote_reserves)`: numa compra real `buy` dá exatamente 38 387 041 lamports
   (ceil, exato em 3 de 3 `buy`; dentro de 1 lamport nos `buy_exact_quote_in`) e as vendas batem exato (4 de 4). Só com a quote real dá **32 468 689**
   (−15 %). O evento carrega `virtual_quote_reserves` (i128; 17,5–25,7 bilhões nas pools lidas, 0 numa).
4. **Cashback.** Na **venda** é dedução (`líquido = bruto − LP − protocolo − criador − cashback`: 54 de 54, incluindo 2 com cashback ≠ 0, ambas na mesma transação);
   na **compra** nunca apareceu (0 de 48). Conta-se como taxa por simetria; se estiver errado o evento reprova na conservação e é reportado, não vira fill.
   `holder_rewards ≠ 0` (2 de 48 compras, 3 de 54 vendas) **não** é dedução extra: a conta fecha sem ele.
5. **Transação versão 1.** 21 das 115 transações com sucesso do programa pump traziam `TradeEvent` **e eram versão 1**; 18 das 100 da PumpSwap também. O nó
   público devolve `-32015` a `getTransaction`/`getBlock` com `maxSupportedTransactionVersion: 0` (resposta real guardada). O JSON v1 tem `transactionConfig` em vez de
   `addressTableLookups`, `loadedAddresses` vazio e o resto igual; todo parser a jusante lê só `accountKeys`/`loadedAddresses`/`innerInstructions`.

Também medido: a cauda do `BuyEvent` pós-redeploy é sempre de **49 bytes** (41 que a IDL declara + um `u64` sem nome; 48 de 48), `ix_name` é o que muda o tamanho (497 B `buy`,
512 B `buy_exact_quote_in`); o `pool` e o `user` do evento são as contas 0 e 1 da instrução (também roteada, 7 de 7).

## Onde foi mostrado (próprio)

| Evidência | Resultado |
|---|---|
| 400 assinaturas mais recentes da PumpSwap, 292 com sucesso, 100 com swap | 48 `BuyEvent` + 54 `SellEvent` (uma transação com dois); 18 v1; cauda 49 B em 48/48 |
| 115 transações com sucesso do programa pump | 21 v1 com `TradeEvent` |
| Pares consecutivos por pool | 61/61 batem em base e quote (após a derivação acima) |
| Prova ao vivo (`tests/live/test_live_tx_version.py`, `HUNTER_LIVE_TESTS=1`) | v1 recusada a `0` (−32015) e servida a `1` igual à fixture; legacy e v0 devolvem respostas **idênticas** a `0` e a `1` (3 passed, 05/10) |

## O que a literatura/documentação diz

A IDL do programa (GitHub, `pump_amm`) lista os campos do `BuyEvent` mas **não** diz que as reservas são anteriores nem que `buy_exact_quote_in` troca dois campos; o
`u64` final não está em nenhuma IDL. A documentação da Solana descreve `maxSupportedTransactionVersion` como o **teto** da versão aceita (https://solana.com/docs/rpc/http/gettransaction).

## Como mediríamos aqui

Fixtures reais de `getTransaction` (proveniência por assinatura, slot e hora) e testes que comparam o decodificador com **a própria cadeia** (contas da instrução, deltas de saldo SPL, reservas do
trade seguinte), nunca com a saída do decodificador. Os eventos dos logs são idênticos byte a byte aos das inner instructions (7 conjuntos).

## Hipótese testável no Lab

Nenhuma: é instrumento. Serve à onda 1c e à onda 2 do H-030.

## O que muda na operação

- **Nada liga.** O leitor e o decodificador não estão ligados a nenhum worker.
- **O motor 1c precisa mudar antes do coletor:** `packages/indicators/hunter_indicators/meme/wallets/pricing.py` cota a pool com `state.sol_lamports * atoms // (token_atoms + atoms)` (sem a reserva virtual) e `_pre_state`
  desfaz só `sol_lamports` (sem a taxa LP). O `SwapRecord` já entrega `virtual_quote_reserves`, `lp_fee_lamports` e reservas pós-trade exatas ([[Open Bugs]]).
- `maxSupportedTransactionVersion` passou a `1` em `tx_rpc.py` e `rpc_wallet.py` ([[Resolved Bugs]]).
- Achado lateral: `infra/scripts/wallet_tape_probe_core.py` (`_from_sell`) soma a taxa da venda **sem** o cashback (2 de 54 vendas): a sondagem da onda 0 subestima a taxa nessas vendas. Não alterado aqui.

## Por que pode falhar

- Uma tarde (noite UTC) de um dia; 100 transações. As frequências (36 de 48 `buy_exact_quote_in`) são desta amostra.
- Cashback em **compra** sem nenhum caso real (a regra é simetria, protegida pela conservação).
- A derivação das reservas assume que a LP fee fica na pool e que nada mais mexe no cofre entre dois trades da pool (um `Deposit`/`Withdraw` sem swap quebraria a cadeia: 3,4 % das pools ativas tiveram retirada em 39 min, [[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]]); nos 61 pares não houve exceção.
- A pilha de invoke estrita pode, em tese, dar falso gap num padrão de log que nunca vimos; vira lacuna visível, não perda silenciosa.
- **Linha de evento sem frame ao redor e log que termina com frame aberto** (achados do code-reviewer, 05/10, reproduzidos na fixture das duas vendas): a primeira também deixa o leitor cego — antes a segunda venda herdava o ordinal 0 da primeira —, a segunda é lacuna (`open_frames_at_end`): uma transação com sucesso fecha todos os frames, então pilha aberta no fim é sufixo perdido. O que **não** se vê pelos logs é um evento apagado do meio de um frame intacto. Ver [[wallets-1a]].
- **Depois de uma lacuna de linha o leitor não atribui mais nada** (`Log truncated` no meio, entrada não textual, pilha incoerente): o runtime pode descartar uma mensagem grande, imprimir o marcador e manter as pequenas seguintes, então o ordinal do que vem depois é impossível de saber. Só o prefixo antes do dano é lido; o resto vira `unattributed_data_lines` (lacuna). Consequência para a onda 2: numa transação com log truncado a recuperação **não** pode vir de `read_transaction_logs` (o log recuperado traz o mesmo corte): precisa dos eventos `emit_cpi` das *inner instructions*, contando **todos** os eventos do programa (swap ou não) antes de filtrar. O ordinal dos logs coincide com o das inner instructions em todas as 11 fixtures reais (sequências inteiras, por programa); isso é **observado, não garantido pelo protocolo** (`Program data:` é saída genérica) — e o leitor por inner instructions ainda não existe.

## Segunda opinião (Astra)

[[wallets-1a]] — duas rodadas: 4 pontos obrigatórios na primeira (reservas e quote virtual, ordinal deslocado, pilha incoerente, quote por igualdade de quantidades), todos tratados com teste que falhou antes.

## Relacionados

[[KB-0183-o-programa-inteiro-da-pumpfun-e-pumpswap-custa-isto-de-coletar]] · [[KB-0182-quem-ganha-dinheiro-de-verdade-nos-memes]] · [[T4.8e-decoders]] · [[wallets-engine]] · [[EXP-M15-carteiras-vencedoras]] · [[Exchange Adapters]]
