---
tags: [experimento, meme, lancamento, sniper, evento, m4]
status: descartado
owner: sexta-feira
updated: 2026-09-19
origem: Everton, 19/09/2026 00:3x BRT — "assim que a moeda é criada dá um pico; se compramos assim que começa a subir conseguimos comprar no lançamento e vender na alta rápida?"
tipo: pesquisa
hipotese: —
variavel: —
populacao: —
efeito: —
ic: —
veredito: —
proximo_passo: —
classe_de_perda: —
mercado: meme
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

## Resultado (R60, 19/09/2026 — papel, cadeia inteira)

**Descartado pela regra pré-registrada.** Captura própria de 60 min (`logsSubscribe` no programa pump,
RPC público, `processed` + segunda conexão em `confirmed`; 00:35–01:35 BRT, hora fraca): 1 072 `create`,
114 832 trades, 0 quadros perdidos; 885 lançamentos em SOL avaliados (15,8 % com quote ≠ SOL excluídos).

| entrada | t6 | t15 | t60 | 1.º sell de terceiro | 1.º sell de comprador do bloco | braço T4.67a |
|---|---|---|---|---|---|---|
| +0,5 s (RPC regional) | −15,1 % | −11,5 % | −11,2 % | −15,1 % | −11,2 % | −14,8 % |
| **+1 s (feed por evento)** | **−15,2 %** | −11,9 % | −12,0 % | −15,5 % | −11,9 % | **−15,2 %** |
| +3 s (infra atual) | −13,9 % | −10,5 % | −10,0 % | −14,3 % | −9,6 % | −13,9 % |

R médio líquido (1,25 %/perna, slippage 5 %/3 %, prioridade 0,0002 SOL/tx, ticket 0,01 SOL), n = 885 em
cada célula; acerto 6–16 %; mediana −13,9 % em todas (preço parado); MDD ≈ ΣR (a equity só desce); top-3 =
16–44 % de um lucro bruto que é menos da metade das perdas. Só com taxa (slippage 0, prioridade 0):
−3,9 % … +1,7 % — o movimento bruto médio do lançamento é ≈ 0 a +2 %. Oráculo "pico exato em 6 s": −7,2 %.
Nenhum subconjunto vira positivo (já subindo em ≤ 1 s: −14,2 %; ≥ 2 compradores em 1 s: −13,6 %; +10 % em
1 s: −16,6 %; dev-buy ≤ 2 SOL: −15,1 %; não nasce cheia: −15,2 %).

Regra de decisão: R médio a +1 s < 0 com n ≥ 300 → **o jogo do lançamento é dos bots colocados no bloco**
(30 % dos lançamentos têm comprador de terceiros no mesmo slot do `create`; 45 % em ≤ 1 s; 1.º comprador →
pico p50 3,5 s, p25 = mesmo instante). Nasce cheia: 2,0 % de todos os `create`. Sem trade depois do
`create`: 6,2 %; sem comprador de terceiros em 60 s: 18 %. `confirmed` chega 0,18 s depois de `processed`.
Sanity do R58 nesta captura: 54/54 células de explosão negativas (−6,6 % … −9,1 %).

O braço `launch_v0/1` (T4.67a) fica `MEME_LAUNCH_LANE=off`; se alguém o ligar em papel, a previsão
pré-registrada é **R médio ≈ −15 %, acerto ≈ 6–10 %** (controle negativo). Captura diurna 14:00–15:00 BRT
agendada em processo desanexado (não faz parte deste resultado). Detalhes, tabelas completas e ressalvas:
`.claude/state/notes-R60.md` · [[KB-0141-sniper-de-lancamento]].
