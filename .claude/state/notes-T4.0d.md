# Notas de pesquisa — T4.0d Mapa on-chain do pump.fun

Sessão: 2026-09-12, madrugada, ~02:20–02:35 BRT (05:20–05:35 UTC, BRT = UTC−3, sem DST — mesma
convenção de `.claude/state/notes-T4.0.md`). Documento principal: `docs/PUMPFUN-ONCHAIN.md`. Este
arquivo guarda os comandos exatos, as respostas cruas relevantes e os apêndices completos (tabela
das 40+31 instruções) que não couberam no documento de referência sem inchá-lo.

Ambiente: todo o trabalho usou `Bash` (Git Bash / MSYS no Windows) + `uv run python` (venv do
projeto, `C:/dev/project-hunter`) para parsear JSON — **achado de ambiente**: caminhos com mais de
~260 caracteres (o diretório de scratchpad designado para esta sessão é um deles) fazem
`python.exe` nativo do Windows falhar com `FileNotFoundError` mesmo quando `ls`/`cat` do Git Bash
enxergam o arquivo normalmente (limite clássico `MAX_PATH`, sem long-path habilitado para esse
interpretador). Usei `C:/pf-t40d/` (caminho curto, fora do repo, fora de `.env*`) como scratch de
trabalho para todo arquivo que precisou ser lido por `uv run python`; nada ali é um deliverable.

## 1. Fee recipients completos (`docs/FEE_RECIPIENTS.md`, commit `9c82f61...`)

Normal (não-Mayhem), índice 0 = `Global.fee_recipient`, 1-7 = `Global.fee_recipients[7]`:
```
62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV
7VtfL8fvgNfhz17qKRMjzQEXgbdpnHHHQRh54R9jP2RJ
7hTckgnGnLQR6sdH7YkqFTAA7VwTfYFaZ6EhEsU3saCX
9rPYyANsfQZw3DnDmKE3YCQF5E8oD89UXoHn9JFEhJUz
AVmoTthdrX6tKt4nDjco2D775W2YK3sDhxPcMmzUAmTY
CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM
FWsW1xNtWscwNmKv6wVsU1iTzRN6wmmk3MjxRP5tT7hz
G5UZAVbAf46s7cKWoyKu8kYTip9DGTpbLZ2qa9Aq69dP
```
Reserved (Mayhem), índice 0 = `Global.reserved_fee_recipient`, 1-7 = `Global.reserved_fee_recipients[7]`:
```
GesfTA3X2arioaHp8bbKdjG9vJtskViWACZoYvxp4twS
4budycTjhs9fD6xw62VBducVTNgMgJJ5BgtKq7mAZwn6
8SBKzEQU4nLSzcwF4a74F2iaUDQyTfjGndn6qUWBnrpR
4UQeTP1T39KZ9Sfxzo3WR5skgsaP6NZa87BAkuazLEKH
8sNeir4QsLsJdYpc9RZacohhK1Y5FLU3nC5LXgYB4aa6
Fh9HmeLNUMVCvejxCtCL2DbYaRyBFVJ5xrWkLnMH6fdk
463MEnMeGyJekNZFQSTUABBEbLnvMTALbT6ZmsxAbAdq
6AUH3WEHucYZyC61hqpqYUWVto5qA5hjHuNQ32GNnNxA
```
Buyback (qualquer moeda), = `Global.buyback_fee_recipients[8]`:
```
5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD
9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7
GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL
3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR
5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6
EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL
5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD
A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW
```
Confirmado: os primeiros 3 "normal" e os primeiros 8 "reserved"/"buyback" batem com os arrays
lidos ao vivo na conta `Global` (§2 abaixo), campo a campo.

## 2. Leitura AO VIVO de `Global` — comando e resultado completo

Comando (RPC call #1 desta tarefa):
```
curl -sS -X POST https://api.mainnet-beta.solana.com \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getAccountInfo","params":["4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf",{"encoding":"base64"}]}'
```
Executado 2026-09-12T05:24:15Z (02:24:15 BRT). Resposta: `slot=446349159`, `owner=6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`,
`lamports=4089670190`, `space=1054`. Discriminador dos primeiros 8 bytes decodificados = decimal
`[167, 232, 232, 177, 200, 108, 114, 127]` — bate exatamente com `accounts[name=Global].discriminator`
do IDL oficial (`idl/pump.json`, mesmo commit). 1045 de 1054 bytes decodificados (9 bytes de cauda
não mapeados no IDL lido — provavelmente slack de `extend_account` para o próximo campo futuro).

Script de decodificação usado (Borsh/Anchor puro — sem libs externas, base58 encoder manual igual
ao de `decode.py`): salvo nesta tarefa em `C:/pf-t40d/decode_global.py` (fora do repo, não é
deliverable; reproduzido aqui por transparência, mas quem quiser repetir deve escrever um script
equivalente, não depender deste path de scratch):

```python
import base64, json, struct, sys
_B58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58encode(raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    out = bytearray()
    while n > 0:
        n, rem = divmod(n, 58)
        out.append(_B58_ALPHABET[rem])
    out.reverse()
    pad = 0
    for byte in raw:
        if byte != 0:
            break
        pad += 1
    return (_B58_ALPHABET[0:1] * pad + out).decode("ascii")

# raw = base64.b64decode(resp["result"]["value"]["data"][0])
# off = 8  (pula discriminador)
# depois: bool=1 byte, u64=struct.unpack_from("<Q", raw, off), pubkey=b58encode(raw[off:off+32])
# na ordem exata de idl/pump.json -> types[name=Global].type.fields
```

Resultado completo (JSON, todos os 25 campos, arrays truncados na doc principal mas completos
aqui):

```json
{
  "initialized": true,
  "authority": "FFWtrEQ4B4PKQoVuHYzZq8FabGkVatYzDpEVHsK5rrhF",
  "fee_recipient": "62qc2CNXwrYqQScmEdiZFFAnJR262PxWEuNQtxfafNgV",
  "initial_virtual_token_reserves": 1073000000000000,
  "initial_virtual_sol_reserves": 30000000000,
  "initial_real_token_reserves": 793100000000000,
  "token_total_supply": 1000000000000000,
  "fee_basis_points": 95,
  "withdraw_authority": "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg",
  "enable_migrate": true,
  "pool_migration_fee": 15000001,
  "creator_fee_basis_points": 5,
  "fee_recipients": ["7VtfL8fvgNfhz17qKRMjzQEXgbdpnHHHQRh54R9jP2RJ", "7hTckgnGnLQR6sdH7YkqFTAA7VwTfYFaZ6EhEsU3saCX", "9rPYyANsfQZw3DnDmKE3YCQF5E8oD89UXoHn9JFEhJUz", "AVmoTthdrX6tKt4nDjco2D775W2YK3sDhxPcMmzUAmTY", "CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM", "FWsW1xNtWscwNmKv6wVsU1iTzRN6wmmk3MjxRP5tT7hz", "G5UZAVbAf46s7cKWoyKu8kYTip9DGTpbLZ2qa9Aq69dP"],
  "set_creator_authority": "39azUYFWPz3VHgKCf3VChUwbpURdCHRxjWVowf5jUJjg",
  "admin_set_creator_authority": "UqN2p5bAzBqYdHXcgB6WLtuVrdvmy9JSAtgqZb3CMKw",
  "create_v2_enabled": true,
  "whitelist_pda": "BwWK17cbHxwWBKZkUYvzxLcNQ1YVyaFezduWbtm2de6s",
  "reserved_fee_recipient": "GesfTA3X2arioaHp8bbKdjG9vJtskViWACZoYvxp4twS",
  "mayhem_mode_enabled": true,
  "reserved_fee_recipients": ["4budycTjhs9fD6xw62VBducVTNgMgJJ5BgtKq7mAZwn6", "8SBKzEQU4nLSzcwF4a74F2iaUDQyTfjGndn6qUWBnrpR", "4UQeTP1T39KZ9Sfxzo3WR5skgsaP6NZa87BAkuazLEKH", "8sNeir4QsLsJdYpc9RZacohhK1Y5FLU3nC5LXgYB4aa6", "Fh9HmeLNUMVCvejxCtCL2DbYaRyBFVJ5xrWkLnMH6fdk", "463MEnMeGyJekNZFQSTUABBEbLnvMTALbT6ZmsxAbAdq", "6AUH3WEHucYZyC61hqpqYUWVto5qA5hjHuNQ32GNnNxA"],
  "is_cashback_enabled": true,
  "buyback_fee_recipients": ["5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD", "9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7", "GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL", "3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR", "5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6", "EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL", "5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD", "A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW"],
  "buyback_basis_points": 5000,
  "initial_virtual_quote_reserves": 4292000000,
  "whitelisted_quote_mints": ["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"]
}
```

`EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v` é o mint canônico de USDC na Solana (fato de
conhecimento geral do ecossistema, não verificado por uma chamada RPC separada nesta tarefa — dado
o contexto (`whitelisted_quote_mints`, `add_quote_mint` existir no IDL, `COIN_CREATION.md` citar
literalmente esse mesmo endereço como exemplo de `quoteMint` para "USDC-Paired Mint"), a
identificação é seguramente correta).

## 3. Confirmação do programa Mayhem (RPC call #2)

```
curl -sS -X POST https://api.mainnet-beta.solana.com \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"getAccountInfo","params":["MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e",{"encoding":"base64"}]}'
```
Executado 2026-09-12T05:28:22Z (02:28:22 BRT). Resposta: `executable=true`,
`owner=BPFLoaderUpgradeab1e11111111111111111111111`, `lamports=11149834`, `space=36` — formato
padrão de uma conta `Program` (não `ProgramData`) apontando para sua conta de dados via upgrade
loader. Confirma que o programa está de fato implantado e é upgradeable; não decodifiquei o
conteúdo dos 36 bytes (é um formato fixo e conhecido do loader, não do pump.fun, e não adiciona
nada ao mapa).

**Total de chamadas RPC ao público `api.mainnet-beta.solana.com` nesta tarefa: 2** (bem dentro do
limite de ≤20 do brief). Não tentei derivar PDAs (`FeeConfig`, `global_params`/`sol_vault`/
`mayhem_state` do Mayhem, IDL on-chain do Mayhem) porque a derivação correta de PDA exige checar se
o ponto de 32 bytes resultante está fora da curva ed25519 (decompressão de ponto + busca de bump),
que não implementei nesta pesquisa — risco de decodificar endereço/conta errada e reportar como
certa, o que violaria a disciplina "nunca inventar um número que a entrada não tem" que o próprio
`decode.py` já segue.

## 4. Tabela completa — 40 instruções do programa Pump (`idl/pump.json`)

(nome, discriminador hex, contas na ordem do IDL, args)

```
add_quote_mint (6f79153828185ed1): global, authority, event_authority, program | quote_mint:pubkey
admin_set_creator (4519ab8e39ef0d04): admin_set_creator_authority, global, mint, bonding_curve, event_authority, program | creator:pubkey
admin_set_idl_authority (08d960e79068c005): authority, global, idl_account, system_program, program_signer, event_authority, program | idl_authority:pubkey
admin_update_token_incentives (d10b7357d5177ccc): authority, global, global_volume_accumulator, mint, global_incentive_token_account, associated_token_program, system_program, token_program, event_authority, program | start_time:i64, end_time:i64, seconds_in_a_day:i64, day_number:u64, pump_token_supply_per_day:u64
buy (66063d1201daebea): global, fee_recipient, mint, bonding_curve, associated_bonding_curve, associated_user, user, system_program, token_program, creator_vault, event_authority, program, global_volume_accumulator, user_volume_accumulator, fee_config, fee_program | amount:u64, max_sol_cost:u64, track_volume:OptionBool
buy_exact_quote_in_v2 (c2ab1c46684d5b2f): global, base_mint, quote_mint, base_token_program, quote_token_program, associated_token_program, fee_recipient, associated_quote_fee_recipient, buyback_fee_recipient, associated_quote_buyback_fee_recipient, bonding_curve, associated_base_bonding_curve, associated_quote_bonding_curve, user, associated_base_user, associated_quote_user, creator_vault, associated_creator_vault, sharing_config, global_volume_accumulator, user_volume_accumulator, associated_user_volume_accumulator, fee_config, fee_program, system_program, event_authority, program | spendable_quote_in:u64, min_tokens_out:u64
buy_exact_sol_in (38fc74089edfcd5f): global, fee_recipient, mint, bonding_curve, associated_bonding_curve, associated_user, user, system_program, token_program, creator_vault, event_authority, program, global_volume_accumulator, user_volume_accumulator, fee_config, fee_program | spendable_sol_in:u64, min_tokens_out:u64, track_volume:OptionBool
buy_v2 (b817ee6167c5d33d): global, base_mint, quote_mint, base_token_program, quote_token_program, associated_token_program, fee_recipient, associated_quote_fee_recipient, buyback_fee_recipient, associated_quote_buyback_fee_recipient, bonding_curve, associated_base_bonding_curve, associated_quote_bonding_curve, user, associated_base_user, associated_quote_user, creator_vault, associated_creator_vault, sharing_config, global_volume_accumulator, user_volume_accumulator, associated_user_volume_accumulator, fee_config, fee_program, system_program, event_authority, program | amount:u64, max_sol_cost:u64
claim_cashback (253a237ebe35e4c5): user, user_volume_accumulator, system_program, event_authority, program | (none)
claim_cashback_v2 (7af3cc415e741d37): user, user_volume_accumulator, quote_mint, quote_token_program, associated_token_program, associated_user_volume_accumulator, associated_quote_user, system_program, event_authority, program | (none)
claim_token_incentives (1004471ccc01281b): user, user_ata, global_volume_accumulator, global_incentive_token_account, user_volume_accumulator, mint, token_program, system_program, associated_token_program, event_authority, program, payer | (none)
close_user_volume_accumulator (f945a4da9667548a): user, user_volume_accumulator, event_authority, program | (none)
collect_creator_fee (1416567bc61cdb84): creator, creator_vault, system_program, event_authority, program | (none)
collect_creator_fee_v2 (cf118af204221338): creator, creator_token_account, creator_vault, creator_vault_token_account, quote_mint, quote_token_program, associated_token_program, system_program, event_authority, program | (none)
create (181ec828051c0777): mint, mint_authority, bonding_curve, associated_bonding_curve, global, mpl_token_metadata, metadata, user, system_program, token_program, associated_token_program, rent, event_authority, program | name:string, symbol:string, uri:string, creator:pubkey
create_v2 (d6904cec5f8b31b4): mint, mint_authority, bonding_curve, associated_bonding_curve, global, user, system_program, token_program, associated_token_program, mayhem_program_id, global_params, sol_vault, mayhem_state, mayhem_token_vault, event_authority, program | name:string, symbol:string, uri:string, creator:pubkey, is_mayhem_mode:bool, is_cashback_enabled:OptionBool
distribute_creator_fees (a572670079cef751): mint, bonding_curve, sharing_config, creator_vault, system_program, event_authority, program | (none)
distribute_creator_fees_v2 (ffcb134ff444089f): payer, mint, bonding_curve, sharing_config, creator_vault, system_program, event_authority, program, creator_vault_quote_token_account, quote_mint, quote_token_program, associated_token_program | initialize_ata:bool
extend_account (ea66c2cb96483ee5): account, user, system_program, event_authority, program | (none)
get_minimum_distributable_fee (75e17fca865f4423): mint, bonding_curve, sharing_config, creator_vault | (none)
init_user_volume_accumulator (5e06ca73ff60e8b7): payer, user, user_volume_accumulator, system_program, event_authority, program | (none)
initialize (afaf6d1f0d989bed): global, user, system_program | (none)
migrate (9beae792ec9ea21e): global, withdraw_authority, mint, bonding_curve, associated_bonding_curve, user, system_program, token_program, pump_amm, pool, pool_authority, pool_authority_mint_account, pool_authority_wsol_account, amm_global_config, wsol_mint, lp_mint, user_pool_token_account, pool_base_token_account, pool_quote_token_account, token_2022_program, associated_token_program, pump_amm_event_authority, event_authority, program, rent | (none)
migrate_bonding_curve_creator (577c34bf3426d6e8): mint, bonding_curve, sharing_config, event_authority, program | (none)
migrate_v2 (bbcb121fceedfe29): global, withdraw_authority, base_mint, quote_mint, bonding_curve, associated_base_bonding_curve, associated_quote_bonding_curve, user, system_program, pump_amm, pool, pool_authority, pool_authority_mint_account, pool_authority_quote_account, amm_global_config, lp_mint, user_pool_token_account, pool_base_token_account, pool_quote_token_account, base_token_program, quote_token_program, token_2022_program, associated_token_program, pump_amm_event_authority, rent, event_authority, program | (none)
remove_quote_mint (b141df2658d19e9b): global, authority, event_authority, program | quote_mint:pubkey
sell (33e685a4017f83ad): global, fee_recipient, mint, bonding_curve, associated_bonding_curve, associated_user, user, system_program, creator_vault, token_program, event_authority, program, fee_config, fee_program | amount:u64, min_sol_output:u64
sell_v2 (5df6823ce7e940b2): global, base_mint, quote_mint, base_token_program, quote_token_program, associated_token_program, fee_recipient, associated_quote_fee_recipient, buyback_fee_recipient, associated_quote_buyback_fee_recipient, bonding_curve, associated_base_bonding_curve, associated_quote_bonding_curve, user, associated_base_user, associated_quote_user, creator_vault, associated_creator_vault, sharing_config, user_volume_accumulator, associated_user_volume_accumulator, fee_config, fee_program, system_program, event_authority, program | amount:u64, min_sol_output:u64
set_creator (fe94ff70cf8eaaa5): set_creator_authority, global, mint, metadata, bonding_curve, event_authority, program | creator:pubkey
set_mayhem_virtual_params (3da9bcbf99952a61): sol_vault_authority, mayhem_token_vault, mint, global, bonding_curve, token_program, event_authority, program | (none)
set_metaplex_creator (8a60aed93055c5f6): mint, metadata, bonding_curve, event_authority, program | (none)
set_params (1beab2349302bb8d): global, authority, event_authority, program | initial_virtual_token_reserves:u64, initial_virtual_sol_reserves:u64, initial_real_token_reserves:u64, token_total_supply:u64, fee_basis_points:u64, withdraw_authority:pubkey, enable_migrate:bool, pool_migration_fee:u64, creator_fee_basis_points:u64, set_creator_authority:pubkey, admin_set_creator_authority:pubkey
set_reserved_fee_recipients (6faca2e87259d58e): global, authority, event_authority, program | whitelist_pda:pubkey
set_virtual_quote_reserves (6587bf6809581460): global, authority, event_authority, program | initial_virtual_quote_reserves:u64
sync_user_volume_accumulator (561fc057a3574fee): user, global_volume_accumulator, user_volume_accumulator, event_authority, program | (none)
toggle_cashback_enabled (7367e0ffbd5956c3): global, authority, event_authority, program | enabled:bool
toggle_create_v2 (1cffe6f0ac6bcbab): global, authority, event_authority, program | enabled:bool
toggle_mayhem_mode (01096fd0641fffa3): global, authority, event_authority, program | enabled:bool
update_buyback_config (fbe0ab92a01a71e9): global, authority, event_authority, program | buyback_basis_points:Option<u64>
update_global_authority (e3b54ac4d01561d5): global, authority, new_authority, event_authority, program | (none)
```

## 5. Tabela completa — 31 instruções do PumpSwap (`idl/pump_amm.json`)

```
admin_set_coin_creator (f228759149606968): admin_set_coin_creator_authority, global_config, pool, event_authority, program | coin_creator:pubkey
admin_update_token_incentives (d10b7357d5177ccc): admin, global_config, global_volume_accumulator, mint, global_incentive_token_account, associated_token_program, system_program, token_program, event_authority, program | start_time:i64, end_time:i64, seconds_in_a_day:i64, day_number:u64, token_supply_per_day:u64
boost_buy_and_burn (694406af000723a2): pool, authority, global_config, base_mint, quote_mint, pool_base_token_account, pool_quote_token_account, boost_vault_authority, boost_vault, base_token_program, quote_token_program, event_authority, program | quote_amount_in:u64, min_base_amount_burned:u64
buy (66063d1201daebea): pool, user, global_config, base_mint, quote_mint, user_base_token_account, user_quote_token_account, pool_base_token_account, pool_quote_token_account, protocol_fee_recipient, protocol_fee_recipient_token_account, base_token_program, quote_token_program, system_program, associated_token_program, event_authority, program, coin_creator_vault_ata, coin_creator_vault_authority, global_volume_accumulator, user_volume_accumulator, fee_config, fee_program | base_amount_out:u64, max_quote_amount_in:u64, track_volume:OptionBool
buy_exact_quote_in (c62e1552b4d9e870): [mesmas contas de buy] | spendable_quote_in:u64, min_base_amount_out:u64, track_volume:OptionBool
claim_cashback (253a237ebe35e4c5): user, user_volume_accumulator, quote_mint, quote_token_program, user_volume_accumulator_wsol_token_account, user_wsol_token_account, system_program, event_authority, program | (none)
claim_token_incentives (1004471ccc01281b): user, user_ata, global_volume_accumulator, global_incentive_token_account, user_volume_accumulator, mint, token_program, system_program, associated_token_program, event_authority, program, payer | (none)
close_user_volume_accumulator (f945a4da9667548a): user, user_volume_accumulator, event_authority, program | (none)
collect_coin_creator_fee (a039592ab58b2b42): quote_mint, quote_token_program, coin_creator, coin_creator_vault_authority, coin_creator_vault_ata, coin_creator_token_account, event_authority, program | (none)
create_config (c9cff3724b6f2fbd): admin, global_config, system_program, event_authority, program | lp_fee_basis_points:u64, protocol_fee_basis_points:u64, protocol_fee_recipients:[pubkey;8], coin_creator_fee_basis_points:u64, admin_set_coin_creator_authority:pubkey
create_pool (e992d18ecf6840bc): pool, global_config, creator, base_mint, quote_mint, lp_mint, user_base_token_account, user_quote_token_account, user_pool_token_account, pool_base_token_account, pool_quote_token_account, system_program, token_2022_program, base_token_program, quote_token_program, associated_token_program, event_authority, program | index:u16, base_amount_in:u64, quote_amount_in:u64, coin_creator:pubkey, is_mayhem_mode:bool, is_cashback_coin:OptionBool
deposit (f223c68952e1f2b6): pool, global_config, user, base_mint, quote_mint, lp_mint, user_base_token_account, user_quote_token_account, user_pool_token_account, pool_base_token_account, pool_quote_token_account, token_program, token_2022_program, event_authority, program | lp_token_amount_out:u64, max_base_amount_in:u64, max_quote_amount_in:u64
disable (b9adbb5ad80feee9): admin, global_config, event_authority, program | disable_create_pool:bool, disable_deposit:bool, disable_withdraw:bool, disable_buy:bool, disable_sell:bool
extend_account (ea66c2cb96483ee5): account, user, system_program, event_authority, program | (none)
init_boost (8ce9215e845ac28f): pool, global_config, creator, base_mint, quote_mint, pool_base_token_account, pool_quote_token_account, boost_vault_authority, boost_vault, quote_token_program, system_program, associated_token_program, event_authority, program | (none)
init_user_volume_accumulator (5e06ca73ff60e8b7): payer, user, user_volume_accumulator, system_program, event_authority, program | (none)
migrate_pool_coin_creator (d0089f044aaf103a): pool, sharing_config, event_authority, program | (none)
sell (33e685a4017f83ad): pool, user, global_config, base_mint, quote_mint, user_base_token_account, user_quote_token_account, pool_base_token_account, pool_quote_token_account, protocol_fee_recipient, protocol_fee_recipient_token_account, base_token_program, quote_token_program, system_program, associated_token_program, event_authority, program, coin_creator_vault_ata, coin_creator_vault_authority, fee_config, fee_program | base_amount_in:u64, min_quote_amount_out:u64
set_boost_authority (e3954c2a8227eacd): admin, global_config, boost_authority, system_program, event_authority, program | (none)
set_coin_creator (d295802dbc3a4eaf): pool, metadata, bonding_curve, event_authority, program | (none)
set_reserved_fee_recipients (6faca2e87259d58e): global_config, admin, event_authority, program | whitelist_pda:pubkey
sync_user_volume_accumulator (561fc057a3574fee): user, global_volume_accumulator, user_volume_accumulator, event_authority, program | (none)
toggle_boost (75a1a04adf897663): admin, global_config | enabled:bool
toggle_cashback_enabled (7367e0ffbd5956c3): admin, global_config, event_authority, program | enabled:bool
toggle_mayhem_mode (01096fd0641fffa3): admin, global_config, event_authority, program | enabled:bool
transfer_creator_fees_to_pump (8b348655e4e56cf1): wsol_mint, token_program, system_program, associated_token_program, coin_creator, coin_creator_vault_authority, coin_creator_vault_ata, pump_creator_vault, event_authority, program | (none)
transfer_creator_fees_to_pump_v2 (01214eb921432c5c): payer, quote_mint, token_program, system_program, associated_token_program, coin_creator, coin_creator_vault_authority, coin_creator_vault_ata, pump_creator_vault, pump_creator_vault_ata, event_authority, program | (none)
update_admin (a1b028d53cb8b3e4): admin, global_config, new_admin, event_authority, program | (none)
update_buyback_config (fbe0ab92a01a71e9): admin, global_config, event_authority, program | buyback_basis_points:Option<u64>
update_fee_config (68b867f258976b14): admin, global_config, event_authority, program | lp_fee_basis_points:u64, protocol_fee_basis_points:u64, protocol_fee_recipients:[pubkey;8], coin_creator_fee_basis_points:u64, admin_set_coin_creator_authority:pubkey
withdraw (b712469c946da122): pool, global_config, user, base_mint, quote_mint, lp_mint, user_base_token_account, user_quote_token_account, user_pool_token_account, pool_base_token_account, pool_quote_token_account, token_program, token_2022_program, event_authority, program | lp_token_amount_in:u64, min_base_amount_out:u64, min_quote_amount_out:u64
```

## 6. Campos completos de eventos secundários (não centrais para reconstrução de trade)

```
SetParamsEvent: initial_virtual_token_reserves, initial_virtual_sol_reserves, initial_real_token_reserves,
  final_real_sol_reserves, token_total_supply, fee_basis_points, withdraw_authority, enable_migrate,
  pool_migration_fee, creator_fee_basis_points, fee_recipients:[pubkey;8], timestamp:i64,
  set_creator_authority, admin_set_creator_authority

ExtendAccountEvent: account, user, current_size:u64, new_size:u64, timestamp:i64

UpdateMayhemVirtualParamsEvent: timestamp:i64, mint, virtual_token_reserves, virtual_sol_reserves,
  new_virtual_token_reserves, new_virtual_sol_reserves, real_token_reserves, real_sol_reserves

MigrateBondingCurveCreatorEvent: timestamp:i64, mint, bonding_curve, sharing_config, old_creator, new_creator

Shareholder (tipo usado dentro de TradeEvent.shareholders): address:pubkey, share_bps:u16
OptionBool (wrapper Anchor para Option<bool> explícito): tupla de 1 campo bool
```

## 7. Programa Pump Fees (`pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ`) — achado não previsto no brief

Descoberto ao ler `idl/pump_fees.json` (mesmo commit) porque `buy_v2`/`sell_v2`/`buy`/`sell`
referenciam a conta `fee_config`/`fee_program`. Contas que expõe: `BondingCurve`, `BuybackVault`,
`DonationFeePda`, `FeeConfig`, `FeeProgramGlobal`, `Global`, `Pool`, `SharingConfig`,
`SocialFeePda` (vários tipos compartilhados/vendorizados dos outros dois programas, para leitura
via CPI). `FeeConfig` tem `bump, admin, flat_fees:Fees, fee_tiers:Vec<FeeTier>,
stable_fee_tiers:Vec<FeeTier>` — dois conjuntos de tiers (`fee_tiers` normal e `stable_fee_tiers`,
provavelmente para pools com quote mint "estável"/USDC, não confirmado). `Fees` = `{lp_fee_bps,
protocol_fee_bps, creator_fee_bps}` (todos u64). `FeeTier` = `{market_cap_lamports_threshold:u128,
fees:Fees}`. Não li a conta `FeeConfig` ao vivo (§3 do documento principal explica por quê — PDA
com seeds `["fee_config", pump_program_id]` sob este programa, precisa de checagem ed25519 que não
implementei). `SharingConfig` cobre fee-splitting entre múltiplos criadores (`distribute_creator_fees_v2`
do lado Pump, `migrate_pool_coin_creator`/`migrate_bonding_curve_creator` fazem a transição de
criador único → `SharingConfig`). `SocialFeePda`/`DonationFeePda`/`BuybackVault` são features de
cashback social/doação/buyback — fora do escopo de trading desta tarefa, citadas só para registro.

## 8. Decodificadores — comandos usados na comparação (§4 do documento principal)

```
curl -sS "https://api.github.com/search/repositories?q=pump-fun-idl&sort=stars&order=desc&per_page=6"
curl -sS "https://api.github.com/search/repositories?q=solana-pumpfun&sort=stars&order=desc&per_page=6"
curl -sS "https://api.github.com/search/repositories?q=pumpfun+decoder+language:Rust&sort=stars&order=desc&per_page=6"
curl -sS "https://api.github.com/search/repositories?q=pumpfun+parser+language:TypeScript&sort=stars&order=desc&per_page=6"
curl -sS "https://api.github.com/repos/0xfnzero/sol-trade-sdk"
curl -sS "https://raw.githubusercontent.com/0xfnzero/sol-trade-sdk/main/README.md"
curl -sS "https://api.github.com/repos/cxcx-ai/solana-dex-parser"
curl -sS "https://raw.githubusercontent.com/cxcx-ai/solana-dex-parser/main/README.md"
curl -sS "https://api.github.com/search/code?q=MAyhSmzXzV1pTf7LsNkrNwkWKTo4ougAJ1PPg47MD4e"   # -> "Requires authentication", não usei token
```
Todos executados 2026-09-12 ~02:22–02:33 BRT. `0xfnzero/sol-trade-sdk`: 339 estrelas, push
2026-09-08T11:22:38Z, Rust, descrição própria "PumpFun, PumpSwap, Bonk, Raydium, Meteora, Jito" —
seções do README incluem "PumpFun V1 vs V2 Instructions" e "Cashback Support (PumpFun/PumpSwap)".
`cxcx-ai/solana-dex-parser`: 114 estrelas, push 2025-10-02T15:37:35Z, TypeScript, `PumpfunEventParser`
com `PumpfunEvent = {data: PumpfunTradeEvent | PumpfunCreateEvent | PumpfunCompleteEvent}` — cobre
o trio básico, sem menção a `buy_v2`/`sell_v2`/cashback no texto lido.

## 9. Rate limits e pricing — comandos e trechos exatos

```
curl -sS -L "https://solana.com/docs/references/clusters" -A "Mozilla/5.0"
```
Lido 2026-09-12T05:29:38Z (02:29:38 BRT). Trecho relevante (seção "Mainnet"):
```
Maximum number of requests per 10 seconds per IP: 100
Maximum number of requests per 10 seconds per IP for a single RPC: 40
Maximum concurrent connections per IP: 40
Maximum connection rate per 10 seconds per IP: 40
Maximum amount of data per 30 second: 100 MB
```
Nenhuma ocorrência de `websocket`, `wss://` ou `logsSubscribe` na página inteira (busca de texto
sobre o HTML completo, 906507 bytes) — a doc oficial não cobre WS para o endpoint público.

```
curl -sS -L "https://www.helius.dev/pricing" -A "Mozilla/5.0"
```
Lido 2026-09-12T05:30:24Z (02:30:24 BRT). JSON-LD embutido na página, tiers:
- Free: US$0/mês — "1M credits. 10 Requests / sec. 1 sendTransaction / sec. LaserStream WSS (standard). Shreds - $1,000/month/IP."
- Developer: US$49/mês — "10M credits. 50 Requests / sec. 5 sendTransaction / sec. Staked Connections. LaserStream WSS. LaserStream gRPC (devnet)."
- Business: US$499/mês — "100M credits. 200 Requests / sec. 50 sendTransaction / sec. 5 sendBundle / sec. Staked Connections. LaserStream WSS. LaserStream gRPC."
- Professional: US$999/mês — "200M credits. 500 Requests / sec. 100 sendTransaction / sec. 5 sendBundle / sec."

Tentativa de confirmar o path exato do endpoint de "Enhanced Transactions History" (para citar
como alternativa a `getTransactionsForAddress` mencionado no brief):
```
curl -sS -L "https://www.helius.dev/docs/api-reference/enhanced-transactions/parse-transaction-s-for-an-address" -A "Mozilla/5.0"
```
Página retornou HTML (103513 bytes) sem o texto do path da API renderizado no HTML cru (site
provavelmente hidrata via JS) — não incluí um path específico no documento principal por essa
razão; citei apenas "existe, é a Enhanced Transactions API + webhooks", sem inventar a URL exata.

## 10. O que ficou de fora / pendências desta rodada

- IDL do programa Mayhem: não encontrado, não derivado (ver §3 acima e §3.2 do documento principal).
- `FeeConfig.fee_tiers`/`stable_fee_tiers` ao vivo: não lidos (PDA não derivado); usei a imagem
  `docs/fees.png` do mesmo commit como fonte primária da tabela de tiers em vez disso.
- Teste ao vivo de `logsSubscribe`/`programSubscribe` no WS público: não feito (sem cliente WS
  confirmado no ambiente desta sessão).
- Modo "Manual" vs "Automático" do Mayhem no screener do Everton: não encontrado on-chain nem na
  doc lida — registrado como pendência (T4.1b) no documento principal, §3.4, não inventado.
- Preço por unidade de compute (`set_compute_unit_price`) necessário para inclusão rápida: não é
  parte do protocolo pump.fun, depende do estado do mercado de blockspace no momento — não
  documentado aqui de propósito.

Nenhum arquivo em `packages/exchange-adapters/hunter_exchanges/pumpfun/**`, `.env*` ou qualquer
outro arquivo do repo foi editado nesta tarefa além dos dois deliverables
(`docs/PUMPFUN-ONCHAIN.md`, este arquivo, e o brief salvo em
`.claude/state/brief-T4.0d-mapa-onchain-pumpfun.md`). Nenhum commit foi feito.
