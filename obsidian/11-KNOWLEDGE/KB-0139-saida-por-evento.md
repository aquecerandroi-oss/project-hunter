---
tags: [knowledge, meme, evento, saida, executor, trailing, t4-63, m4]
status: vivo
owner: sexta-feira
updated: 2026-09-18
fonte: .claude/state/notes-T4.63.md
---

# KB-0139 — Saída por evento: a posição real é julgada a cada trade da curva, não a cada tique (T4.63, 18/09/2026)

**Pergunta.** Quanto custa decidir a saída de uma posição real só a cada 10 s, e o que muda quando a mesma regra roda em cada atualização da curva?

**Medido (o caso que motivou).** CITIZEN, 18/09/2026, 19:06:43 → 19:11:29 BRT, mesa real: compra a 0,0716 SOL, pico de marca 0,1303 (**+82 %**), venda pelo trailing a 0,0142 (**−0,80 R**). A curva foi drenada em segundos **entre dois tiques** de `exits.py`: o trailing (que teria vendido perto de +45 %) só foi avaliado quando já não havia SOL na curva. Não foi erro de regra — a regra estava certa e chegou tarde. Referência de latência do transporte (KB-0134): `received_at − block_time` p50 1,5 s no WS do RPC; `confirmed` chega 0,06 s depois de `processed`.

**O que foi construído (`MEME_EVENT_EXITS`, padrão `off`).**
- Um WebSocket de RPC Solana do próprio executor (`SolanaWsClient`, o mesmo do portão de evento do radar), `confirmed`; para cada posição aberta, `accountSubscribe` + `logsSubscribe` da PDA da curva (assina no fill e a cada 2 s; desassina no fechamento; teto `max_open_positions`).
- Cada notificação vira **a mesma marca** do tique (líquido de vender tudo agora, taxas fora), o pico segue toda atualização (em memória **e** na linha, para sobreviver a restart) e passa pelo **mesmo** `decide_exit` com os **mesmos** `ExitParams` do conjunto.
- Disparou ⇒ **a mesma venda** do tique (`sell_on_event` → `route_exit` → `_sell`): trava por posição, releitura da linha, `CurveRead` fresco, simulação, tolerância 5 %/15 %, reenvio dos mesmos bytes. O tique de 10 s continua como reserva.
- Venda do criador vista no `TradeEvent` ⇒ `creator_sold_seen_at` carimbado **com a fração medida** (vendido ÷ `creator_initial_tokens`; sem alocação registrada, só memória) e `creator_dump` dispara no próprio frame, com a tolerância de pânico.
- Falha fechada = "só tique": frame ruim contado, reconexão com backoff para sempre, fila limitada, restart do runtime em 5 s, nunca o executor parado.
- Heartbeat: `event_exits_*` e `event_to_sell_submit_s_p50/p95` — o número que CITIZEN perdeu, para ser relido depois do deploy.

**Provado (Postgres real, testcontainers).** Uma notificação de −35 % ⇒ **uma** ordem `confirmed` com `exit_reason = trailing`, posição fechada com o mesmo motivo, e o tique logo depois não vende nada; uma venda do criador no `logsNotification` ⇒ carimbo com fração 0,1129 e venda `creator_dump` a 15 %; o pico sobrevive a um restart do runtime.

**O que muda na operação.** Ligar é decisão do Everton (`docs/ACTIVATION.md` 9g). Depois de ligar, ler `event_to_sell_submit_s_p50` (alvo < 2 s) e `event_exits_triggered_total` no `hb:meme:executor`. Nada da política de capital, do tamanho ou da admissão mudou — a mesma decisão chega antes.

**Ressalvas.** A velocidade encurta a espera até a regra, não a espera da cadeia (pouso da venda 1–3 s, disputa por prioridade, `TooLittleSolReceived` numa curva derretendo — KB-0135: a vantagem não está na saída). Um caso (CITIZEN) motivou; o ganho em R por posição ainda não foi medido — fica para o primeiro dia com a flag ligada.

Ligações: [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]] · [[KB-0135-a-vantagem-nao-esta-na-saida]] · [[KB-0138-explosao-de-compradores-nao-tem-vantagem]] · [[KB-0118-nao-entrar-depois-da-queda]]
