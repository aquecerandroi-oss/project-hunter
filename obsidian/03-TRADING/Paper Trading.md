---
tags: [trading, paper, m3]
updated: 2026-09-05
status: planejado
---

# Paper Trading

## Status

**Planejado para o Milestone 3.** Nenhum `ExecutionAdapter` existe hoje. As tabelas `portfolios`, `orders`, `fills`, `positions`, `trades`, `portfolio_equity_snapshots` existem como schema desde o M0, mas vazias — nenhuma ordem paper foi criada ainda.

## O que está especificado

Paper é um dos três `portfolio_type` (`paper|shadow|live`); é o modo em que o produto opera até a Fase 4 (`ENABLE_LIVE_TRADING=false`, sem exceções — ver [[Execution Engine]]).

**Fill.** Ordem a mercado contra o book top 25 do Redis; fill com walk do book (partial fills se o book não cobre); slippage real do book + `slippage_model` configurável; fee taker (Binance 0,05 %, Bybit 0,055 %); latência simulada 50–300 ms — o preço usado é o book **após** a latência, penalizando mercados rápidos de propósito. Se `spread_pct > max_spread_pct` no momento, a ordem é rejeitada com `reason=spread_guard`.

**Ordem manual paper** (papel TRADER+), planejada para o M3, existe para exercitar o motor de execução em Market Detail antes dos agentes existirem (M4). Passa pelo Risk Engine básico mesmo antes do engine completo do M4.

**Gestão de posição.** A cada 1 s: marca a mercado, atualiza PnL não realizado/MFE/MAE, verifica stop/alvos/invalidações/expiração, verifica limites do portfolio.

**Onboarding.** No M3, o passo 3 do onboarding (hoje só grava `default_initial_capital` no workspace) passa a criar o primeiro portfolio paper de verdade com o capital escolhido (padrão 10.000 USDT).

## Testes planejados

Fills contra books sintéticos (book raso → partial fill); invariante `equity = cash + Σ posições`; PnL com fees e slippage; stop e alvo parciais; restart do worker com posições abertas sem perder estado; idempotência (mesma proposta processada duas vezes gera uma única ordem).

## Relacionadas

[[Execution Engine]] · [[Portfolio]] · [[Risk Engine]]

## Fontes

`docs/PIPELINE.md` §8, `docs/ROADMAP.md` (Milestone 3), `docs/PRODUCT.md` §3
