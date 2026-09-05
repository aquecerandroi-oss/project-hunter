---
tags: [trading, portfolio, m3]
updated: 2026-09-05
status: planejado
---

# Portfolio

## Status

**Planejado para o Milestone 3.** A tabela `portfolios` existe desde o M0 (schema completo, RLS aplicada), mas não há CRUD de API nem UI ainda — nenhum portfolio real foi criado por um usuário.

## Modelo (schema já migrado)

`portfolios`: `organization_id`, `workspace_id`, `name`, `type` (`paper|shadow|live`), `base_currency` (USDT), `initial_capital`, `risk_profile_id`, `exchange_connection_id` (null no MVP), `execution_config` (fee/slippage/latency model), `status` (`active|paused|archived`), `kill_switch_state`, `is_arena` (para o M6). Isolado por RLS como qualquer tabela de tenant (ver `docs/DATABASE.md` §1.2).

Tenancy: `USER → ORGANIZATION → WORKSPACE → PORTFOLIOS → AGENTS`.

## O que o M3 vai entregar

- CRUD de portfolios, risk profile por portfolio.
- Onboarding passa a criar o primeiro portfolio paper com o capital escolhido no passo 3 (hoje esse passo só grava a preferência no workspace).
- API: `portfolios`, `positions`, `orders`, `trades`, `equity`; WS `rt:org:*:portfolio:*`.
- Web: `/portfolio` (lista, detalhe, equity curve, posições), `/trades`, `/trades/[id]`.

Segundo `docs/PRODUCT.md`, o item de navegação `/portfolio` está registrado no `nav-registry` com `Disponível a partir de: M3` — hoje ele não aparece como funcional na sidebar.

## Relacionadas

[[Paper Trading]] · [[Execution Engine]] · [[System Overview]]

## Fontes

`docs/DATABASE.md` §7, `docs/PRODUCT.md` §2 e §4, `docs/ROADMAP.md` (Milestone 3)
