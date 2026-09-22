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

## Adendo 18/09/2026 10:5x BRT — Proposta A aceita: "pode fazer, vamos estudando como dá e colhendo resultados vencedores" (Everton, por escrito)

A porta da mesa (`operator/5`) passa a ter a **entrada do braço em papel `flow_v2/5`** (+0,10 SOL/noite em 17→18/09, +0,10 em 16→17), mantendo os freios da mesa (2 posições, 0,28 SOL/op, cap diário 0,15, TTL 180 s, criador pela cadeia, bundle 20 %, top-10 25 %). Mudanças, aplicadas pelo script auditado (`meme_rule_set.py --set-param`, histórico em `meme_rule_set_param_history`):
`progress_or_mcap_rising` false → true; `require_progress_rising` false → true; `require_holders_rising` false → true; `holders_rising_or_flat` false → true; `max_progress_pct` 50 → 100; `min_snipers` 21 → (removido); `max_snipers` 1000 → 10.
Evidência: R54 (45 vencedoras do papel com 0–10 snipers, 26 acima de 50 %), R56 (7 de 7 compras reais depois da queda; conjuntos sem "subindo" negativos), R46 (7 casos com ≥ 21 snipers: 0 de 7). Não mudou: teto de bundle 20 % (a Keel de hoje, 25,8 %, continuaria recusada) — subir é decisão à parte dele. Método: [[analise-continua]] — medir todo dia, KB por resultado.

## Adendo 18/09/2026 12:5x BRT — "terminando já liga" (Everton, por escrito): radar por evento (T4.52b)

Everton manda ligar o portão de evento assim que os consertos F1–F7 (T4.52b-4) fecharem e a revisão liberar. Registro da Sexta-feira: sobe **desligado** no pacote 5; o Everton põe `MEME_EVENT_GATE=shadow` no `.env` e recria o radar; a Sexta-feira mede **1 h no pico** (propostas da pista de evento × pista de 15 s nos mesmos mints, `event_to_proposal_s`, CPU, quedas); com a medição em mãos ele troca para `MEME_EVENT_GATE=on`. A sombra curta substitui as 24 h do plano por decisão dele ("liga"); o que não se pula é a medição, porque `on` gera proposta real que o executor compra a 0,28 SOL.

## Adendo 18/09/2026 14:3x BRT — "se achou oportunidade eu quero que ela entre já" (Everton, por escrito): `MEME_EVENT_GATE=on`

Everton decide pular a hora de sombra: o portão de evento passa a propor de verdade (`on`). Estado no momento: sombra viva há 3 min, WS conectado, 132 assinaturas, ~2 300 eventos/min, 0 descartados, 0 reconexões, 1 097 avaliações, 0 propostas-sombra ainda (as moedas passam a porta tão raramente quanto na via de 15 s: ~6/h). Bloqueios de código da re-revisão fechados (corrida T4.52b-5, latência em sombra). A Sexta-feira acompanha a 1.ª hora com os critérios da revisão (dropped 0, reconexões ≤ 2, memória estável, sem proposta dupla por (mint, set)) e o desligamento é `MEME_EVENT_GATE=off` + recriar o radar.

## Adendo 18/09/2026 15:0x BRT — "usa a inteligência que já adquirimos e opera agora com o dinheiro que temos; pode variar os valores da entrada a partir de agora" (Everton, por escrito)

Everton delega à Sexta-feira o **tamanho por operação variável**, dentro do teto de 0,28 SOL e dos freios (cap diário 0,15, 2 posições, tesouraria). Leitura registrada: (1) **T4.61a** — a única vantagem limpa medida (KB-0118: não entrar depois de queda ≥ 50 % de um pico ≤ 60 s; 7 de 7 compras reais de 17→18/09 foram depois de queda) passa a valer também na pista de 15 s e é semeada como braço `flow_v2/9` (EXP-M13) para medição; (2) **T4.61b** — escada de convicção no executor (`MEME_CONVICTION_SIZING`, desligada até ele ligar): 1,0× do teto quando criador limpo pela cadeia, compradores ≥ 25, holders subindo, bundle ≤ 10 %/top-10 ≤ 20 %; cada fator faltando divide por 2; abaixo de 0,25× recusa; entrada depois de queda recusa. A escada inteira fica gravada em cada ordem para auditoria. A mesa continua operando a 0,28 fixo até o deploy; ligar a escada é a flag dele.

## Adendo 18/09/2026 15:4x BRT — "vou querer sim afrouxar; pode fazer girar na operação de verdade, você consegue mais dados, bora" (Everton, por escrito; "Sexta-feira decide com a Astra")

Decisão dele: afrouxar a mesa real para girar mais e colher dados, aceitando perdas. Parecer da Astra (`.claude/state/astra-afrouxar-2026-09-18.md`) e decisão da Sexta-feira: **só `max_sells_to_buys` 0,6 → 1,0** (o único afrouxamento com evidência: KB-0121/R48/R51; braço flow_v2/8 = +0,063 SOL hoje, ×3 de volume) **e ticket 0,28 → 0,07 SOL** (o espaço do cap diário hoje é 0,105 SOL depois da YOU; a 0,07 cabem 10–15 operações, a 0,28 caberia 1; o dado por operação é o mesmo em qualquer tamanho). Não afrouxa: holders/buyers (R51: zero ganho), top-10 (filtro de rug), criador desconhecido (29/35 morrem), pedigree (perde mais por aposta). Paradas duras: perda do dia ≥ 0,12 ou 3 perdas seguidas ≥ 50 % ou 6 seguidas → volta 0,6; criador vendeu em ≥ 5 das 8 primeiras → volta 0,6. Comandos executados por ele (script auditado).

## Adendo 18/09/2026 20:0x BRT — "vamos continuar no real; vamos perder dinheiro, mas estou aceitando o risco para ganhar conhecimento e estratégias válidas em cima da meme coin" (Everton, por escrito)

Decisão de princípio, registrada como tal: a mesa real continua operando como **instrumento de aprendizado**, com perda aceita, dentro dos freios (ticket 0,07, cap diário 0,15, 2 posições, tesouraria com cap de 50 USDC/dia, kill switch). Contrapartida da Sexta-feira: cada compra real vira ficha (KB) ou ajuste com número no mesmo dia; balanço diário real × papel; paradas duras da Astra (perda do dia ≥ 0,12, 3 rugs seguidos, criador vendedor em 5 das 8 primeiras) continuam valendo como freio de qualidade, não como fim do programa. Estado no momento: 15 compras reais desde 16/09, −0,18 SOL acumulado; mesa com Proposta A + razão 1,0 + saída rápida (alvo 1,3×, trailing 20 % sempre armado, 5 min) + radar por evento ligado; T4.63 (saída por evento) em construção.

## Adendo 19/09/2026 00:5x BRT — "faça essa estratégia agora; vamos arrumar o robô do que ele precisa" (Everton, por escrito): pista de lançamento (EXP-M18)

Everton manda construir a estratégia de lançamento (comprar no bloco da criação, sair em segundos) enquanto o R60 mede em papel. Registro: **T4.67 — pista de lançamento**, `MEME_LAUNCH_LANE=off|paper|on` (padrão off; `paper` = apostas em papel com preço do evento, sem ordem; `on` = ordem real com ticket próprio `MEME_LAUNCH_TICKET_SOL`, padrão 0,01). Radar: proposta no `create` (< 200 ms, sem linha de 15 s). Executor: perfil de admissão rápido (kill switch, carteira, cap diário, tamanho, simulação; sem leituras sob demanda), blockhash pré-carregado, prioridade alta, saída por evento em segundos (tempo 6–15 s, primeiro sell de terceiro, queda X % do pico). Ligar `on` é dele, depois do R60 e da revisão de risco; `paper` liga assim que subir.

## Adendo 19/09/2026 01:0x BRT — "pode subir ligado já" (Everton, por escrito): pista de lançamento em modo `on`

Everton autoriza a pista de lançamento a subir já em modo real (`MEME_LAUNCH_LANE=on`), sem esperar o R60. Registro da Sexta-feira: cumpre, com a revisão de risco relâmpago do guardião antes do deploy (regra do dia: nada que assina transação sobe sem revisão), ticket 0,01 SOL, no máximo 2 posições de lançamento, cap diário compartilhado (0,15), simulação mantida. A linha do `.env` é dele; a Sexta-feira mede as primeiras 20 compras (proposta → envio em ms, acerto, R) e compara com o R60.

## Adendo 19/09/2026 02:1x BRT — "esse alvo nosso não está alto?" / "pronto, começa agora" (Everton, por escrito): saída curta na mesa

Medido: reais que chegaram a +30 % = 4 de 15 (27 %); a +10–15 % = 6 de 15 (40 %); papel (3 dias) +30 % = 9–20 %, +15 % = 27–35 %. A mesa passa a **alvo 1,15×, trailing 10 % armado desde a entrada, 5 min** ("regra do Everton": entrar cedo, esperar ficar positiva, vender). Aplicado por ele às 02:10 via script auditado (agora validado antes de gravar, T4.64). Contexto que ele trouxe: à mão lucrava apostando alto, escolhendo "as que gostava", esperando ficar positiva e vendendo; o que perdia era descobrir tarde — o radar por evento resolve a descoberta. Pendências: endereço público da carteira manual dele para medir o histórico real; braço em papel `everton_v0/1` com a mesma regra.

## Adendo 19/09/2026 09:5x BRT — "vi que o Lab está dando bom, vamos operar com dinheiro real também" (Everton, por escrito): segunda mesa real

Papel 72 h: flow_v2/2 +0,105 (mas −0,084 nas últimas 24 h), **flow_v2/1 +0,054 e +0,103 nas 24 h (38 apostas, 45 % de acerto)**, flow_v2/5 +0,035/−0,030, operator/5 −0,070. O dia bom foi 17/09. Decisão: **segunda mesa `operator/6` = entrada do `flow_v2/1` + saída do Everton (1,15×, trailing 10 %, 5 min), ticket 0,07**, freios compartilhados (2 posições, cap 0,15, tesouraria, kill switch). Migração de semente (T4.71), revisão relâmpago, deploy; comparação real × papel dos dois conjuntos por 3 dias. Expectativa honesta: −0,02 a +0,05 SOL em 3 dias. R62: "sair na venda do grande" não ajuda (é o próprio gatilho); o dinheiro ficou no trailing 10 % → EXP-M17 (trailing 20/30 % em papel).

## Adendo 19/09/2026 10:3x BRT — o Lab de cripto normal vai para o real (mesa `spot/1`)

**Decisão do Everton (escrita, 10:2x–10:3x):** "o Lab já faz estratégia de análise, então pode ser que ali vamos ter mais vantagem do que o meme — quero testar logo no real com ele" e, depois da ressalva, "eu quero ir no dinheiro real e testar no real mesmo".

**Ressalva registrada (Sexta-feira):** o Lab de perps/spot não tem vantagem medida — `momentum v3` está *inconclusiva* (30 resultados, expectância −0,26 R) e nunca operou nem em papel (T4.72). A decisão é de aprendizado com perda aceita, mesma régua da mesa de memes (decisão 18/09).

**Como vai ser real:** não pela Binance (Fase 4: `LiveExecutionAdapter` bloqueado, sem cofre de chave de API) e sim pela **Solana com a carteira que já existe**: sinal do Lab (mercados da Binance) → mapa sinal→mint na Solana (R63) → compra/venda pela Jupiter (T4.73, troca genérica + script auditado) → mesa **`spot/1`**: ficha pequena (0,05 SOL), saída pela regra do próprio sinal (alvo/stop/tempo), mesmos freios da carteira (teto diário, posições abertas, chave). Primeiro passo obrigatório: teste real de ida e volta de 0,02 SOL com `--apply` do Everton. Revisão do risk-engine-guardian e do Codex antes de ligar. A autonomia em papel (T4.72) é ligada em paralelo para ter o contraste papel × real.

## Adendo 19/09/2026 23:2x BRT — recuperar o aluguel das ATAs Token-2022 (T4.77b)

R64 mostrou que 75 % da perda de 19/09 foi aluguel de ATA não devolvido (`MEME_CLOSE_ATA_ON_FULL_SELL` desligada): 35 contas vazias do pump.fun (Token-2022) = 0,0515 SOL parados. **Everton: "pode"** — estender o script auditado `meme_close_atas.py` com `--token-2022` sob as guardas da Astra (só conta de token, extensões ⊆ `immutableOwner`, ATA derivada com o programa certo, lotes homogêneos, 1 conta na primeira execução). Ligar `MEME_CLOSE_ATA_ON_FULL_SELL=1` no `.env` fica como ato dele.

## Adendo 20/09/2026 00:3x BRT — pausa por mint após perda na mesa real (T4.78)

**Everton:** "eu exijo que mexa pelo menos um pouco na estratégia". Sexta-feira e Astra tinham recomendado não mexer na mesa real hoje (R64: saída atual venceu 52 variantes; pausa por mint tiraria o NARKY#2 nas 24). **Decisão dele: aplicar.** Mudança escolhida = a de maior amostra a favor e menor risco: **recusar recompra do mesmo mint por 300 s após uma saída com perda** (papel 19/09: 19 recompras, 0 acertos, −0,338; real: Musepaid). Contraponto registrado (NARKY#2 +0,014). `MEME_MINT_COOLDOWN_AFTER_LOSS_S` no `.env` (0 desliga). Medição em sombra por 3 dias; se bloquear mais vencedoras que perdedoras, cai. Nada mais muda (alvo, recuo, tempo, ficha, saídas por evento).

## Adendo 22/09/2026 18:2x BRT — "pode ligar": fecho de ATA + mesa `spot/1` no real

Depois do R65 (72 % do prejuízo é custo; sem o aluguel o acerto de equilíbrio cai de 27 % para 19 % e a mesa fez 26 %) e da pergunta "e se sairmos da pump.fun?", **Everton autorizou ligar**: (a) `MEME_CLOSE_ATA_ON_FULL_SELL=1` na mesa de memes e a recuperação das 75 ATAs abertas (T4.77/b, prova de 1 conta antes do resto); (b) a mesa **`spot/1`** no real com `SPOT1_ENABLED=true` e `SPOT1_MAX_OPEN=1` (revisão T4.74 = aprovado com ressalvas, as duas fechadas na T4.74-7, já implantada).

**Ordem imposta pela realidade, não por cautela:** nada disso funciona enquanto o RPC da Solana estiver em *rate limit* (desde 21/09 12:08 BRT) — a `spot/1` usa o mesmo RPC para simular e enviar. Sequência: RPC → deploy da T4.78 → linhas no `.env` → recriar → prova de 1 ATA → `spot/1` com 1 posição. Refutação da `spot/1` continua no código (20 operações com expectância ≤ 0 ou Σ ≤ −0,15 SOL ⇒ mesa recusa sozinha).
