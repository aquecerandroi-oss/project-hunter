---
tags: [arquitetura, workers, shadow-lab]
updated: 2026-09-06
status: parcial
---

# Workers

O backend Python é um único artefato Docker; a variável `HUNTER_ROLE` escolhe qual processo roda (`api | market | scanner | strategy | execution | analytics | all`). Em desenvolvimento, `HUNTER_ROLE=all` roda todos os workers num processo com tasks `asyncio`; em produção cada papel escala isoladamente.

## Estado atual (2026-09-06)

Dois papéis estão implementados e rodando; os outros três continuam vazios.

| Worker | Estado | O que faz hoje |
|---|---|---|
| `market-worker` | **no ar** (M1 aprovado) | WS da Binance → normaliza → Redis hot state → candles/snapshots/funding/OI/liquidações no Postgres → publica `market.*`; recovery de gaps por REST; supervisão, `/ready` e heartbeat |
| `strategy-worker` | **no ar** (S2 do Shadow Lab) | consome `market.candles.closed`, avalia as `strategy_versions` ativas em modo sombra, persiste decisão + outcome + episódio + outbox na mesma transação e despacha `shadow.signals.emitted` |
| `scanner-worker` | vazio | M2 |
| `execution-worker` | vazio | M3/M4 |
| `analytics-worker` | vazio | M5 |

## `strategy-worker` em modo sombra — o que ele é e o que ele não é

- **Escritor único dos outcomes do Lab.** `advance_tracking`, `settle` e a liberação do slot em
  `shadow_episodes` acontecem **só** neste processo. A transferência futura ao `analytics-worker`
  está registrada em `docs/PIPELINE.md` §6b: quando acontecer, os três **mudam** de processo, não
  são duplicados. Dois escritores sobre o mesmo acompanhamento fariam o resultado depender de qual
  laço rodou primeiro.
- **Stream próprio, `purpose = research_only`.** Os eventos saem em `shadow.signals.emitted` (não em
  `signals.emitted`), com `event_id = signal_id`, e o envelope persistido carrega
  `purpose = research_only`. O proposal builder do M4 **recusa** `research_only` — há teste para
  isso. `active` numa `strategy_version` não implica elegibilidade de execução.
- **Nada aqui pode ordenar.** Sem carteira, sem ordem, sem posição, sem Risk Engine no caminho —
  porque não há caminho para execução nenhuma. Ver [[Risk Engine]] e [[Execution Engine]].
- **Cadência dupla:** decisões só em fechamentos distintos do timeframe da estratégia (15 min para
  `momentum`, 5 min para `volume_anomaly`, UTC); acompanhamentos avançam em barras de 1 min.
- **Supervisão:** `/ready` com seis checagens (`database`, `redis`, `shadow_migration`,
  `shadow_versions`, `shadow_consumer`, `shadow_outbox`) e heartbeat `hb:strategy:shadow` com
  `evaluated_bars`, `evaluations_by_state`, `open_trackings`, `outbox_pending`, `outbox_lag_s` e
  `errors`. `shadow_versions` fica **vermelho** quando existem linhas `active` e nenhuma
  executável — a falha que deixava o Lab morto com `/ready` verde.
- **`tracking_hold`:** o `strategy-worker` publica ao `market-worker` a lista de mercados com
  acompanhamento aberto, e o coletor mantém as velas de um mercado excluído do universo até o
  término. É o oposto do bug de gaps de mercados não monitorados ([[Open Bugs]]).

Resultados e cobertura em [[EXP-0001-momentum-v1]] e [[EXP-0002-volume-anomaly-v1]].

## Papéis ainda não implementados

| Worker | Papel | Cadência | Milestone |
|---|---|---|---|
| `scanner-worker` | Feature Engine, Anomaly Engine, Regime Engine, Opportunity Engine | evento + 1 min | M2 |
| `execution-worker` | ExecutionAdapter (paper/shadow), posições, trades, kill switch enforcement | evento + 1 s | M3/M4 |
| `analytics-worker` | Estatísticas por agente/estratégia/regime, retenção; assume os outcomes do Lab | 1 min / 1 h / diário | M5 |

**Isolamento planejado do `execution-worker`:** será o único processo com acesso a chaves descriptografadas de exchange (Fase 3); não expõe HTTP além de `/health`; o `api` nunca descriptografa chaves.

## Infraestrutura já pronta para quando os workers existirem

- Runtime base (`HUNTER_ROLE`, heartbeat, `/health`) em `packages/core`.
- Envelopes de evento (`hunter_core.events`) e cliente Redis já definidos.
- Schema de banco completo (todas as 54 tabelas) já migrado, incluindo as tabelas que só os workers vão escrever (`candles`, `feature_snapshots`, `anomalies`, `trade_proposals`, `orders`, etc.) — ver `docs/DATABASE.md`.

## Relacionadas

[[System Overview]] · [[Data Flow]] · [[Market Collector]] · [[Execution Engine]] · [[Momentum Agent]] · [[Volume Agent]] · [[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Open Bugs]] · [[Dialogos/SHADOW]]

## Fontes

`docs/ARCHITECTURE.md` §3–4, `docs/DEPLOYMENT.md` §2–3, `infra/docker/docker-compose.yml`
