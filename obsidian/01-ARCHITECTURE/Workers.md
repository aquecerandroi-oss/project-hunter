---
tags: [arquitetura, workers]
updated: 2026-09-05
status: planejado
---

# Workers

O backend Python é um único artefato Docker; a variável `HUNTER_ROLE` escolhe qual processo roda (`api | market | scanner | strategy | execution | analytics | all`). Em desenvolvimento, `HUNTER_ROLE=all` roda todos os workers num processo com tasks `asyncio`; em produção cada papel escala isoladamente.

## Estado atual

`hunter_core.runtime.RoleRegistry` existe como mecanismo (o runtime que lê `HUNTER_ROLE` e decide o que executar, com heartbeat e `/health`), mas **está vazio** — nenhum papel de worker tem lógica de negócio registrada. Por isso, no `docker-compose.yml`, o serviço `worker` com `HUNTER_ROLE=all` imprime que ainda não tem papéis e sai com código 0. Isso é intencional (comentário no compose e em `infra/docker/entrypoint.sh`): nenhum processo falso fica "rodando" sem fazer nada.

## Papéis planejados (nenhum implementado)

| Worker | Papel | Cadência | Milestone |
|---|---|---|---|
| `market-worker` | WS Binance/Bybit → normaliza → Redis hot state → candles no Postgres → publica `market.*` | contínuo | M1 |
| `scanner-worker` | Feature Engine, Anomaly Engine, Regime Engine, Opportunity Engine | evento + 1 min | M2 |
| `strategy-worker` | Agentes, proposal builder, Risk Engine | evento | M4 |
| `execution-worker` | ExecutionAdapter (paper/shadow), posições, trades, kill switch enforcement | evento + 1 s | M3/M4 |
| `analytics-worker` | Estatísticas por agente/estratégia/regime, `signal_outcomes`, retenção | 1 min / 1 h / diário | M5 |

**Isolamento planejado do `execution-worker`:** será o único processo com acesso a chaves descriptografadas de exchange (Fase 3); não expõe HTTP além de `/health`; o `api` nunca descriptografa chaves.

## Infraestrutura já pronta para quando os workers existirem

- Runtime base (`HUNTER_ROLE`, heartbeat, `/health`) em `packages/core`.
- Envelopes de evento (`hunter_core.events`) e cliente Redis já definidos.
- Schema de banco completo (todas as 54 tabelas) já migrado, incluindo as tabelas que só os workers vão escrever (`candles`, `feature_snapshots`, `anomalies`, `trade_proposals`, `orders`, etc.) — ver `docs/DATABASE.md`.

## Relacionadas

[[System Overview]] · [[Data Flow]] · [[Market Collector]] · [[Execution Engine]]

## Fontes

`docs/ARCHITECTURE.md` §3–4, `docs/DEPLOYMENT.md` §2–3, `infra/docker/docker-compose.yml`
