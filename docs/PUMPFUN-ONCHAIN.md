# Mapa on-chain do pump.fun (Solana) — T4.0d

Referência técnica dos três programas Solana que compõem o pump.fun hoje: a bonding curve
(`6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`), o AMM de pós-graduação PumpSwap
(`pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA`) e o programa Mayhem
(`MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e`), além de um quarto programa que apareceu nesta
pesquisa e não estava listado no brief — o **Pump Fees** (`pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ`),
dono da conta `FeeConfig` que referenciada em `buy_v2`/`sell_v2`.

Toda afirmação abaixo tem URL + (quando aplicável) commit + hora de leitura em horário de
Brasília (BRT = UTC−3, sem horário de verão, convenção já usada em `.claude/state/notes-T4.0.md`).
Sessão de pesquisa: 2026-09-12, madrugada, ~02:20–02:35 BRT (05:20–05:35 UTC). Fonte primária
principal: `github.com/pump-fun/pump-public-docs`, commit `9c82f61cb711b044a17f770ab8ce9f9bdf78f333`
(branch `main`, HEAD no momento da leitura — `pushed_at` da API do GitHub: 2026-07-15T18:22:27Z),
lido via `raw.githubusercontent.com/pump-fun/pump-public-docs/9c82f61.../<path>` para cada arquivo
citado, mais leituras AO VIVO contra `https://api.mainnet-beta.solana.com` (read-only, sem chave).
Lista completa de URLs e comandos em `.claude/state/notes-T4.0d.md`.

**Como ler este documento:** ele é mais detalhado que o necessário para o T4.1 inicial de propósito
— é o mapa "por completo" que o Everton pediu. §7 resume o que é realmente acionável agora.

---

## 0. Os quatro programas

| Programa | Endereço | Papel |
|---|---|---|
| Pump (bonding curve) | `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | cria moedas, roda a curva até a graduação |
| PumpSwap (Pump AMM) | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` | AMM de produto constante pós-graduação |
| Pump Fees | `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ` | `FeeConfig` (tiers de taxa por market cap), `SharingConfig` (fee-splitting entre múltiplos criadores), cashback social, buyback |
| Mayhem | `MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e` | agente autônomo que compra/vende em random walk nas primeiras 24h de moedas criadas com o modo ligado |

Confirmado ao vivo (`getAccountInfo`, 2026-09-12 02:28 BRT): o Mayhem é um programa BPF
upgradeable real e implantado (`executable=true`, `owner=BPFLoaderUpgradeab1e...`, conta de 36
bytes — o formato padrão de uma conta `Program` apontando para sua `ProgramData`). Não encontrei
o IDL público desse programa (§3.2) — o que se sabe dele vem inteiramente de como o programa Pump
o referencia (CPI em `create_v2`) e da doc `pump.fun/docs/mayhem-mode` já citada em
`docs/plans/T4-MEME-RADAR.md` (adendo 2026-09-12 02:3x BRT).

---

## 1. Programa Pump — bonding curve

Fonte: `docs/PUMP_PROGRAM_README.md` e `idl/pump.json` do repo acima (mesmo commit). O README
descreve uma versão **mais antiga e mais simples** do que o IDL atual — isso é esperado e
documentado pelo próprio programa: `extend_account` existe exatamente para acrescentar campos a
`Global`/`BondingCurve` sem quebrar contas existentes, e o README não foi atualizado desde
2026-07-15 enquanto o IDL já reflete campos posteriores (mayhem, cashback, buyback, multi-quote).
**Trate o IDL como a fonte de verdade sobre o README sempre que divergirem** — é o que este
documento faz.

### 1.1 Conta `Global` (PDA `["global"]` → `4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf`)

Discriminador Anchor (do IDL, `accounts[].discriminator` para `Global`): decimal
`[167, 232, 232, 177, 200, 108, 114, 127]` = hex `a7e8e8b1c86c727f`.

Layout completo (ordem exata do IDL `types[name=Global].type.fields`; todo `pubkey` = 32 bytes,
`u64` = 8 bytes little-endian, `bool` = 1 byte 0/1, array = N × tamanho do elemento, sem padding
entre campos — layout Borsh/Anchor puro):

| # | campo | tipo | valor lido AO VIVO em 2026-09-12 02:24:15 BRT (slot 446349159) |
|---|---|---|---|
| 1 | `initialized` | bool | `true` |
| 2 | `authority` | pubkey | `FFWtrEQ4B4PKQoVuHYzZq8FabGkVatYzDpEVHsK5rrhF` |
| 3 | `fee_recipient` | pubkey | `62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV` |
| 4 | `initial_virtual_token_reserves` | u64 | `1073000000000000` (1,073 bi tokens, 6 casas) |
| 5 | `initial_virtual_sol_reserves` | u64 | `30000000000` (30 SOL) |
| 6 | `initial_real_token_reserves` | u64 | `793100000000000` (793,1 M tokens) |
| 7 | `token_total_supply` | u64 | `1000000000000000` (1 bi tokens) |
| 8 | `fee_basis_points` | u64 | `95` (0,95% — **fallback**, ver §1.4) |
| 9 | `withdraw_authority` | pubkey | `39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg` |
| 10 | `enable_migrate` | bool | `true` |
| 11 | `pool_migration_fee` | u64 | `15000001` lamports |
| 12 | `creator_fee_basis_points` | u64 | `5` (0,05% — **fallback**, ver §1.4) |
| 13 | `fee_recipients` | [pubkey;7] | os 7 últimos da tabela "Normal Fee Recipients" (§1.5) — item #0 é o campo 3 (`fee_recipient`) |
| 14 | `set_creator_authority` | pubkey | `39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg` |
| 15 | `admin_set_creator_authority` | pubkey | `UqN2p5bAzBqYdHXcgB6WLtuVrdvmy9JSAtgqZb3CMKw` |
| 16 | `create_v2_enabled` | bool | `true` |
| 17 | `whitelist_pda` | pubkey | `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s` |
| 18 | `reserved_fee_recipient` | pubkey | `GesfTA3X2arioaHp8bbKdjG9vJtskViWACZoYvxp4twS` |
| 19 | `mayhem_mode_enabled` | bool | `true` |
| 20 | `reserved_fee_recipients` | [pubkey;7] | itens #1–7 da tabela "Reserved Fee Recipients" (§1.5) |
| 21 | `is_cashback_enabled` | bool | `true` |
| 22 | `buyback_fee_recipients` | [pubkey;8] | tabela "Buyback Fee Recipients" (§1.5) |
| 23 | `buyback_basis_points` | u64 | `5000` (ver ressalva abaixo) |
| 24 | `initial_virtual_quote_reserves` | u64 | `4292000000` — reserva virtual inicial para o quote mint alternativo (não-SOL) |
| 25 | `whitelisted_quote_mints` | [pubkey;1] | `EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` = **USDC** (mint canônico da Solana) |

Comando exato e script de decodificação em `.claude/state/notes-T4.0d.md` §2. Todos os campos até
`quote_mint` (32 bytes por pubkey, sem padding) somam 1045 bytes; a conta tem `space=1054`
(9 bytes de cauda reservada, não decodificados — `extend_account` já correu à frente do que o IDL
público expõe, ou é slack alocado para o próximo campo).

**Dois achados que não estavam nas notas anteriores (T4.0/T4.0b), obtidos por correlação entre a
leitura ao vivo acima e as tabelas oficiais de `docs/FEE_RECIPIENTS.md`:**

1. `whitelist_pda` (campo 17, nome genérico no IDL) contém, hoje, exatamente o endereço
   `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s` — a **carteira do agente Mayhem** citada em
   `pump.fun/docs/mayhem-mode` e no brief desta tarefa. O nome do campo no IDL não menciona Mayhem;
   é plausível que o campo tenha nascido para outro propósito (uma allowlist genérica) e hoje
   carregue esse valor porque `set_reserved_fee_recipients(whitelist_pda: pubkey)` é a única
   instrução que escreve nele (ver tabela de instruções, §1.3) — ninguém documentou publicamente
   essa reutilização; é uma leitura direta da conta, não uma alegação de terceiros.
2. `reserved_fee_recipient` (campo 18, singular) é exatamente `GesfTA3X2arioaHp8bbKdjG9vJtskViWACZoYvxp4twS`,
   o "recebedor de taxa das moedas Mayhem" citado no adendo de `T4-MEME-RADAR.md` — mas na
   verdade é só o **item #0** da lista de 8 "Reserved Fee Recipients" oficial (`FEE_RECIPIENTS.md`):
   os outros 7 estão no array `reserved_fee_recipients` (campo 20). Não é um destinatário único
   fixo; é um de 8 endereços entre os quais `buy_v2`/`sell_v2` de moedas Mayhem escolhem (ver §1.3).

**Ressalva sobre `buyback_basis_points=5000`:** não confirmei o que esse número mede (50,00%? de
qual base?) — a única doc que toquei sobre buyback é a definição de tipo (`update_buyback_config`,
evento `TradeEvent.buyback_fee`/`buyback_fee_basis_points`), sem uma página explicando a mecânica
do buyback como um todo. Não afirmo um significado além de "está em basis points, campo existe,
valor lido ao vivo é 5000".

### 1.2 Conta `BondingCurve` (PDA `["bonding-curve", mint]`)

Discriminador Anchor: decimal `[23, 183, 248, 55, 96, 216, 172, 96]` = hex `17b7f83760d8ac60`.

| # | campo | tipo | bytes |
|---|---|---|---|
| 1 | `virtual_token_reserves` | u64 | 8 |
| 2 | `virtual_quote_reserves` | u64 | 8 |
| 3 | `real_token_reserves` | u64 | 8 |
| 4 | `real_quote_reserves` | u64 | 8 |
| 5 | `token_total_supply` | u64 | 8 |
| 6 | `complete` | bool | 1 |
| 7 | `creator` | pubkey | 32 |
| 8 | `is_mayhem_mode` | bool | 1 |
| 9 | `is_cashback_coin` | bool | 1 |
| 10 | `quote_mint` | pubkey | 32 |

Discriminador (8) + campos (107) = **115 bytes mínimos**. Para moedas pareadas em SOL,
`quote_mint = Pubkey::default()` (32 bytes zero, base58 `"111...1"`), e o campo 2/4 carregam
lamports de SOL (é por isso que `docs/PUMP_PROGRAM_README.md`, na versão antiga, chama os campos
2/4 de `virtual_sol_reserves`/`real_sol_reserves` — mesmo campo, nome mais antigo).

Regras de atualização (confirmadas em `PUMP_PROGRAM_README.md`, ainda válidas no IDL atual):
- `buy`: `virtual_quote_reserves` e `real_quote_reserves` **sobem** pelo mesmo tanto de
  lamports/unidades de quote; `virtual_token_reserves` e `real_token_reserves` **descem** pelo
  mesmo tanto de tokens.
- `sell`: o inverso.
- `complete` vira `true` ao final de um `buy` que zera `real_token_reserves`.
- A **graduação** (`migrate`) é uma instrução **separada** de `complete` — confirmado também pelo
  IDL: `migrate`/`migrate_v2` não têm argumentos e checam o estado já gravado, e são
  **idempotentes e permissionless** ("running it on a completed and migrated bonding curve does
  nothing", "anyone can migrate a completed bonding curve" — `PUMP_PROGRAM_README.md`).

**§ Comparação com `packages/exchange-adapters/hunter_exchanges/pumpfun/decode.py` (Astra, READ
ONLY nesta tarefa):** o layout, a ordem dos 10 campos e o discriminador `17b7f83760d8ac60`
implementados em `decode_bonding_curve_account` **batem byte a byte com o IDL oficial acima** —
não há divergência de layout. `_MIN_LEN=115` também bate (40 + 1 + 32 + 1 + 1 + 32 = 107, + 8 de
discriminador). O único ponto que vale registrar não é em `decode.py`, é em `curve.py`
(`CURVE_TRADE_FEE_PCT = Decimal("1.25")`) — ver §1.4 abaixo, é uma imprecisão de **taxa**, não de
**layout**.

### 1.3 Instruções — as que interessam para reconstruir/operar trades

Todas do IDL `idl/pump.json`, mesmo commit. Contas na ordem exata do IDL.

**`create`** (disc `181ec828051c0777`) — legado, sem Mayhem/cashback.
Args: `name:string, symbol:string, uri:string, creator:pubkey`.
Contas (14): `mint, mint_authority, bonding_curve, associated_bonding_curve, global,
mpl_token_metadata, metadata, user, system_program, token_program, associated_token_program,
rent, event_authority, program`.

**`create_v2`** (disc `d6904cec5f8b31b4`) — a única forma de ligar Mayhem/cashback na criação.
Args: `name:string, symbol:string, uri:string, creator:pubkey, is_mayhem_mode:bool,
is_cashback_enabled:OptionBool`.
Contas (16): `mint, mint_authority, bonding_curve, associated_bonding_curve, global, user,
system_program, token_program, associated_token_program,`
**`mayhem_program_id, global_params, sol_vault, mayhem_state, mayhem_token_vault`**`,
event_authority, program` — as 5 em negrito são PDAs do programa Mayhem
(`global-params`, `sol-vault`, `["mayhem-state", mint]`) passadas por CPI: **`create_v2` inicializa
o estado Mayhem do token na própria transação de criação quando `is_mayhem_mode=true`**, não é um
passo separado depois. Isso responde diretamente à pergunta do brief: sim, `create_v2` seta a flag
Mayhem, e o faz via CPI para o programa Mayhem, não só gravando um bit local.
Além disso, `create_v2` aceita 3 contas opcionais em `remaining_accounts` (`quote_mint`,
`associated_quote_bonding_curve`, `quote_token_program`) para criar moedas pareadas em USDC em vez
de SOL (`docs/instructions/COIN_CREATION.md`) — confirma que multi-quote já é real, não só um
campo dormente em `Global`.

**`buy` / `sell`** (legado, disc `66063d1201daebea` / `33e685a4017f83ad`) — só SOL, 16/14 contas,
args `amount, max_sol_cost` / `amount, min_sol_output` (+ `track_volume:OptionBool` em `buy`).

**`buy_v2` / `sell_v2`** (disc `b817ee6167c5d33d` / `5df6823ce7e940b2`) — interface unificada
SOL/USDC/Token-2022, 27/26 contas (`docs/instructions/BUY.md`, `SELL.md`, transcritos in extenso —
27 contas incluem `fee_recipient` + `buyback_fee_recipient` + ATAs associadas, `creator_vault`,
`sharing_config`, `global_volume_accumulator`/`user_volume_accumulator` para tracking de
incentivos, `fee_config` + `fee_program` do programa Pump Fees). Args: `amount:u64,
max_sol_cost:u64` / `amount:u64, min_sol_output:u64`. Regra de seleção de `fee_recipient`
(`docs/FEE_RECIPIENTS.md`): moeda **não-Mayhem** → um dos 8 "normal fee recipients"; moeda
**Mayhem** → um dos 8 "reserved fee recipients" (`Global.reserved_fee_recipient` + `[7]`); para
**qualquer** moeda, `buyback_fee_recipient` é um dos 8 "buyback fee recipients"
(`Global.buyback_fee_recipients`). Variantes adicionais no IDL, mesmo padrão de contas:
`buy_exact_sol_in`/`buy_exact_quote_in_v2` (compra por valor gasto em vez de por quantidade de
token — slippage no lado do output).

**`migrate`** (disc `9beae792ec9ea21e`, sem args, 25 contas) / **`migrate_v2`** (disc
`bbcb121fceedfe29`, sem args, 27 contas) — chamam **`create_pool`** do PumpSwap via CPI (as contas
incluem `pump_amm`, `pool`, `pool_authority`, `amm_global_config`, `lp_mint`,
`pump_amm_event_authority` — o próprio programa Pump é o `creator` do pool, então o `index` do
pool é sempre `0`, o **canonical pool**). `migrate_v2` generaliza para `base_mint`/`quote_mint`
(USDC também migra para um pool PumpSwap USDC-pareado). Confirmação de que completar e migrar são
eventos distintos: nenhuma das duas tem argumentos nem lê `real_token_reserves` como argumento —
elas releem o estado já persistido em `BondingCurve` e falham ou não fazem nada se ele não estiver
`complete`.

**`collect_creator_fee_v2`** (disc `cf118af204221338`, 10 contas, sem args) — varre o
`creator_vault` da bonding curve para a carteira/ATA do criador; permissionless (qualquer um pode
chamar em nome de um `creator`). Equivalente pós-migração no PumpSwap:
**`collect_coin_creator_fee`** (8 contas). `docs/instructions/COLLECT_CREATOR_FEE.md` documenta
os dois em detalhe, incluindo o caso de `quote_mint=SOL` (transferência de lamports nativa) vs.
outro quote (transferência SPL). **Ressalva do próprio doc:** essas duas instruções só funcionam
para moedas de criador único; uma vez migrado para `SharingConfig` (fee-splitting entre vários
criadores, programa Pump Fees), o saque tem que passar por `distribute_creator_fees_v2`.

**`extend_account`** (disc `ea66c2cb96483ee5`, 5 contas: `account, user, system_program,
event_authority, program`, sem args) — qualquer um paga para alongar `Global` ou `BondingCurve`
antes de um campo novo caber; é assim que a conta cresce sem migração de todos os tokens já
criados.

**`set_params`** (disc `1beab2349302bb8d`, só `authority`, 11 args) — reescreve praticamente todo
`Global` (reservas iniciais, `fee_basis_points`, `withdraw_authority`, `enable_migrate`,
`pool_migration_fee`, `creator_fee_basis_points`, autoridades de `set_creator`) — **não** toca
`authority` em si (isso é `update_global_authority`, separado).

**Instruções administrativas específicas de Mayhem/cashback/multi-quote** (só `authority` +
`global`/`event_authority`/`program`, todas de baixo custo de conta — 4 contas): `toggle_mayhem_mode(enabled:bool)`,
`toggle_cashback_enabled(enabled:bool)`, `toggle_create_v2(enabled:bool)`, `add_quote_mint`/
`remove_quote_mint(quote_mint:pubkey)`, `set_virtual_quote_reserves(initial_virtual_quote_reserves:u64)`,
`set_reserved_fee_recipients(whitelist_pda:pubkey)` (é esta instrução que escreve o campo 17 de
`Global` — reforça a leitura do achado 1 acima), `update_buyback_config(buyback_basis_points:
Option<u64>)`. **`set_mayhem_virtual_params`** (disc `3da9bcbf99952a61`, 8 contas: `sol_vault_authority,
mayhem_token_vault, mint, global, bonding_curve, token_program, event_authority, program`, sem
args) é a única dessas ligada a um **mint específico** em vez de ser puramente global — é como o
programa Mayhem (via `sol_vault_authority`, uma PDA dele) empurra as reservas virtuais da curva
para simular o efeito dos trades do agente sem necessariamente rodar `buy`/`sell` completos; emite
`UpdateMayhemVirtualParamsEvent` (campos: `timestamp, mint, virtual_token_reserves,
virtual_sol_reserves, new_virtual_token_reserves, new_virtual_sol_reserves, real_token_reserves,
real_sol_reserves`) — **um decodificador de trades que ignorar esse evento vai ver a curva de uma
moeda Mayhem "pular" sem um `TradeEvent` correspondente.**

Tabela completa das 40 instruções (nome, discriminador hex, contas, args) está em
`.claude/state/notes-T4.0d.md` §3 — reproduzida por completo lá para não inchar este documento com
as puramente administrativas/de incentivo (`admin_update_token_incentives`,
`claim_token_incentives`, `sync_user_volume_accumulator`, `init_user_volume_accumulator`,
`close_user_volume_accumulator`, `claim_cashback`/`claim_cashback_v2`, `initialize`,
`admin_set_idl_authority`, `set_creator`/`set_metaplex_creator`/`admin_set_creator`,
`distribute_creator_fees`/`_v2`, `migrate_bonding_curve_creator`, `get_minimum_distributable_fee`).

### 1.4 Eventos — o que um decodificador precisa parsear

Todos emitidos via `#[event_cpi]` (self-CPI do Anchor — aparecem como uma instrução interna
chamando o próprio programa com `event_authority`/`program` como contas, carregando os bytes do
evento no `data` dessa instrução interna; é isso que `getTransaction` + `meta.innerInstructions`
(ou o log `Program data: ...` em `meta.logMessages`) expõe, e o que os decodificadores da §4 leem).

**`CreateEvent`** (disc decimal `[27, 114, 169, 77, 222, 235, 99, 118]` = hex `1b72a94ddeeb6376`):
`name, symbol, uri, mint, bonding_curve, user, creator,
timestamp:i64, virtual_token_reserves, virtual_sol_reserves, real_token_reserves,
token_total_supply, token_program, is_mayhem_mode:bool, is_cashback_enabled:bool, quote_mint,
virtual_quote_reserves`.

**`TradeEvent`** (disc `bddb7fd34ee661ee`): o mais rico — `mint, sol_amount, token_amount,
is_buy:bool, user, timestamp:i64, virtual_sol_reserves, virtual_token_reserves, real_sol_reserves,
real_token_reserves, fee_recipient, fee_basis_points, fee, creator, creator_fee_basis_points,
creator_fee, track_volume:bool, total_unclaimed_tokens, total_claimed_tokens, current_sol_volume,
last_update_timestamp:i64, ix_name:string, mayhem_mode:bool, cashback_fee_basis_points, cashback,
buyback_fee_basis_points, buyback_fee, shareholders:Vec<{address,share_bps}>, quote_mint,
quote_amount, virtual_quote_reserves, real_quote_reserves`. **`ix_name` diz qual instrução gerou o
evento** (`"buy"`/`"buy_v2"`/`"sell_v2"`/`"buy_exact_sol_in"`/...) — um decodificador não precisa
adivinhar pela forma da transação. **As taxas efetivas (`fee_basis_points`, `fee`,
`creator_fee_basis_points`, `creator_fee`) vêm prontas no evento, por trade** — ver §1.4b abaixo,
é a recomendação central desta seção sobre taxas.

**`CompleteEvent`** (disc `5f7261...` decimal `[95, 114, 97, 156, 212, 46, 152, 8]`): apenas
`user, mint, bonding_curve, timestamp:i64, quote_mint` — confirma que a conclusão da curva
(`complete=true`) é reportada separada da migração.

**`CompletePumpAmmMigrationEvent`** (disc decimal `[189, 233, 93, 185, 92, 148, 234, 148]`):
`user, mint, mint_amount, sol_amount, pool_migration_fee, bonding_curve, timestamp:i64, pool,
quote_mint` — este é o evento de migração de fato (não existe um evento chamado `MigrateEvent` no
IDL atual; o nome mudou).

**`SetParamsEvent`**, **`ExtendAccountEvent`**, **`UpdateMayhemVirtualParamsEvent`**,
**`MigrateBondingCurveCreatorEvent`**: campos completos em `.claude/state/notes-T4.0d.md` §4 —
úteis para auditoria/observabilidade do programa, não para reconstrução de preço/trade.

### 1.4b Fórmula de preço/custo — incluindo taxa, com uma ressalva importante

Curva de produto constante: `virtual_quote_reserves * virtual_token_reserves = k`. Preço marginal
(unidades normalizadas, já convertidas de lamports/subunidades — é o que `curve.py` faz):

```
preço_marginal = virtual_quote_reserves / virtual_token_reserves
```

Isso é **pré-taxa** e é o preço do próximo infinitésimo, não o preço médio de uma compra/venda
finita (a curva desliza — ver `T4-MEME-RADAR.md` §0/§4, já documentado, sem mudança aqui).

**A taxa efetivamente aplicada não é um número fixo simples — há duas fontes possíveis, e a leitura
ao vivo desta tarefa mostra que elas hoje discordam:**

1. **Fallback plano de `Global`:** `fee_basis_points` (protocolo) + `creator_fee_basis_points`
   (criador). Lido ao vivo em 2026-09-12 02:24 BRT: `95 + 5 = 100 bps = 1,00%`.
2. **`FeeConfig` (programa Pump Fees, PDA `["fee_config", pump_program_id]`, conta obrigatória em
   `buy_v2`/`sell_v2`):** tiers por market cap. A imagem `docs/fees.png` do mesmo commit (lida
   2026-09-12 02:26 BRT) mostra a tabela completa — reproduzida abaixo — cuja linha "N/A / Bonding
   curve" (aplica-se a **toda** compra/venda na curva, não escalona por mcap) é
   **criador 0,300% + protocolo 0,950% = total 1,25%**.

| Aprox. mcap (US$) | Estado | Criador | Protocolo | LP | Total |
|---|---|---|---|---|---|
| N/A | **Bonding curve** | 0,300% | 0,950% | 0% | **1,25%** |
| 0–85k | PumpSwap, 0–420 SOL | 0,300% | 0,930% | 0,020% | 1,25% |
| 85k–300k | 420–1470 SOL | 0,950% | 0,050% | 0,200% | 1,20% |
| 300k–500k | 1470–2460 SOL | 0,900% | 0,050% | 0,200% | 1,15% |
| 500k–700k | 2460–3440 SOL | 0,850% | 0,050% | 0,200% | 1,10% |
| 700k–900k | 3440–4420 SOL | 0,800% | 0,050% | 0,200% | 1,05% |
| 900k–2M | 4420–9820 SOL | 0,750% | 0,050% | 0,200% | 1,00% |
| 2M–3M | 9820–14740 SOL | 0,700% | 0,050% | 0,200% | 0,95% |
| 3M–4M | 14740–19650 SOL | 0,650% | 0,050% | 0,200% | 0,90% |
| 4M–5M | 19650–24560 SOL | 0,600% | 0,050% | 0,200% | 0,85% |
| 5M–6M | 24560–29470 SOL | 0,550% | 0,050% | 0,200% | 0,80% |
| 6M–7M | 29470–34380 SOL | 0,500% | 0,050% | 0,200% | 0,75% |
| 7M–8M | 34380–39300 SOL | 0,450% | 0,050% | 0,200% | 0,70% |
| 8M–9M | 39300–44210 SOL | 0,400% | 0,050% | 0,200% | 0,65% |
| 9M–10M | 44210–49120 SOL | 0,350% | 0,050% | 0,200% | 0,60% |
| 10M–11M | 49120–54030 SOL | 0,300% | 0,050% | 0,200% | 0,55% |
| 11M–12M | 54030–58940 SOL | 0,275% | 0,050% | 0,200% | 0,53% |
| 12M–13M | 58940–63860 SOL | 0,250% | 0,050% | 0,200% | 0,50% |
| 13M–14M | 63860–68770 SOL | 0,225% | 0,050% | 0,200% | 0,48% |
| 14M–15M | 68770–73681 SOL | 0,200% | 0,050% | 0,200% | 0,45% |
| 15M–16M | 73681–78590 SOL | 0,175% | 0,050% | 0,200% | 0,43% |
| 16M–17M | 78590–83500 SOL | 0,150% | 0,050% | 0,200% | 0,40% |
| 17M–18M | 83500–88400 SOL | 0,125% | 0,050% | 0,200% | 0,38% |
| 18M–19M | 88400–93330 SOL | 0,100% | 0,050% | 0,200% | 0,35% |
| 19M–20M | 93330–98240 SOL | 0,075% | 0,050% | 0,200% | 0,33% |
| 20M+ | 98240 SOL+ | 0,050% | 0,050% | 0,200% | 0,30% |

Fonte da mecânica de tiers (não da tabela em si, essa vem da imagem acima):
`docs/FEE_PROGRAM_README.md` (mesmo commit) — mostra o pseudocódigo TypeScript
`computeFeesBps`/`calculateFeeTier`, que só cai no fallback plano de `Global`/`GlobalConfig`
**se `feeConfig == null`**. Como `fee_config` é conta obrigatória (não opcional) em `buy_v2`/
`sell_v2`/`buy`/`sell` do IDL atual, o caminho tiered é o que roda hoje na prática — o fallback
plano de `Global` (item 1 acima) é best-effort para quem ainda não sabe ler `FeeConfig`.

**Recomendação prática para o T4.1 (e correção precisa a `curve.py`):** não tentar decidir entre
os dois caminhos, nem fixar `CURVE_TRADE_FEE_PCT` como uma constante — `TradeEvent` já entrega
`fee_basis_points`, `fee`, `creator_fee_basis_points`, `creator_fee` **prontos, por trade,
independente de qual caminho o programa usou para calculá-los**. `curve.py`'s
`CURVE_TRADE_FEE_PCT = Decimal("1.25")` não está "errado" (bate com a linha "Bonding curve" da
tabela acima, hoje) mas é uma constante estática descrevendo um parâmetro que o próprio programa
trata como configurável por tier — e o `Global.fee_basis_points` que uma leitura ingênua da conta
mostraria (95 bps) **não é** o número que sai de um `TradeEvent` real numa curva não-tierizada.
Como o módulo já documenta que a constante "nunca é aplicada pelas fórmulas" (é só referência),
não é um bug funcional — é uma nota para não promovê-la a "a" taxa em nenhum uso futuro sem casar
com `TradeEvent`.

Eu não tentei derivar a PDA de `FeeConfig` (`["fee_config", pump_program_id]` sob o programa Pump
Fees) para ler os tiers ao vivo — a derivação de PDA exige checar se o ponto resultante está fora
da curva ed25519 (múltiplas tentativas de bump + decompressão de ponto), que não implementei nesta
pesquisa para não arriscar inventar um endereço errado; a tabela acima (fonte primária, imagem
`fees.png` do repo oficial) e o campo `fee_basis_points` do `TradeEvent` cobrem a necessidade sem
isso.

### 1.5 Fee recipients — as 24 contas fixas

`docs/FEE_RECIPIENTS.md` (mesmo commit): 8 "normais" (moedas não-Mayhem), 8 "reserved" (moedas
Mayhem — item #0 é `Global.reserved_fee_recipient`, itens #1–7 são `Global.reserved_fee_recipients`),
8 "buyback" (qualquer moeda). Lista completa em `.claude/state/notes-T4.0d.md` §1 (24 endereços
base58, não reproduzidos de novo aqui para não duplicar).

---

## 2. PumpSwap (Pump AMM)

Fonte: `docs/PUMP_SWAP_README.md` + `idl/pump_amm.json`, mesmo commit.

### 2.1 `GlobalConfig` (PDA `["global_config"]` → `ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw`)

Campos confirmados no IDL, na ordem: `admin, lp_fee_basis_points, protocol_fee_basis_points,
disable_flags:u8 (bitmask: bit0=create_pool, bit1=deposit, bit2=withdraw, bit3=buy, bit4=sell),
protocol_fee_recipients:[pubkey;8], coin_creator_fee_basis_points, admin_set_coin_creator_authority,
whitelist_pda, reserved_fee_recipient, mayhem_mode_enabled, reserved_fee_recipients:[pubkey;7],
is_cashback_enabled, buyback_fee_recipients:[pubkey;8], buyback_basis_points, boost_authority,
boost_enabled`. Estrutura espelha `Global` do programa Pump quase campo a campo (mesmo padrão de
Mayhem/cashback/buyback), mais dois campos exclusivos do AMM: `boost_authority`/`boost_enabled`
(recurso "boost buy-and-burn" — `boost_buy_and_burn`/`init_boost`/`toggle_boost` no IDL, fora do
escopo de trading desta tarefa, só citado para não parecer omissão).

Não li essa conta ao vivo nesta tarefa (o exemplo estático do README já bate, campo a campo, com
o que o IDL declara — `lp_fee_basis_points=20`, `protocol_fee_basis_points=5`; ver ressalva de
tiers abaixo, que também vale aqui).

### 2.2 `Pool` (PDA `["pool", index, creator, baseMint, quoteMint]`)

Discriminador: decimal `[241, 154, 109, 4, 17, 177, 109, 188]`.

| campo | tipo | nota |
|---|---|---|
| `pool_bump` | u8 | |
| `index` | u16 | pools canônicos (criados por `migrate`/`migrate_v2`) usam `index=0` |
| `creator` | pubkey | criador **do pool** (quase sempre uma PDA `pool_authority` do programa Pump, para pools canônicos) |
| `base_mint`, `quote_mint` | pubkey | |
| `lp_mint` | pubkey | |
| `pool_base_token_account`, `pool_quote_token_account` | pubkey | vaults do pool (ATAs) |
| `lp_supply` | u64 | supply total do LP, **sem** descontar burns/lock-ups |
| `coin_creator` | pubkey | quem recebe a taxa de criador **deste pool** (pode ≠ `Pool.creator`); `Pubkey::default()` em pools anteriores à feature |
| `is_mayhem_mode` | bool | |
| `is_cashback_coin` | bool | |
| `virtual_quote_reserves` | i128 | reserva de quote virtual **adicional** — hoje `0` em todo pool, mas já parte do layout |

**Preço a partir das reservas — a ressalva "effective quote reserves":** `PUMP_SWAP_README.md`
define explicitamente que preço/quote NÃO devem usar o saldo cru do vault de quote, e sim:

```
effective_quote_reserves = pool_quote_token_account.amount + Pool.virtual_quote_reserves
preço = effective_quote_reserves / pool_base_token_account.amount
```

Hoje `virtual_quote_reserves=0` em todo pool então isso equivale ao saldo cru — mas um
decodificador que hardcodar "preço = saldo cru / saldo cru" quebra silenciosamente no dia em que
um pool carregar esse campo não-zero. `BuyEvent`/`SellEvent` já trazem `virtual_quote_reserves` no
próprio evento, então um decodificador de eventos (em vez de leitor de conta) não precisa nem
somar isso manualmente.

### 2.3 Instruções

**`buy`** (disc `66063d1201daebea` — mesmo hex do `buy` legado do programa Pump, mas é outro
programa) / **`sell`** (disc `33e685a4017f83ad`): 23/21 contas — `pool, user, global_config,
base_mint, quote_mint, user_base_token_account, user_quote_token_account,
pool_base_token_account, pool_quote_token_account, protocol_fee_recipient,
protocol_fee_recipient_token_account, base_token_program, quote_token_program, system_program,
associated_token_program, event_authority, program, coin_creator_vault_ata,
coin_creator_vault_authority, global_volume_accumulator(só buy), user_volume_accumulator,
fee_config, fee_program`. Args: `base_amount_out, max_quote_amount_in, track_volume:OptionBool`
(buy) / `base_amount_in, min_quote_amount_out` (sell). Mesma família `buy_exact_quote_in`
(compra por gasto de quote fixo).

**`create_pool`** (disc `e992d18ecf6840bc`, 18 contas) — args `index:u16, base_amount_in:u64,
quote_amount_in:u64, coin_creator:pubkey, is_mayhem_mode:bool, is_cashback_coin:OptionBool`.
**Como a migração cria o pool:** `migrate`/`migrate_v2` do programa **Pump** (não do PumpSwap)
fazem CPI para `create_pool` do PumpSwap, com `creator` = a PDA `pool_authority` do próprio
programa Pump e `index=0` fixo (canonical pool) — confirmado pela lista de contas de `migrate`
(§1.3) incluir `pump_amm, pool, pool_authority, amm_global_config` como contas passadas adiante.
`is_mayhem_mode`/`is_cashback_coin` do novo pool vêm herdados do estado da `BondingCurve` que está
migrando (mesmos nomes de campo dos dois lados).

**`deposit`/`withdraw`** (LP, sem taxa — confirmado em `PUMP_SWAP_README.md`: "No fees are
charged on deposit/withdraw instruction"), **`collect_coin_creator_fee`** (espelha
`collect_creator_fee_v2` do lado curva — §1.3), **`extend_account`**, e instruções admin
(`create_config`, `disable`, `update_admin`, `update_fee_config`) — tabela completa em
`.claude/state/notes-T4.0d.md` §5.

### 2.4 Eventos `BuyEvent`/`SellEvent`

Tão ricos quanto `TradeEvent` do lado curva — trazem `pool_base_token_reserves`,
`pool_quote_token_reserves`, `lp_fee_basis_points`, `lp_fee`, `protocol_fee_basis_points`,
`protocol_fee`, `coin_creator_fee_basis_points`, `coin_creator_fee`, `cashback_fee_basis_points`,
`cashback`, `buyback_fee_basis_points`, `buyback_fee`, `virtual_quote_reserves`, `ix_name:string`,
`base_supply`. Mesma recomendação do §1.4b: ler as taxas efetivas do evento, não recalcular a
partir de `GlobalConfig`/`FeeConfig`.

---

## 3. Mayhem

### 3.1 O que o programa Pump expõe sobre ele (fonte primária, tudo já citado acima)

- `Global.mayhem_mode_enabled: bool` — chave geral (lida ao vivo = `true`).
- `BondingCurve.is_mayhem_mode` / `Pool.is_mayhem_mode` — por token/pool.
- `create_v2` arg `is_mayhem_mode:bool` — só `create_v2` liga isso; `create` (legado) não tem esse
  argumento, então **moedas criadas com `create` nunca são Mayhem**.
- `create_v2` faz CPI para o programa Mayhem (contas `mayhem_program_id, global_params, sol_vault,
  mayhem_state, mayhem_token_vault`) — o estado Mayhem nasce atomicamente com o token, não depois.
- `set_mayhem_virtual_params` (programa Pump, PDA `sol_vault_authority` do Mayhem como signer) —
  como o agente empurra a curva sem passar por `buy`/`sell` convencional; emite
  `UpdateMayhemVirtualParamsEvent`.
- `toggle_mayhem_mode` (Pump e PumpSwap, ambos) — liga/desliga a feature globalmente.
- `TradeEvent.mayhem_mode:bool` / `BuyEvent`/`SellEvent` não têm esse campo do lado PumpSwap (não
  está na lista de campos de `BuyEvent`/`SellEvent` — só `Pool.is_mayhem_mode` na conta).
- Fee recipients "reserved" (§1.5) são exclusivos de trades em moedas Mayhem.

### 3.2 IDL próprio do programa Mayhem — não encontrado

Não há `MAYHEM_README.md` nem IDL de Mayhem no repo `pump-fun/pump-public-docs` (árvore completa
conferida, §"tree" nas notas). Não tentei derivar o endereço da conta on-chain de IDL do Anchor
(`Pubkey::create_with_seed` sobre uma PDA de seeds vazias) porque essa derivação também depende de
uma checagem de curva ed25519 que não implementei nesta pesquisa (mesma ressalva do `FeeConfig`,
§1.4b) — e mesmo que a conta exista, não haveria como confirmar que o formato é o esperado sem
arriscar decodificar bytes errados como se fossem certos. Uma busca de código no GitHub
(`api.github.com/search/code?q=MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e`) **exige autenticação**
(bloqueado sem token, 2026-09-12 02:27 BRT) — não usei um token. Uma tentativa de busca web geral
(DuckDuckGo HTML, sem chave) não retornou nenhum link de GitHub/Solscan relevante. **Conclusão
honesta: o que se sabe do programa Mayhem hoje é (a) o que o programa Pump expõe sobre ele (§3.1,
primário) e (b) a página `pump.fun/docs/mayhem-mode` já citada em `T4-MEME-RADAR.md` (secundário,
mas é a doc oficial do produto, só não é um IDL).**

### 3.3 Identificar os trades do agente

Carteira do agente: `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s` (= `Global.whitelist_pda`,
achado §1.1). Um decodificador de `TradeEvent` que filtrar por `user == essa carteira` OU por
`mayhem_mode == true` pega os trades Mayhem — mas **atenção**: `mayhem_mode=true` no evento marca
"esta moeda está em modo Mayhem", não necessariamente "este trade específico foi feito pelo
agente" (um humano também pode comprar/vender numa moeda Mayhem-ligada durante as 24h). O filtro
correto para "excluir volume do agente" (pedido pelo T4-MEME-RADAR.md, implicação obrigatória #2)
é por **carteira** (`user == BwWK17c...`), não pela flag da moeda.

### 3.4 Manual vs. automático — o que dá para inferir on-chain

Não encontrei, no que li nesta sessão, um campo on-chain que diga "modo Manual" (visto no
screener que o Everton mostrou, per o adendo de `T4-MEME-RADAR.md`). O que existe on-chain é
binário: `is_mayhem_mode` ligado/desligado por token. Hipótese não confirmada: "Manual" pode ser
um modo de operação do **backend/agente** (que trades específicos ele decide fazer dentro dos
limites do programa) sem ser um bit separado na `BondingCurve`/`Pool` — ou pode ser um campo dentro
da conta `mayhem_state` (PDA do próprio programa Mayhem, não decodificada, §3.2). Marcar como
pendência de pesquisa (T4.1b, já citada no plano) em vez de adivinhar.

### 3.5 `MayhemState` — a reserva inicial de uma curva Mayhem e o saldo líquido do agente (T4.2e, 12/09/2026)

**Pergunta da T4.2d:** a fixture `2sduGq…` tinha 822 644 036,902123 tokens reais na curva, mais que os
793 100 000 de `initial_real_token_reserves` do registro de `/global-params`; nem `Global` nem o
registro trazem "reserva Mayhem". Qual é a reserva inicial *daquela* curva? **Resposta, lida da cadeia
em 12/09/2026, 08:43–08:54 BRT (11:43–11:54 UTC), 4 chamadas RPC públicas de 10 permitidas
(`api.mainnet-beta.solana.com`, `finalized`, slots 446421000 / 446422623 / 446422983), fixtures
`packages/exchange-adapters/tests/fixtures/pumpfun/t42e_*`:** a reserva inicial de uma curva Mayhem
**é a do registro** (793,1 M), como a de qualquer curva do programa Pump; o que a empurra acima disso
é o **bilhão do próprio agente**, cunhado ao lado do supply da curva e vendido *líquido* para dentro
dela. Na fixture, `822 644 036,902123 = 793 100 000 + 29 544 036,902123` — até a subunidade.

**As quatro contas por moeda, e de onde vêm os endereços (pela IDL do Pump, `create_v2` /
`set_mayhem_virtual_params`, §1.3):** `bonding_curve` (seeds `["bonding-curve", mint]`, programa
Pump); `mayhem_state` (`["mayhem-state", mint]`, programa `MAyh…`); `mayhem_token_vault` = ATA de
`sol_vault` (`["sol-vault"]`, programa `MAyh…`) sob **Token-2022** (o `token_program` de `create_v2` é
essa constante); e o próprio `mint` (SPL Mint). **`sol_vault` = `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s`
— a "carteira do agente" publicada em `pump.fun/docs/mayhem-mode` é a PDA `sol-vault` do programa Mayhem**,
o que explica o `signer:false` da compra real da A4.1b §5.2 (uma PDA não assina; o programa assina por ela).

**IDL do programa Mayhem: continua não existindo em lugar acessível.** Repositório oficial sem ela
(§3.2) **e** conta de IDL Anchor ausente na cadeia: `create_with_seed(find_program_address([], MAyh),
"anchor:idl", MAyh)` = `Acy6P7eBsmrzz7pxakoGkxhEB9Hcr9XzSJj8RD7yvQS4`, `getAccountInfo` → `value: null`
(`t42e_rpc_mayhem_idl_raw.json`). O que se prova sem ela é a **convenção Anchor dos discriminadores**:
`sha256("account:MayhemState")[:8] = b1fdbf7dcb16866b` e `sha256("account:GlobalParams")[:8] =
79c1f857c3384c0b` batem byte a byte com os 8 primeiros bytes das duas contas (4/4 e 1/1) — os tipos se
chamam `MayhemState` e `GlobalParams`. A `GlobalParams` (318 bytes; começa com `8000, 20 SOL, 20 SOL,
50 M, 50 M` em u64) fica **crua, não interpretada**.

**Layout de `MayhemState` (106 bytes, Borsh, little-endian) — inferido de cinco contas ao vivo e
validado em toda leitura por uma identidade sem constante** (`hunter_exchanges/pumpfun/mayhem_state.py`):

| offset | tamanho | campo | evidência |
|---|---|---|---|
| 0 | 8 | discriminador `b1fdbf7dcb16866b` | convenção Anchor, acima |
| 8 | 8 | u64 `window_start` (unix s) | = `created_timestamp/1000` da REST, 5/5 |
| 16 | 8 | u64 `window_end` | = `window_start + 86 400` (as 24 h do agente), 5/5 |
| 24 | 32 | pubkey `mint` | = o mint pedido, 5/5 |
| 56 | 16 | i128 SOL líquido que o agente pôs na curva (lamports; negativo = retirou) | −0,607 SOL na `2sduGq…` (vendeu), +0,020 SOL na `4BTP…` (comprou) |
| 72 | 16 | i128 tokens líquidos que o agente vendeu para a curva (subunidades; negativo = comprou) | **`cofre + este campo = supply_do_mint − token_total_supply_da_curva` em 5/5** |
| 88 | 18 | cauda não interpretada (u8, u64 ≈ unix s ~14 min após a criação, u8 = 1, 8 zeros) | guardada crua |

**A identidade que valida cada leitura (nenhum número digitado):** o SPL Mint reporta `supply =
2 000 000 000` enquanto `BondingCurve.token_total_supply = 1 000 000 000`; a diferença (o bilhão do
agente) tem de estar ou no cofre (`mayhem_token_vault.amount`) ou na curva (o i128 de 72):

| mint | `rt` da curva | i128@72 (líquido vendido) | cofre | cofre + líquido | `rt − líquido` vs 793,1 M | progresso site vs chain |
|---|---|---|---|---|---|---|
| `2sduGq…` (pausada, manual) | 822 644 036,902123 | +29 544 036,902123 | 970 455 963,097877 | 1 000 000 000 ✓ | **= 793 100 000** (humanos líquido 0; `real_sol` = 1 lamport) | 0 vs −3,7251 % (o site trunca em 0) |
| `4BTP…` (ativa, manual) | 765 908 543,509630 | −9 988 703,539400 | 1 009 988 703,539400 | 1 000 000 000 ✓ | 775 897 247 ≤ ✓ | **3,43 vs 3,4285 %** (0,002 pp) |
| `8pzW…` (ativa, auto) | 636 607 348,093183 | +5 670 068,993381 | 994 329 931,006619 | 1 000 000 000 ✓ | 630 937 279 ≤ ✓ | 24,7 vs 19,73 % (curva moveu ~108 M tokens entre a REST e o RPC; inconclusivo) |
| `668Q…` (pausada, manual) | 690 274 279,549636 | +51 896 841,783969 | 948 103 158,216031 | 1 000 000 000 ✓ | 638 377 437 ≤ ✓ | 8,82 vs 12,97 % (idem, ~74 M entre leituras) |
| `Fh42k…` (fixture T4.1, 6,5 h depois) | **1 713 296 709,488602** | +999 999 991,751764 | 8,248236 | 1 000 000 000 ✓ | 713 296 717 ≤ ✓ | (o agente vendeu o bilhão inteiro: a curva segura 2,16× o inicial) |

Logo `real_token_reserves = inicial − líquido_humanos + líquido_agente`, com `inicial` = o do registro
(igualdade exata na `2sduGq…`, e o progresso do site reproduzido em 0,002 pp na `4BTP…`). O radar escreve
esse inicial com `progress_denominator_source = mayhem_state` (`0025`) **só depois** de ler as quatro
contas no mesmo slot e fechar a identidade; `1 − rt/inicial` fica **negativo** quando o agente vendeu
mais do que os humanos compraram (o site mostra 0; nós guardamos o número — `features.py` não trunca;
o portão da EXP-M1 recusa por `progress_below_min`). O limiar de enchimento em SOL do registro (85,005
SOL) **não** se aplica a Mayhem: `set_mayhem_virtual_params` move o SOL virtual (0,46–27,9 SOL nas
cinco curvas contra os 30 do registro), então `curve_filled_seen_at` não é reivindicado para elas.
O `mayhemBotCoinSupplied` do indexer (14,39 / 1,60 / 65,57 / 18,92) não é nem tokens nem SOL líquidos
destas contas — unidade desconhecida, não usada. Comandos e saídas: `.claude/state/notes-T4.2e.md`.

---

## 4. Decodificadores open-source comparados

| Repo | Estrelas | Último push | Linguagem | Cobertura pump.fun | Observação |
|---|---|---|---|---|---|
| `pump-fun/pump-public-docs` | 450 | 2026-07-15 | — | IDL oficial (fonte primária desta pesquisa) | README defasado vs. IDL (§1) |
| `chainstacklabs/pumpfun-bonkfun-bot` | 985 | 2026-08-24 | Python | create/buy_v2/sell_v2, estado da curva, migração | já escolhido em T4.0; decodifica direto de Geyser/logs/blockSubscribe, IDL vendorizada oficial |
| `0xfnzero/sol-trade-sdk` | 339 | **2026-09-08** | Rust | PumpFun **V1 vs V2** explicitamente documentado, PumpSwap, **cashback** | mais recente de todos os candidatos (4 dias antes desta pesquisa); é o único que eu vi tratar V1/V2 e cashback como seções próprias da doc — sinal de que acompanha o IDL atual de perto |
| `cxcx-ai/solana-dex-parser` | 114 | 2025-10-02 | TypeScript | create/trade/complete via `PumpfunEventParser`, multi-DEX (Jupiter/Raydium/Meteora/PumpSwap/Moonit) | ~1 ano parado relativo a esta pesquisa — quase certamente **anterior** a `buy_v2`/`sell_v2`/cashback/multi-quote; bom para o parsing genérico de create/trade/complete legado, não confiar nele para V2 |
| `rckprtr/pumpdotfun-sdk` | 821 | 2025-04-11 | TypeScript | pré-PumpSwap | citado em T4.0; **não recomendado**, parado há ~17 meses |
| `nirholas/pump-fun-sdk` | 121 | 2026-09-12 | TypeScript | criação/curva/migração AMM/taxas escalonadas/MCP server | citado em T4.0, ativo no próprio dia |
| `0xfnzero/sol-shred-sdk` | 15 | 2026-08-31 | Rust | decodificador genérico Solana (shreds), não específico | citado em T4.0 |

Nenhum desses foi de fato instalado/rodado nesta tarefa — a comparação é por metadado do
GitHub (estrelas, `pushed_at`) e pela própria descrição/README de cada repo, lidos ao vivo em
2026-09-12 ~02:3x BRT via `api.github.com`/`raw.githubusercontent.com`. Recomendação: manter
`chainstacklabs/pumpfun-bonkfun-bot` como referência primária (T4.0 já decidiu isso e o IDL bate
com `decode.py`), e usar `0xfnzero/sol-trade-sdk` como segunda referência cruzada especificamente
para os campos V2/cashback/multi-quote mais novos, dado que é o candidato com o push mais recente
tratando exatamente essas features como de primeira classe.

---

## 5. Caminhos de leitura e seus custos

### 5.1 Limites oficiais do RPC público (`api.mainnet-beta.solana.com`)

Fonte primária, lida ao vivo em 2026-09-12 02:29 BRT:
`https://solana.com/docs/references/clusters` (seção "Mainnet" → rate limits):

- Máx. 100 requisições/10s por IP (≈10 req/s, **todos os métodos somados**)
- Máx. **40 requisições/10s por IP para um único método RPC** (≈4 req/s por método — ex.: no
  máximo ~4 `getTransaction`/s mesmo que o orçamento total permita mais)
- Máx. 40 conexões concorrentes por IP
- Máx. 40 novas conexões/10s por IP
- Máx. 100 MB de dados/30s

A página não menciona `websocket`/`wss://`/`logsSubscribe` em nenhum lugar (busquei o texto
inteiro) — **não há limite ou garantia de capacidade documentada oficialmente para WS no endpoint
público**. Não testei `logsSubscribe`/`programSubscribe` ao vivo nesta sessão (exigiria um cliente
WS que não confirmei disponível no ambiente) — não invento um número de capacidade para isso.

### 5.2 Custo por trade via polling REST

Padrão `getSignaturesForAddress(bonding_curve)` + `getTransaction(signature)` por assinatura nova:
- 1 chamada de `getSignaturesForAddress` por ciclo de poll, por token monitorado — **não
  depende de quantos trades aconteceram**, só de quantos tokens você observa.
- +1 chamada de `getTransaction` por assinatura **nova** desde o último poll — este sim escala
  com o volume real de trades, não com N.

### 5.3 Tabela "quanto o RPC público grátis aguenta, para N tokens"

Assumindo poll a cada `T` segundos e usando só o teto **por método** (40/10s = 4/s, o mais
apertado dos dois tetos para este padrão de acesso):

| Intervalo de poll `T` | N tokens sustentável só para "houve trade novo?" (`getSignaturesForAddress` ≤ 4/s) | Sobra no teto total (10/s) para `getTransaction` |
|---|---|---|
| 1 s | 4 | ~6/s — decodifica só ~6 trades/s **somando todos os 4 tokens** |
| 5 s | 20 | ~8/s (10 − 20/5) — ~8 trades/s somando os 20 tokens |
| 10 s | 40 (empata no teto do método) | ~6/s (10 − 40/10) — ~6 trades/s somando os 40 tokens, com até 10 s de atraso para notar um trade |

Conclusão aritmética, não qualitativa: mesmo no cenário mais folgado da tabela (poll de 10 s, pior
frescor), o RPC público sustenta **ordens de grandeza menos** que os "~30-52 mil tokens criados/dia"
citados em `T4-MEME-RADAR.md` §4 — e um único token popular nos primeiros minutos já pode gerar
dezenas de trades por segundo sozinho, estourando o orçamento inteiro. Isso quantifica (não só
qualifica) a conclusão que T4.0/T4.0b já tinham chegado por outra via: **polling REST no RPC
público não é uma estratégia viável para trades em escala**, só para leituras pontuais/getAccountInfo
sob demanda (que é o que este próprio documento fez, ≤5 chamadas RPC no total).

### 5.4 Alternativas (números já confirmados em T4.0/T4.0b, citados aqui por completude)

| Fonte | Custo | Nota |
|---|---|---|
| PumpPortal WS | grátis (`subscribeNewToken`/`subscribeMigration`); pago (`subscribeTokenTrade`/`subscribeAccountTrade`, 0,01 SOL/10k eventos) | `.claude/state/notes-T4.0.md` §3 |
| Helius Free | 1.000.000 créditos/mês, **10 req/s**, 1 `sendTransaction`/s, LaserStream WSS padrão | confirmado de novo nesta tarefa, `helius.dev/pricing`, lido 2026-09-12 02:30 BRT — bate com T4.0b |
| Helius Developer (US$49/mês) | 10M créditos/mês, 50 req/s, LaserStream gRPC só em **devnet** | idem |
| Helius Business (US$499/mês) | 100M créditos/mês, 200 req/s, LaserStream **gRPC em mainnet** — piso real para Geyser gerenciado | idem — é aqui que o custo de "todos os tokens, sem polling" aparece |
| Helius Professional (US$999/mês) | 200M créditos/mês, 500 req/s | idem |
| Helius Enhanced Transactions History / Webhooks | existe (endereço parseado, push via webhook) | não confirmei o path exato do endpoint nesta sessão (a doc não carregou o conteúdo renderizado via `curl` simples) — não cito uma URL específica |
| QuickNode Build (US$49/mês, US$34/mês anual) | 10M créditos, 15 req/s, trial de 1 mês | `.claude/state/notes-T4.0b.md`, não re-verificado nesta tarefa |
| Bitquery | trial 7 dias/1000 pontos; Personal/Pro/Scale US$99/US$299+/mês | idem, não re-verificado |

---

### 5.5 Leitura em lote da curva de todos os rastreados — `getMultipleAccounts` (T4.2f, 12/09/2026)

**O que foi medido** (10:07 e 10:36 BRT; 6 chamadas RPC públicas de 10 permitidas, sem chave; fixtures
`t42f_rpc_curves_batch{1,2}_{raw,addresses}.json`, `t42f_rpc_block_time_raw.json`, `t42f_capture_http_log.json`):
os 140 mints mais novos de `/coins` (2 páginas de 70), com a PDA `["bonding-curve", mint]` derivada localmente
(`tx.bonding_curve_address`) **igual ao `bonding_curve` da REST em 140/140** — o laço lê qualquer rastreado sem
depender do frame do PumpPortal; `getMultipleAccounts` de 100 contas em **467 ms / 34,6 KB** (slot 446436963) e de
41 em 187 ms (slot 446436965); `getBlockTime` dos dois slots = 13:07:47Z e 13:07:48Z, **~11 s antes** do
`received_at` (13:07:58Z) — a finalidade, e por isso `observed_at` é o blockTime. Na cadeia: **115 curvas em SOL**
(79 + 36); **23 com quote ≠ SOL** (6 USDC `EPjFWdd5…`, 6 `pumpCmXq…`, 11 `Xs…`/`DoGE…`/`RDDT…`) — 16 % das moedas
novas, invisíveis ao adaptador só-SOL por construção (`unsupported_quote`, nomeado, o mint sai do conjunto);
**2 esvaziadas** (`complete = true` e todas as reservas zero: é o que `migrate` deixa na conta; a REST mantém os
números pré-migração — o sinal de migração da própria cadeia, `curve_emptied`); 1 endereço-sonda que não é curva
(`owner = System`, 0 bytes, 1,4 SOL de lamports → `curve_not_found`). Tamanhos de conta: 124 bytes (55) e 151
(45) — `extend_account` já correu à frente; o decodificador lê os 115 mínimos. **Nenhuma** das 79 curvas SOL do
lote 1 estava virgem (`real_sol_reserves = 0`): toda moeda nasce com a compra do criador, logo `observed_virgin`
é a exceção e `global_params` a regra do denominador. REST e cadeia coincidiram exatamente em 113/140 (leituras
30 s distantes, não atômicas).

**Cabeçalhos do próprio RPC público** (na resposta, não na doc): `x-ratelimit-tier: free`,
`x-ratelimit-rps-limit: 250`, **`x-ratelimit-method-limit: 10`** (`remaining` 9 → 8 em duas chamadas do mesmo
método), `x-ratelimit-conn-limit: 40`, `x-ratelimit-connrate-limit: 40`, `x-ratelimit-pubsub-limit: 10`. O teto
por método é **10**, não os 40/10 s da §5.1 (a página de `solana.com`); o cliente espaça uma chamada por segundo
por método (`rpc.METHOD_SPACING_S`). O RPC recusou com 403 as duas primeiras chamadas feitas com `Origin`/
`User-Agent` do site — sem esses cabeçalhos, 200.

**O laço** (`services/meme-worker/hunter_meme_worker/chain.py`, `MEME_CHAIN_CURVES_ENABLED`): uma vez por minuto,
todos os rastreados (≈ 130 → 2 `getMultipleAccounts` + 1–2 `getBlockTime` ≈ 4 chamadas/min contra `rps 250` e
`method 10`), decodificados pela IDL (`decode.py`), gravados em `meme_curve_snapshots` com `source = 'solana_rpc'`,
`slot`, `commitment = 'finalized'` e `observed_at` = blockTime (senão `received_at`, contado em
`chain_block_time_missing_60s`), pelo **mesmo caminho da T4.2d** (`persist_reading`: denominador
`global_params`/`observed_virgin`, sinais de conclusão, tracker, fold). O poll REST (60/min) fica só para o que
o espelho ensina sozinho (`tracker.needs_rest`: `mayhem_state` de mint nunca lido, agente `active`/`paused` a
cada `MEME_REST_MAYHEM_REFRESH_S`, leitura final, apostas abertas) e volta ao plano cheio se o laço falhar por
dois ciclos; a reconciliação top-K não roda com o laço ligado. Heartbeat: `chain_cycle_s`,
`chain_tracked_mints`, `chain_read_mints`, `chain_calls_60s`, `chain_refused_1h`, `chain_block_time_missing_60s`.

---

## 6. O que a execução vai precisar depois (descrição, sem código de assinatura)

**Compra/venda na curva (`buy_v2`/`sell_v2`):** transação com, no mínimo, as 26-27 contas listadas
em §1.3 — a maioria são PDAs determinísticos (deriváveis a partir de `mint` e endereços fixos do
programa) e ATAs (deriváveis a partir de mint+owner+token program), exceto a escolha de
`fee_recipient`/`buyback_fee_recipient` (um dos 8 de cada lista, §1.5 — a doc recomenda escolher
aleatoriamente para distribuir carga/throughput, não é uma escolha "livre" no sentido de conteúdo).
Args: quantidade de token (`amount`, unidades cruas de 6 casas) + teto/piso de quote
(`max_sol_cost`/`min_sol_output`, unidades cruas de lamports ou do quote mint) — **é aqui que
entra o slippage**: não há um parâmetro de "% de slippage" na instrução, o chamador calcula o
teto/piso a partir do preço esperado e da tolerância desejada antes de montar a transação.

**Compra/venda no PumpSwap (`buy`/`sell`):** 21-23 contas (§2.3), mesmo padrão de slippage via
`max_quote_amount_in`/`min_quote_amount_out`.

**Criação de ATA:** `buy_v2`/`sell_v2` e o `buy`/`sell` do PumpSwap esperam várias ATAs já
existentes ou criadas `init_if_needed` na própria transação (associated_token_program está sempre
na lista de contas) — várias linhas de `docs/instructions/BUY.md` citam custo de aluguel exato
quando a conta precisa ser criada (ex.: `user_volume_accumulator` = 0,0018444 SOL se ainda não
existir). Uma implementação de execução real precisa checar a existência de cada ATA antes de
montar a transação e decidir se inclui a instrução de criação (ou usar "create idempotent
associated token account", citado em `docs/PUMP_CASHBACK_README.md` para o claim de cashback).

**Compute budget / priority fee:** os exemplos de SDK Rust em `docs/instructions/BUY.md` e
`COLLECT_CREATOR_FEE.md` (mesmo commit, primário) prependem
`ComputeBudgetInstruction::set_compute_unit_limit(...)` — **400.000 CU** para `buy_v2`/`sell_v2`/
`create_v2_and_buy`, **200.000 CU** para `collect_creator_fee_v2`/`collect_coin_creator_fee`. Não
há, nesses exemplos, uma chamada a `set_compute_unit_price` (o preço por CU, que é como se paga
"priority fee" na Solana) — isso fica a critério de quem monta a transação, não é parte do
protocolo do pump.fun. Não documentado nesta pesquisa: qual preço por CU é necessário para incluir
rápido numa moeda popular (isso é uma característica do mercado de blockspace no momento, não do
programa).

**Jito tips:** o pump.fun em si não define contas de tip Jito (isso é infraestrutura de
submissão de transação, ortogonal ao programa) — não encontrei nenhuma menção a Jito em nenhum dos
documentos primários lidos nesta tarefa. Uma implementação que queira usar bundles Jito adicionaria
uma instrução de transferência para uma das contas de tip do Jito Block Engine por fora do que
está documentado aqui; não é algo que este mapa on-chain do pump.fun cobre porque não é parte dele.

**Nada disto inclui código de assinatura de transação** — por instrução explícita do brief, e
porque monta transação ≠ assina/envia transação (o próximo seria uma tarefa de execução, com as
chaves fora do escopo desta pesquisa).

---

## 6b. O que o construtor de instruções faz hoje (T4.8, 2026-09-12)

`packages/exchange-adapters/hunter_exchanges/pumpfun/tx.py` monta `buy` (disc `66063d1201daebea`)
e `sell` (disc `33e685a4017f83ad`) — as instruções legadas só-SOL, que são as que o próprio site
usa hoje (o `swap-build` do site devolve uma transação v0 que roteia por `6Vo3245…` e faz CPI
em `buy`, capturado em `tests/fixtures/pumpfun/rpc_tx_buy_raw.json`). Tudo puro; toda conta é
derivada ou lida de estado:

| Conta | De onde vem |
|---|---|
| `global`, `event_authority`, `global_volume_accumulator` | PDAs do programa Pump (`solana_codec.find_program_address`, com a checagem ed25519 que a §1.4b dizia faltar) |
| `fee_config` | PDA `["fee_config", pump_program_id]` **sob o programa Pump Fees** = `8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt` (conferido na cadeia) |
| `bonding_curve`, `associated_bonding_curve`, `associated_user`, `creator_vault`, `user_volume_accumulator` | PDAs/ATAs de `mint`, `creator` (da conta `BondingCurve`) e `user`; o **token program vem do owner do mint** (a moeda da fixture é Token-2022) |
| `fee_recipient` | um dos 8 de `Global` — normais para moeda comum, **reservados** (`reserved_fee_recipient(s)`) quando `BondingCurve.is_mayhem_mode` (é isto o "vault Mayhem" da execução); qualquer outro endereço é recusado pelo construtor e pelo verificador |
| `buyback_fee_recipient` | um dos 8 `Global.buyback_fee_recipients` |

**Duas coisas que a IDL não diz (confirmadas em duas transações reais e por simulação):**

1. **Remaining accounts.** O programa exige, depois das contas da IDL, `[<conta não documentada>,
   buyback_fee_recipient]` no `buy` e `[user_volume_accumulator, <conta não documentada>,
   buyback_fee_recipient]` no `sell`. A conta não documentada é sempre
   `4CLQeN5wrddJ9adY3GJGSTyu1AEKD4Ta14RffSy5aHud` (read-only, **não existe** na cadeia —
   `rpc_account_4CLQ_raw.json`; não é PDA derivável sob os quatro programas nem ATA de nada
   envolvido; nem a IDL `main` do GitHub nem a IDL on-chain a nomeiam). Sem ela o programa falha
   com `BuybackFeeRecipientMissing` (6062) — o slot é posicional. Guardada literalmente em
   `tx.UNDOCUMENTED_REMAINING_ACCOUNT`, com esse aviso.
2. **`track_volume: OptionBool` vai ausente** (dados de 24 bytes) nas duas transações reais; só é
   anexado quando o chamador passa `True`/`False` explicitamente.

**Taxas, medidas na cadeia (não na doc):** `GetFeesWithQuoteMint` devolveu `lp 0 / protocolo 95 /
criador 30` bps nas duas fixtures. Cada componente é arredondado **para cima** sobre `sol_amount`;
em moeda *cashback* os 30 bps viram `cashback` (creator_fee = 0 no evento) mas **saem igualmente da
carteira** — reconciliado lamport a lamport: delta do vendedor = `sol_amount − fee − cashback −
taxa de rede − tip`. `buy`: `sol_amount = ⌊a·vsol/(vtok−a)⌋ + 1`; `sell`: `⌊a·vsol/(vtok+a)⌋`;
`max_sol_cost` é comparado com o custo **com taxas** (simulação: `total_cost − 1` → `TooMuchSolRequired`).
Cotação local em `quote.py`; contra o `swap-build` do site (0,01 SOL exact-in) a diferença foi
`−9,8 × 10⁻⁶` em tokens (`test_pumpfun_quote.py`).

**Prova de execução:** `simulateTransaction` na mainnet, `sigVerify=false`, pagador sem assinatura
(nunca enviada): `buy` 18 contas OK (65.345 CU), `sell` 17 contas OK (55.284 CU) —
`simulation_proof_mainnet_raw.json`. O programa e o `Global` existem na **devnet** (atividade às
08:01 UTC de 2026-09-12), mas o faucet público recusou o airdrop (`-32603`), por isso não houve envio
em rede nenhuma nesta tarefa.

## 7. Resumo acionável para T4.1/Astra

1. `decode.py` (layout de `BondingCurve`) está **correto e bate byte a byte com o IDL oficial** —
   nenhuma mudança necessária.
2. `curve.py.CURVE_TRADE_FEE_PCT=1.25%` bate com a linha "Bonding curve" da tabela de tiers hoje,
   mas é melhor documentá-la como "tier atual, não uma taxa fixa do protocolo" e apontar quem for
   calcular fills a ler `fee_basis_points`/`creator_fee_basis_points` direto do `TradeEvent`
   (§1.4b) em vez de reimplementar `computeFeesBps`.
3. `models.py`/`normalize.py` já assumem SOL como único quote — `Global.whitelisted_quote_mints`
   confirma que **USDC já é um quote mint real e habilitado hoje** (`add_quote_mint` foi chamado
   pelo menos uma vez). Não é urgente (T4.1 pode continuar só-SOL), mas é uma lacuna conhecida a
   documentar, não a ignorar.
4. Se algum dia um decodificador de eventos on-chain for construído (em vez de depender só de
   PumpPortal), os discriminadores/campos de `CreateEvent`/`TradeEvent`/`CompleteEvent`/
   `CompletePumpAmmMigrationEvent` (§1.4/§2.4) são a fonte; `ix_name` no evento evita ter que
   inferir qual instrução rodou.
5. Mayhem: filtrar por carteira `BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s` (não pela flag da
   moeda) para excluir volume do agente, conforme a implicação obrigatória #2 do adendo de
   `T4-MEME-RADAR.md`.

---

## Fontes (resumo — lista completa com comandos em `.claude/state/notes-T4.0d.md`)

- `github.com/pump-fun/pump-public-docs`, commit `9c82f61cb711b044a17f770ab8ce9f9bdf78f333`:
  `README.md`, `docs/PUMP_PROGRAM_README.md`, `docs/PUMP_SWAP_README.md`,
  `docs/PUMP_SWAP_SDK_README.md`, `docs/FEE_PROGRAM_README.md`, `docs/FEE_RECIPIENTS.md`,
  `docs/BREAKING_FEE_RECIPIENT.md`, `docs/PUMP_CASHBACK_README.md`,
  `docs/PUMP_CREATOR_FEE_README.md`, `docs/PUMP_SWAP_CREATOR_FEE_README.md`, `docs/CPI_README.md`,
  `docs/FAQ.md`, `docs/instructions/{BUY,SELL,COIN_CREATION,COLLECT_CREATOR_FEE,
  CREATOR_FEE_SHARING,CLAIM_CASHBACK}.md`, `docs/fees.png`, `idl/{pump,pump_amm,pump_fees}.json` —
  todos lidos via `raw.githubusercontent.com/.../9c82f61.../<path>` em 2026-09-12 ~02:22–02:28 BRT.
- `https://api.mainnet-beta.solana.com` (RPC público, sem chave): `getAccountInfo` em
  `4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf` (`Global`, 02:24:15 BRT, slot 446349159) e em
  `MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e` (programa Mayhem, 02:28:22 BRT). Total: **2
  chamadas RPC nesta tarefa**, dentro do limite de ≤20 do brief.
- `https://solana.com/docs/references/clusters`, lido 2026-09-12 02:29 BRT (limites do RPC
  público mainnet).
- `https://www.helius.dev/pricing`, lido 2026-09-12 02:30 BRT (tiers Free/Developer/Business/
  Professional).
- `api.github.com/repos/pump-fun/pump-public-docs`, `.../commits/main`,
  `.../git/trees/main?recursive=1`; `api.github.com/search/repositories?q=...` para os candidatos
  de decodificador (§4); `api.github.com/repos/0xfnzero/sol-trade-sdk`,
  `.../repos/cxcx-ai/solana-dex-parser` — todos lidos ~02:22–02:33 BRT.
- `.claude/state/notes-T4.0.md`, `.claude/state/notes-T4.0b.md`, `docs/plans/T4-MEME-RADAR.md` —
  pesquisa anterior (T4.0/T4.0b), citada e não reaberta quando os números não mudaram.
