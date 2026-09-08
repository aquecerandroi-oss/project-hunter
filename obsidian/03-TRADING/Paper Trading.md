---
tags: [trading, paper, m3]
updated: 2026-09-08
status: carteira aberta e motor rodando; nenhuma ordem paper criada porque a ponte está desligada e o aceite operacional (T3.29) não foi feito
owner: sexta-feira
---

# Paper Trading

## Status

> **Atualizado em 2026-09-08 — a frase antiga desta seção deixou de ser verdade.** Ela dizia
> "planejado para o Milestone 3; nenhum `ExecutionAdapter` existe hoje". O simulador de execução
> paper e o `execution-worker` **existem, foram provados e rodam na VPS**, e a carteira permanente do
> Everton está aberta desde 2026-09-07 04:27Z (19.333,0111164813 USDT — ver [[Portfolio]]).

**O que continua verdadeiro:** `orders`, `fills`, `positions`, `trades` seguem **vazias** — nenhuma
ordem paper foi criada. Não por falta de motor, e sim porque a **ponte sinal → admissão está
desligada** (`ENABLE_PAPER_AUTONOMY=false`): a linha `momentum v3` paper, ativa desde **02:57 de
Brasília de 2026-09-08**, emitiu **154 sinais** e produziu **0 propostas, 0 posições, 0 trades**
([[Diario/2026-09-08]]).

## Antes de ligar a chave: sete itens, e a maioria ainda **não medida**

A revisão da Astra de 2026-09-08 ([[2026-09-08-shadow-lab-pronto]]) mostrou que as quatro condições
que a base citava não eram todas. O aceite operacional completo — admissão, `avgPrice`, proteção
degradada, qualidade do MTM, integração (WS + Redis), backup restaurável e o DSN de dono — está na
tabela de [[Execution Engine]], com o estado de cada linha e o arquivo:linha do risco. Cinco deles
estão em [[Open Bugs]]; o brief é `.claude/state/brief-T3.29-autonomy-acceptance-run.md`.

Ligar `ENABLE_PAPER_AUTONOMY` é decisão do **Everton**, e a recomendação registrada é **esperar**:
com β indisponível em 100% dos mercados, o Risk Engine recusaria as propostas de qualquer jeito.

## O que está especificado

Paper é um dos três `portfolio_type` (`paper|shadow|live`); é o modo em que o produto opera até a Fase 4 (`ENABLE_LIVE_TRADING=false`, sem exceções — ver [[Execution Engine]]).

**Fill.** Ordem a mercado contra o book top 25 do Redis; fill com walk do book (partial fills se o book não cobre); slippage real do book + `slippage_model` configurável; fee taker (Binance 0,05 %, Bybit 0,055 %); latência simulada 50–300 ms — o preço usado é o book **após** a latência, penalizando mercados rápidos de propósito. Se `spread_pct > max_spread_pct` no momento, a ordem é rejeitada com `reason=spread_guard`.

**Ordem manual paper** (papel TRADER+), planejada para o M3, existe para exercitar o motor de execução em Market Detail antes dos agentes existirem (M4). Passa pelo Risk Engine básico mesmo antes do engine completo do M4.

**Gestão de posição.** A cada 1 s: marca a mercado, atualiza PnL não realizado/MFE/MAE, verifica stop/alvos/invalidações/expiração, verifica limites do portfolio.

**Onboarding.** No M3, o passo 3 do onboarding (hoje só grava `default_initial_capital` no workspace) passa a criar o primeiro portfolio paper de verdade com o capital escolhido (padrão 10.000 USDT).

## Testes planejados

Fills contra books sintéticos (book raso → partial fill); invariante `equity = cash + Σ posições`; PnL com fees e slippage; stop e alvo parciais; restart do worker com posições abertas sem perder estado; idempotência (mesma proposta processada duas vezes gera uma única ordem).

## Relacionadas

[[Execution Engine]] · [[Portfolio]] · [[Risk Engine]] · [[Open Bugs]] ·
[[2026-09-08-shadow-lab-pronto]] · [[EXP-0005-momentum-paper]]

## Fontes

`docs/PIPELINE.md` §8, `docs/ROADMAP.md` (Milestone 3), `docs/PRODUCT.md` §3
