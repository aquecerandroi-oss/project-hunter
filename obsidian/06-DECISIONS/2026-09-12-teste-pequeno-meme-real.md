---
tags: [decisao, meme, pumpfun, execucao, dinheiro-real, teste-pequeno, m4]
titulo: Dinheiro real no executor de memecoins — autorização, escopo do teste pequeno, tetos e o que continua fora
data: 2026-09-12
updated: 2026-09-16
owner: sexta-feira
origem: Everton, 2026-09-12, 17:2x–17:4x BRT — "Autorização escrita — está autorizado"; "tem que fazer vários e vários testes e ir validando; lembrando que cria e morre rápido, e as mais promissoras é para fazer milhão"; "carteira própria do robô já está criada; máximo por SOL até 1000 dólares"
status: decidido
decided_on: 2026-09-12
by: everton
---

# Dinheiro real no executor de memecoins — autorização e escopo

## A decisão
O Everton autoriza por escrito (chat, 12/09/2026 17:2x BRT) ligar o executor real de memecoins
(`docs/ACTIVATION.md` §9b, item 2), sabendo que os Portões A (VM1–VM9 na VPS + 7 dias de papel) e B (EXP-M1: ≥ 100
operações e ≥ 30 dias) estão **vermelhos**: em papel, 12/09 fechou 17 apostas medidas a −3,37 R com 1 acerto. A carteira
dedicada do robô já existe (criada por ele às 17:4x BRT). O teto que ele fixou: **até US$ 1 000 por operação**
(≈ 9,8 SOL a US$ 102/SOL, cotação do heartbeat às 17:00 BRT).

## Em dois estágios — a proposta da Sexta-feira, para ele confirmar
O executor nunca assinou uma transação real; a prova é simulação na mainnet. Por isso a ordem proposta:

| Estágio | Escopo (`small_test_authorization` no `meme_gates.json`) | Objetivo |
|---|---|---|
| **1 — encanamento** | `max_sol_per_trade` **0,05 SOL** (≈ US$ 5), `max_total_sol` **0,25**, `max_trades` **5**, validade 2026-09-15 | provar fill real, `TradeEvent`, posição, venda real na curva, `sell_now`, kill switch — cinco compras e cinco vendas de verdade |
| **2 — o teto dele** | `max_sol_per_trade` **9,8 SOL** (US$ 1 000), `max_total_sol` e `max_trades` a fixar por ele, validade curta | as promissoras, uma a uma, cada compra aprovada por ele na mesa |

O estágio 2 só começa depois de o estágio 1 fechar cinco vendas reais sem recusa inesperada e com o PnL batendo ao
lamport com a cadeia (`meme_live_positions` × saldo da carteira). Ele assina o segundo `meme_gates.json` quando quiser.

Os cinco números de política do `.env` (só ele digita) para o **estágio 1** — sugeridos, ele pode apertar:
`MEME_WALLET_MAX_SOL=0.30` · `MEME_MAX_SOL_PER_TRADE=0.05` · `MEME_DAILY_LOSS_CAP_SOL=0.15` · `MEME_MAX_OPEN_POSITIONS=2`
· `MEME_COOLDOWN_S=60`. Saldo da carteira ≤ `MEME_WALLET_MAX_SOL` (acima disso o executor recusa entradas,
`wallet_over_max_sol`). No estágio 2 os cinco sobem junto com o escopo (o escopo é sempre o mínimo com a política).

## O que é dele e só dele (nenhum agente toca; o classificador de segurança bloqueia até a criação do arquivo de portões)
1. A carteira dedicada (feita) com saldo ≤ `MEME_WALLET_MAX_SOL`.
2. No `.env` da VPS: a flag ligada, `SOLANA_WALLET_SECRET_KEY` (base58 do Phantom **ou** o array JSON do
   `solana-keygen` — os dois formatos são aceitos, `hunter_core/execution/meme/signer.py`), `SOLANA_RPC_URL` (RPC próprio
   com chave — Helius/QuickNode/Triton; o endpoint público é recusado, `rpc_url_missing`), os cinco `MEME_*`,
   `MEME_GATES_FILE=/run/hunter/meme_gates.json`.
3. O arquivo `/opt/project-hunter/run/meme/meme_gates.json` (conteúdo pronto no chat de 17:4x BRT; formato em
   `packages/core/hunter_core/execution/meme/gates.py`).
4. Depois disso a Sexta-feira sobe com `MEME_LIVE=1 MEME=1 MEME_ENABLED=true bash infra/vps/compose.sh update`, confere
   `hb:meme:executor` e `GET /meme/live`, e **cada compra real é aprovada por ele** na mesa ("Aprovar (REAL)", T4.17, dupla
   confirmação) ou por HTTP com `Idempotency-Key`. Nada compra sozinho em dinheiro real.
5. Desligar em 5 s: `touch /opt/project-hunter/run/meme/meme.kill`.

## O que continua fora (ele sabe antes de ligar)
- **Venda na PumpSwap: implementada em 16/09/2026 (T4.29a), ainda não simulada na mainnet real.**
  `pumpswap_sell_not_implemented` deixou de existir: uma posição que migrar agora vende de verdade no
  pool canônico da PumpSwap (decode/quote/instrução verificados offline contra 3 pools reais e o
  `GlobalConfig` lido ao vivo — `.claude/state/notes-T4.29a.md`), pelo mesmo caminho de
  verificação/simulação/journal/kill-switch da curva. Falta a prova que só a VPS com carteira e RPC
  próprio pode dar: nenhuma venda foi simulada (`simulateTransaction`) nem enviada na mainnet real
  ainda — `pumpswap_pool_not_found` é a única recusa nomeada que resta (pool ainda não indexado).
- `holder_rewards` sempre 0 hoje e o piso de taxa é constante datada (decodificar `FeeConfig` depois — T4.8b).
- O rastreador ainda pode expulsar uma moeda com aposta aberta (T4.16b em curso); o executor lê a curva por RPC na hora
  de vender e não depende do rastreador para sair.

## Estágio 1 — sozinho (16/09)
**Decisão do Everton (16/09/2026 01:2x BRT: "liga sozinho no estágio 1"; antes: "precisa estar pronto hoje",
"o robô fazer os trades da memecoin"):** no estágio 1 o robô compra e vende **sem o clique** em "Aprovar (REAL)".
Isto revoga, só para o estágio 1, a frase "cada compra real é aprovada por ele na mesa" do item 4 acima.

- **Escopo inalterado:** `max_sol_per_trade` 0,05 SOL, `max_total_sol` 0,25, `max_trades` 5; validade estendida para
  **2026-09-18** (ele edita o `meme_gates.json`: `small_test_authorization.expires_at` e `valid_until`). Tetos do
  `.env`: `MEME_WALLET_MAX_SOL=0.30`, `MEME_MAX_SOL_PER_TRADE=0.05`, `MEME_DAILY_LOSS_CAP_SOL=0.15`,
  `MEME_MAX_OPEN_POSITIONS=2`, `MEME_COOLDOWN_S=60`. **Risco máximo do estágio: 0,30 SOL** (o saldo da carteira).
- **Como:** `MEME_LIVE_AUTO_APPROVE` ligada no `.env` da VPS (T4.28). O executor abre a proposta `proposed` do conjunto
  `operator` ativo como proposta real com a mesma regra e a mesma escrita do clique (`decided_by =
  executor:auto_stage1`, `decision = suggested`) e a admissão segue inalterada: 25 checks, sizing, escopo (agora
  fechando também por `max_total_sol`, somando o SOL real gasto), kill switch relido antes de assinar. Freios só
  deste modo: 1 compra por tique e por mint; proposta com mais de 60 s fica para a mão dele; no máximo 5 aprovações
  automáticas por hora; toda recusa da admissão marca a proposta `rejected` com o motivo. A flag só é lida com a flag
  live ligada e o escopo escrito nos portões; sem escopo o boot recusa (`auto_approve_needs_small_test`).
- **Desligar:** `MEME_LIVE_AUTO_APPROVE=false` + `update`, ou `touch /opt/project-hunter/run/meme/meme.kill`.
- **Estágio 2 (US$ 1 000/operação) continua exigindo o clique** até nova decisão escrita dele.

Registro: `docs/RISK_ENGINE_MEME.md` §3.5, `docs/ACTIVATION.md` §9b item 9, `.claude/state/notes-T4.28.md`.

## O método que o Everton pediu e como ele se encaixa
"Vários e vários testes, validando; cria e morre rápido; as promissoras são para fazer milhão." O laboratório de papel
é isso: centenas de apostas pequenas por conjunto, régua de ≥ 100 apostas e 30 dias por regra
([[06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real|a régua]]), o fechamento diário escrevendo as lições
sozinho (T4.15), e os braços **moonshot** (alvo 10×/25×, trailing 50 % só após 3×, segurar pela migração —
[[05-EXPERIMENTS/EXP-M4-moonshot|EXP-M4]]) para a cauda. O dinheiro real grande entra **atrás** da regra que provar
vantagem; o estágio 1 garante que, no dia em que ela provar, o robô já esteja provado.

## Ligações
[[06-DECISIONS/2026-09-12-mesa-do-operador-e-caminho-inerte]] · [[03-TRADING/Meme/Estudo-2026-09-12-21-apostas]] ·
[[05-EXPERIMENTS/EXP-M4-moonshot]] · [[11-KNOWLEDGE/KB-0094-pump-fun-upgrade-de-12-09-2026-holder-rewards-e-bonding-curve-v2|KB-0094]]

## Ligado — 16/09/2026 11:2x BRT (estágio 1, sozinho)
- **Carteira do robô:** `ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4`, gerada pelo Everton na própria VPS (chave só no `.env`; uma primeira
  carteira, `G1Jnek…`, foi descartada porque a chave apareceu parcialmente num print). Saldo depositado: **0,717 SOL** (do Terminal,
  `6nAh…`, que ficou com 0,0098 SOL). Ele mandou mais do que os 0,30 combinados; em vez de devolver, subiu o escopo.
- **Escopo em vigor (`meme_gates.json`, editado por ele):** `max_sol_per_trade` 0,05 · `max_total_sol` **0,72** · `max_trades` 5 ·
  validade 2026-09-18. `.env`: `MEME_WALLET_MAX_SOL=0.80` (teto efetivo = min(0,80; 0,72) = **0,72 SOL**). Na prática o gasto máximo
  continua 5 × 0,05 = 0,25 SOL; o que mudou é o teto "aceita perder inteiro", que passou de 0,25 para 0,72.
- **Subida:** `MEME_LIVE=1 MEME=1 MEME_ENABLED=true MEME_ACTIVITY_ENABLED=true STRATEGY_SHARDS=4 MARKET_SPOT=1 MARKET_SHARDS=4
  bash infra/vps/compose.sh update` rodado **pelo Everton** (o classificador bloqueou a Sexta-feira: primeiro deploy com perfil
  `meme-live`). Executor `hunter-api:9f828dd`, boot aceito (`meme_executor_program_identity_ok`, slot 447 228 373), `auto_approve
  true`, kill switch ACTIVE, 0 reinícios. Como o executor lê os portões só no boot, o escopo novo exigiu `docker restart
  hunter-meme-executor-1` (dele, 11:3x BRT) — T4.28d: recarregar os portões no tique do kill switch.
- **Fato de operação:** o executor só lê o saldo da carteira quando existe candidata; `wallet_sol_balance` fica vazio até a primeira
  proposta do conjunto `operator` ativo. Horário útil da mesa: 13–22 BRT (KB-0098).
- **Sacar da carteira do robô:** importar a chave (lida do `.env` na VPS, sem print) no Phantom → "Importar chave privada", com o
  executor desligado (`meme.kill`). Acompanhar: `solscan.io/account/ARsuJEagSE2pLgjMfDvgNo1TdMRS2DDRYLmgu4fX6Dr4` e a mesa (`/ever/meme/mesa`).

## Decisão A — 16/09/2026 15:0x BRT: a mesa alinhada ao teto de progresso do executor
**Everton: "confirma o A".** Fato que motivou: nas 24 h anteriores, 51 de 68 propostas da mesa (`operator/5`, progresso 5–100 %)
estavam acima dos 50 % que o executor real aceita (`curve_progress_max_pct`, §3.1); depois da volta da fita (14:00–14:14) foram 6 de 6.
O teto do executor **não muda** (a venda depois da migração não existe — T4.29a em construção): a mesa passa a propor só até 50 %.
Gravado por `meme_rule_set.py --set-param max_progress_pct=50 --rule-set operator/5 --apply`, auditado em `system_events`.
Opção B (subir o teto para 85 %) fica registrada como o passo natural **depois** que a venda na PumpSwap existir e for simulada.

**Estágio 2 em paralelo (mesma mensagem: "já vai fazendo o estágio 2 agora mesmo em paralelo"):** T4.29a venda na PumpSwap,
T4.29b estudo do tamanho (o que US$ 1 000 por operação permite sob os nossos tetos de participação e impacto), T4.29c `FeeConfig`
+ simulação de venda em curva com holder rewards, T4.28c painel do modo sozinho. Nada disso liga dinheiro novo: o escopo do estágio 2
continua exigindo o segundo `meme_gates.json` assinado por ele e o clique por compra.

## Estágio 2 redefinido — 16/09/2026 16:0x BRT ("aceito")
**Fato medido (T4.29b, [[03-TRADING/Meme/Estudo-2026-09-16-tamanho-estagio-2|estudo]]):** o impacto de uma compra na curva é
`SOL ÷ reserva virtual` (30–115 SOL); com o teto de impacto de 0,5 % cabem 0,15–0,58 SOL por compra; **1, 2, 5 e 9,8 SOL admitem
zero minutos-moeda em 24 h**; na pool, 9,8 SOL cabem em 0 % dos instantes medidos. US$ 1 000 por operação não existe sob os nossos tetos.
**Decisão do Everton:** o estágio 2 passa a ser **0,25 SOL por operação** (impacto ≤ 0,5 %, participação ≤ 1 % mantidos) e o
**US$ 1 000 vira teto de exposição do dia** (≈ 10 SOL à cotação de 16/09), não tamanho de ticket. Cada compra continua aprovada
pelo clique dele. Pré-requisitos inalterados: estágio 1 fecha 5 vendas reais; venda na PumpSwap (T4.29a) implementada e simulada.
Números sugeridos para o segundo `meme_gates.json`/`.env` (ele fixa): `max_sol_per_trade 0,25` · `MEME_WALLET_MAX_SOL 10` ·
`MEME_MAX_OPEN_POSITIONS 5` · `MEME_DAILY_LOSS_CAP_SOL` a escolher · `MEME_LIVE_AUTO_APPROVE=false`. Tickets maiores só com compra
na pool com liquidez medida — frente nova, não autorizada.

## Adendo 17/09/2026 11:5x BRT — "deixa comprar moedas à vontade" (Everton, por escrito no chat)

Depois do estágio 1 concluído (5/5 compras, −0,0449 SOL realizado; [[03-TRADING/Meme/Balanco-2026-09-17-estagio-1]]), o Everton decidiu retirar o limite de **número** de compras do teste pequeno. O que muda: só `scope.max_trades` (5 → 1000) no `meme_gates.json` da VPS, editado por ele (o arquivo é a assinatura dele; a Sexta-feira não o edita). O que **não** muda: 0,05 SOL por operação, 0,72 SOL de teto total, cap de perda diária 0,15 SOL, no máximo 2 posições abertas, `expires_at`/`valid_until` 2026-09-18 (vence amanhã; renovar é outra decisão dele), estágio 1 = modo sozinho. O robô relê o arquivo em até 10 s.

## Adendo 17/09/2026 13:5x BRT — "usa a outra moeda, não tem problema" / "quero deixar atualizado para usar outra moeda" (Everton, por escrito)

A carteira do robô tem 21,33 USDC além do SOL. O Everton pede que o sistema use USDC como capital. Decisão de construção (Sexta-feira): **tesouraria do executor (T4.54)** — quando o SOL cai abaixo de um piso, o executor converte USDC → SOL pela Jupiter, com tetos (por troca, por dia, slippage, intervalo), verificação e simulação antes de assinar, linha auditada em `meme_treasury_swaps`. **Nasce desligada** (`MEME_TREASURY_ENABLED=false`); ligar é dele, no `.env`, depois da revisão de risco. Enquanto não liga, vale a conversão manual (Phantom/Jupiter) + `max_total_sol` no `meme_gates.json`.

## Adendo 18/09/2026 09:1x BRT — "deixa o robô ilimitado" (Everton, por escrito no chat)

Depois do estágio 1b (7 compras na noite 17→18, PS +0,66 R, +0,0078 SOL líquido), o Everton pede o robô sem limite de escopo. Leitura da Sexta-feira, registrada para ele confirmar pelo próprio ato de editar o arquivo: **"ilimitado" = sem teto de número de compras (já 1000), sem teto total do teste pequeno (`max_total_sol` → 10 SOL, na prática a carteira) e sem vencimento próximo (`expires_at`/`valid_until` → 2026-12-31)**. O que **continua**, porque é o freio e não o escopo: 0,05 SOL por operação (estágio 1), cap de perda diária 0,15 SOL, no máximo 2 posições abertas, kill switch, simulação antes de assinar, `wallet_max_sol` 0,80 no `.env`. Mudar o tamanho por operação (estágio 2: 0,25 SOL) ou o cap diário é outra decisão dele, por escrito. O arquivo `meme_gates.json` é a assinatura dele; a Sexta-feira não o edita.

## Adendo 18/09/2026 09:3x BRT — "vamos subir até 150 reais" (Everton, por escrito)

Tamanho por operação sobe de 0,05 SOL para **R$ 150 ≈ US$ 29,2 ≈ 0,28 SOL** (SOL US$ 105,24 pelo batimento; USD/BRL 5,13 em 17/09). O tamanho efetivo é o **menor** entre `MEME_MAX_SOL_PER_TRADE` (`.env`, base) e `scope.max_sol_per_trade` (`meme_gates.json`, teste pequeno) — os dois precisam mudar, e a mudança do `.env` exige reiniciar o executor (o Everton faz). Consequências registradas para ele: com a carteira em 0,68 SOL e 2 posições abertas de 0,28, sobra pouco para a terceira; uma perda típica da mesa (−0,08 a −0,35 R) passa a custar 0,02–0,10 SOL, e o cap diário de 0,15 SOL para o robô depois de 2–4 perdas seguidas — o cap é freio, continua. `MEME_WALLET_MAX_SOL` 0,80 continua (carteira 0,68 cabe). É o estágio 2 com tamanho um pouco maior que o previsto (0,25), decidido por ele.

## Adendo 18/09/2026 10:1x BRT — "liga" / "pode ligar" a tesouraria USDC→SOL (Everton, por escrito)

Everton manda ligar a tesouraria (T4.54/T4.54b, revisão de risco: BLOCK → consertos A–E aplicados → prova ao vivo pendente). Registro da Sexta-feira: **liga em dois passos**, os dois no `.env` dele. (1) **Prova ao vivo com 1 USDC**: `MEME_TREASURY_ENABLED=true`, `MEME_TREASURY_MAX_USDC_PER_SWAP=1`, `MEME_TREASURY_MAX_USDC_PER_DAY=1`, `MEME_TREASURY_SOL_FLOOR=0.70`, `MEME_TREASURY_SOL_TARGET=0.72`, `MEME_WALLET_MAX_SOL=1.0` (o alvo é limitado a `wallet_max − 0,28`; com 0,80 o alvo cairia para 0,52, abaixo da carteira, e nada aconteceria) — uma troca de 1 USDC, conferida na Solscan e em `meme_treasury_swaps`. (2) Se a prova passar: `MAX_USDC_PER_SWAP=25`, `MAX_USDC_PER_DAY=50`, piso/alvo de operação. Ligar/mudar é dele; a Sexta-feira confere e reporta.
