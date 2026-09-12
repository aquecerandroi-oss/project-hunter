---
tags: [knowledge, nota, plantao, meme, pumpfun, programa, upgrade, holder-rewards]
tema: memecoin / pump.fun / upgrade do programa da curva em 2026-09-12 (holder rewards, fim do cashback, `bonding_curve_v2`, `creator_fee_bps` configurável)
fonte: RPC público da Solana (`getAccountInfo` do programa e do `ProgramData`, `getBlockTime`); repositório `pump-fun/pump-public-docs` (README, HOLDER_REWARDS_README, COIN_CREATION, PUMP_PROGRAM_README, atom de commits, PR #45); IDL `main` do programa (baixada pela T4.14); Telegram `pump_tech_updates`; `pump.fun/docs/fees`; notas da T4.14 (simulação mainnet)
fonte_url: https://github.com/pump-fun/pump-public-docs/pull/45
lido_em: 2026-09-12
evidencia: medição própria on-chain (slot e hora do último deploy do programa, lidos por RPC às 14:51:38 BRT) + docs e IDL do próprio programa com horas de commit + falha independente do nosso executor às 14:09 BRT (erro 6074); cadência e limiar de distribuição só por imprensa (não medidos); nenhuma moeda holder-rewards observada ainda (a REST não expõe o flag)
hipotese_testavel: sim
astra: ver seção Astra (run 14; parecer em `.claude/state/astra-review-plantao-meme-20260912-1447.md`)
status: vivo
owner: sexta-feira
updated: 2026-09-12
confiança: "?"
---

# KB-0094 — pump.fun: o upgrade de 12/09/2026 (holder rewards, fim do cashback, `bonding_curve_v2`)

**Plantão T4.64, run 14, lane 2 (14:47–15:1x BRT).** Rascunho: `.claude/state/plantao-meme/2026-09-12-1447-lane2.md` (itens 1–3, 10). Brutos:
`.claude/state/plantao-meme/raw-lane14/` (`01_rpc_program_account.json`, `03_rpc_programdata.json`, `04_rpc_blocktime.json`, `09_gh_*.txt`, `02_tg_pump_tech_updates.txt`).

## O fato medido

| o quê | valor | como/onde | lido em (BRT) |
|---|---|---|---|
| programa da curva | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` → `ProgramData` `B5MvUwXdiW1NMM6QFFD3ssPKBujD4zMohncbM73Z2BQu` | `getAccountInfo(jsonParsed)` em `https://api.mainnet-beta.solana.com` (contexto slot 446 490 524) | 14:50:49 |
| **último deploy** | **slot 446 462 760**; autoridade de upgrade `7gZufwwAo17y5kg8FMyJy2phgpvv9RSdzWtdXiWHjFr8` | `getAccountInfo(ProgramData, jsonParsed)` (contexto 446 490 673) | 14:51:38 |
| **hora do bloco do deploy** | `getBlockTime(446462760)` = 1789226644 = **2026-09-12 15:24:04Z ≈ 12:24:04 BRT** (estimativa do bloco, não precisão da execução; na fronteira, ordem por slot/transação) | RPC | 14:51:48 |
| coerência com o nosso lado | T4.8: simulação ok às 07:59:27Z (slot 446 378 553, layout antigo); T4.14: `TradeEvent` com 16 bytes a mais e erro 6074 às 17:09Z (slot 446 484 451) — 446 378 553 < 446 462 760 < 446 484 451 | `.claude/state/notes-T4.14.md` §4 | 14:49 |
| docs do programa | commit "docs: holder rewards coins, cashback deprecated, create_v2 is_holder_reward" + "chore(idl): refresh pump, pump_amm and pump_fees IDLs" **11:28:42 BRT**; PR #45 mesclado **12:58:18 BRT** ("aligning with corresponding on-chain program updates") | `https://github.com/pump-fun/pump-public-docs/commits/main.atom`, `/pull/45` | 14:52 |
| Telegram `pump_tech_updates` | 20 posts; último **20/07 13:50:48Z**; os upgrades de 07/05 e 15/07 foram anunciados lá com 3–14 dias de antecedência; **este não foi anunciado** | `https://t.me/s/pump_tech_updates` (curl, texto extraído) | 14:51:51 |
| REST do site | `/coins` (70 mais novas, `includeNsfw=true`): 55 chaves, **nenhuma `is_holder_reward`**; `is_cashback_enabled` 70× `false`; chave `is_mayhem_mode` **ausente** (idem nos brutos do run 13 — não é mudança de hoje) | `https://frontend-api-v3.pump.fun/coins?sort=created_timestamp&order=DESC&limit=70&includeNsfw=true` | 14:53:33 |
| docs de usuário do site | `pump.fun/docs` só Termos/Privacidade; `/docs/bonding-curve` sem holder rewards; `/docs/fees` "Last Updated: 20 May 2026" | WebFetch | 14:50–14:54 |

## O que mudou no programa (docs + IDL, não imprensa)

- **Holder rewards coins** (`docs/HOLDER_REWARDS_README.md`): `create_v2` ganha o argumento final opcional `is_holder_reward` (`OptionBool`; permanente). O creator fee
  de cada trade "is set aside for the people who hold the coin, and pump.fun distributes it to them on an ongoing basis"; "the program records a pump.fun
  controlled address as the coin's creator"; "no claim instruction for holders". **"There are no changes to any trade instruction … Fees are computed exactly as
  before; the only difference is who ends up receiving the creator fee."** Criação pode ser desligada globalmente (`Global.is_holder_reward_enabled`).
- **Campos novos:** `BondingCurve.is_holder_reward: bool` e `Pool.is_holder_reward` (apêndice; contas antigas 1 byte mais curtas leem-se `false`);
  `CreateEvent`/`CreatePoolEvent.is_holder_reward`; `TradeEvent`/`BuyEvent`/`SellEvent` ganham `holder_rewards_bps: u64` + `holder_rewards: u64` ("0 otherwise").
  IDL `main` (T4.14, 17:13:54Z): `TradeEvent` 34 campos (era 32); 47 instruções, novas `distribute_fee_to_holders` ("Pays fees collected on the `holder-rewards`
  PDA … Signed by `Global.holder_reward_claim_authority`" — os `amounts[i]` vêm de fora da cadeia) e `update_holder_reward_config`.
- **Cashback encerrado:** `create_v2` rejeita `is_cashback_enabled = [true]`; moedas cashback existentes continuam iguais e o acumulado segue reclamável.
- **Taxas (para quem compra) inalteradas:** curva 1,25 % = criador 0,30 % + protocolo 0,95 % (`pump.fun/docs/fees`, 20/05/2026); PumpSwap canônico por faixa
  (1,25 % → 0,30 %); graduação 0,015 SOL. Numa holder-rewards coin os 0,30 % vão para a PDA `holder-rewards` em vez do `creator_vault`.
- **`creator_fee_bps` configurável** (`COIN_CREATION.md` arg 7; erros 6077/6078 "between 1 and the configured maximum"; `Global.max_configurable_creator_fee_bps`):
  **só para pares "custom"** (quote ≠ SOL/USDC); em SOL/USDC "the schedule always applies". A taxa de criador deixa de ser constante por moeda nesses pares.
- **`bonding_curve_v2`:** a IDL documenta-a como conta restante **opcional** de `sell` para cashback ("[0] user_volume_accumulator, [1] bonding_curve_v2. If provided
  and valid, creator_fee goes to user_volume_accumulator. Otherwise, falls back to transferring creator_fee to creator_vault"); erro **6074 `InvalidBondingCurveV2`
  "bonding_curve_v2 remaining account is missing or invalid"**. O nosso executor recebeu 6074 numa simulação rotulada `buy` cujo log aponta
  `programs/pump/src/sell.rs:133` (T4.14, 14:09 BRT); trades reais de hoje carregam a PDA `["bonding-curve-v2", mint]` + uma segunda conta, diferentes entre compra e
  venda — **conferir discriminador, instrução e contas antes de concluir que `buy` exige a conta** (Astra, must-fix 2); a divergência com "no changes to any trade
  instruction" fica em aberto para a T4.8b. Correlação temporal com o deploy não é diagnóstico.

## O que é imprensa (não medido)

`https://cryptobriefing.com/pumpfun-holder-rewards-cashback-deprecated/` (datada 12/09, sem hora exposta): "Distributions go out multiple times each hour", limiar
de US$ 20, conversão de moedas existentes "gated" e permanente, Cashback lançado em fevereiro/2026. Nada disso está nos docs do programa ("on an ongoing basis").

## O que muda para o Meme Radar (regra de casa)

1. **Versão do programa como coluna** (M-D8): `ProgramData.slot` da curva e do PumpSwap gravado a cada hora; fronteira **slot 446 462 760 (bloco ≈ 12:24:04 BRT)** em
   toda série que decodifica `TradeEvent`/`BondingCurve`; teste inicial: eventos antigos continuam corretos após atualizar o decoder e formato desconhecido fica
   explicitamente indisponível. Ordem de vigilância: RPC > atom do GitHub (merge 12:58:18 BRT; a autoria 11:28:42 não prova disponibilidade antes do deploy) >
   Telegram (silêncio) > site (desatualizado).
2. **`is_holder_reward` é feature do minuto 0** (byte final da `BondingCurve` / `CreateEvent`), invisível na REST — o Radar só a tem se decodificar on-chain (T4.2g/T4.12).
3. **Taxa de criador por moeda** (`creator_fee_bps`) em pares custom: `quote.py`/fita por lote leem da conta, não assumem 0,30 %.
4. Nenhuma régua de custo muda para o comprador (KB-0076/KB-0091); o que muda é o incentivo a **segurar** em holder-rewards coins — só a observação prospectiva
   (M-P34) diz se isso altera retenção 24 h.

## Hipótese testável

**M-P34** (prospectiva; `obsidian/00-INBOX/Hipoteses-do-plantao.md`; must-fixes 4–5 da Astra): exposição congelada `holder_reward_at_create` (lida quando o Radar
recebeu a criação; conversões posteriores, identidade original do criador e `Global.is_holder_reward_enabled` em colunas separadas; histórico reconstruído separado
da coleta prospectiva) × (i) conclusão comprovada 24 h em **todas** as criações acompanhadas e (ii) retenção de **preço** 24 h pós-migração só nas migradas (relógio
próprio, referência congelada, censura explícita); braços contemporâneos com sobreposição nos estratos `quote_mint` × Mayhem × `x_link_kind` (M-P17); desconhecido
nunca vira `false`; ≥ 100 avaliáveis por braço e ≥ 30 dias como piso; IC95 % por blocos de dia. Ordem da Astra: M-D8 → coleta de exposição → avaliação.

## Astra
Parecer do run 14 (`.claude/state/astra-review-plantao-meme-20260912-1447.md`) resumido na nota do dia [[02-MARKET/Meme/2026-09-12]] (seção "Run 14").

## Ligações
[[02-MARKET/Meme/2026-09-12]] · [[00-INBOX/Hipoteses-do-plantao]] · [[KB-0091-pump-fun-as-taxas-base-e-seus-denominadores]] · [[KB-0093-dex-paid-e-boost-o-que-custam-e-o-que-medem]] · [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas]] · [[README-meme]]
