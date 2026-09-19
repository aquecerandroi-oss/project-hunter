---
tags: [experimento, meme, lancamento, sniper, evento, m4]
status: pre-registrado
owner: sexta-feira
updated: 2026-09-19
origem: Everton, 19/09/2026 00:3x BRT — "assim que a moeda é criada dá um pico; se compramos assim que começa a subir conseguimos comprar no lançamento e vender na alta rápida?"
---

# EXP-M18 — Sniper de lançamento (compra no bloco da criação, venda no pico de segundos)

## Hipótese (congelada antes de medir)
Comprar em ≤ 1 s após o `create` (feed por evento em `processed`) e vender em +6 s, +15 s ou no primeiro trade de venda de terceiros paga em média, líquido de taxas (1,25 %/perna), slippage 5 % e prioridade, apesar de a maioria das moedas morrer.

## O que já sabemos (contra e a favor)
- KB-0123: 46 % das graduações nascem cheias (create → cheia em ~1 s): pico não comprável.
- R58/KB-0138: entrar "quando sobe" e sair no recuo = negativo em 54 células; quem faz o pico vende para quem chega 2–3 s depois.
- KB-0136: carteiras que lucram no lançamento seguram 1–13 s; entrada a 3 s pega 1,01×.
- A favor: nunca medimos a entrada a ≤ 1 s com custo real; o feed de `create` já existe (PumpPortal) e o de trades também (WS do RPC).

## Método (R60, papel)
Captura própria de 60 min no pico (14–20 BRT) de TODOS os `create` + trades program-wide (`logsSubscribe` no programa pump, como no R58). Para cada moeda: preço em +1 s (entrada), em +6 s, +15 s, +60 s, e no primeiro sell de terceiro; R líquido por regra; taxa de acerto; concentração no top-3; sinais por hora; comparação com "entrar em +3 s" (o que a nossa infra faz hoje) e "+0,5 s" (RPC regional).

## Braço (se pagar em papel)
Conjunto `launch_v0/1` (`research_only`): sem porta de saúde (não existe dado), ticket 0,01 SOL, saída fixa +6 s ou primeiro sell de terceiro, ≤ 200 tentativas/dia. Controle: `flow_v2/6`.

## Regra de decisão
Vira mesa só se: R médio líquido > 0 com ≥ 300 moedas, top-3 < 50 % do lucro, e o custo de prioridade cabe. Se negativo a +1 s, o jogo do lançamento é dos bots colocados no bloco: descartar e registrar.

Ligações: [[KB-0123-graduacoes-born-full]] · [[KB-0138-explosao-de-compradores-nao-tem-vantagem]] · [[KB-0136-carteiras-vencedoras-nao-sao-gatilho]] · [[KB-0134-websocket-do-rpc-lag-medido-ao-vivo]]

## Braço semeado (T4.67a, 19/09/2026)

`launch_v0/1` (`0053_meme_launch_lane_arm`, `research_only`, `01994d00-6c1a-7000-8000-000000000017`)
está semeado e ativo, atrás de `MEME_LAUNCH_LANE=off|paper|on` (padrão `off` — ninguém liga sozinho).
Parâmetros exatamente os do pré-registro acima: `size_sol "0.01"`, `max_creator_initial_sol "2"`,
`exit_key "lancamento_6s_ou_primeiro_sell"`, `time_stop_s 6`, `exit_on_first_third_party_sell true`,
`max_drawdown_from_peak_pct "20"`.

**Gatilho escolhido: o stream `create` do PumpPortal** (já em produção, `discovery.py`), não um novo
`logsSubscribe` program-wide no programa pump — `plan-T4.52b.md` §1 já media esse transporte em
~100 ms e nunca escolheu o caminho program-wide para nada além de uma PDA já conhecida; construir e
decodificar um `CreateEvent` novo, sem fixture e sem medição própria, gastaria o orçamento da tarefa
num transporte provavelmente não mais rápido que o já testado. Não houve nova medição ao vivo —
decisão de engenharia declarada, não um resultado de bancada.

**"Nasce cheia" (KB-0123), leitura declarada**: como a proposta sai em < 200 ms do `create` — antes
de existir qualquer preço —, ela **não pode** ser condicionada ao progresso de +2 s. O que a pista
faz é abandonar a *entrada em papel pendente* se o progresso atingir 90 % dentro de 2 s antes do
preço de +1 s existir (contado em `born_full_60s`); a proposta em si (o registro de que a pista
decidiu, no instante do `create`) permanece. Uma leitura, não uma certeza — sinalizada para quem
julgar os resultados.

A aposta de papel é precificada por evento (não pelo preenchimento de 15 s do Lab): entra no
primeiro preço observado em `create + 1 s`, sai no primeiro de três gatilhos (`time_stop_s`, a
primeira venda de um endereço que não é o criador, ou 20 % de queda do pico) — reaproveitando as
mesmas peças do Lab (`BetEntry`/`BetExit`/`mark_filled`/`close_bet_row`/`paper_engine.close_bet`).
Nada disto decide ainda: `kind = 'research_only'`, papel por construção. Detalhes técnicos e as
simplificações declaradas em `.claude/state/notes-T4.67a.md`; braço executável real (T4.67b,
`docs/RISK_ENGINE_MEME.md` §18) semeado em paralelo, ainda sem dado medido.
