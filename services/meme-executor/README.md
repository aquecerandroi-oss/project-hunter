# meme-executor — `HUNTER_ROLE=meme_executor`, perfil compose `meme-live`

O único processo do sistema que lê `SOLANA_WALLET_SECRET_KEY` (uma vez, e a remove do ambiente).
Liga uma proposta `meme_proposals.mode = 'live'` aprovada na mesa a uma transação assinada na
bonding curve do pump.fun: admissão (`hunter_risk_meme`, 25 checks + sizing) → cotação local →
`tx.build_buy` → verificador §9.1 → `simulateTransaction` → assinar → enviar → confirmar pelo
`TradeEvent` → `meme_live_orders`/`meme_live_positions`. Saídas: alvo, trailing, `max_hold_s`,
`sell_now` (via `GET/POST /meme/live`), `emergency_auto_close` (só com
`MEME_AUTO_CLOSE_ON_EMERGENCY=true`). Doutrina: `docs/RISK_ENGINE_MEME.md`; operação:
`docs/DEPLOYMENT.md` §3.7 ("como ligar", "como desligar em 5 s"); notas: `.claude/state/notes-T4.14.md`.

Inerte por construção: com `ENABLE_MEME_LIVE_TRADING=false` o processo sobe, serve
`/health`/`/ready`/`/metrics`, escreve `hb:meme:executor` e **não assina nada** (o submitter
levanta `MemeLiveTradingDisabled` antes da chave). Com a flag ligada e qualquer coisa faltando
(portões, política, chave) o boot é **recusado por nome** (`MemeLiveTradingRefused`).

Identidade do programa (T4.8b, `program_check.py`): no boot o executor lê a IDL on-chain e o slot do
último deploy do programa da pump.fun e compara com o que as fixtures do construtor foram provadas
contra (`hunter_exchanges.pumpfun.program_identity.EXPECTED_PUMP_PROGRAM`). Divergência ⇒ live recusa
subir (`program_upgraded`; leitura impossível ⇒ `program_identity_unreadable`), inerte loga e expõe no
heartbeat (`program_idl_hash`, `program_last_deploy_slot`, `program_divergence`). A cada tique do kill
switch o slot é relido (45 bytes); se mudou, toda entrada é recusada `program_upgraded` até a T4.8b ser
refeita (`docs/PUMPFUN-ONCHAIN.md` §6c). Curvas com quote ≠ SOL são recusadas em `build.py`
(`unsupported_quote`).
