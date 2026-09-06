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

## Em voo, ainda não commitada: outbox genérico + rate limit fail-closed (T2.9)

**Estado do trabalho: em voo, ainda não commitada.** Não há hash de commit para o
que segue — a fonte é o próprio código não commitado em
`packages/core/hunter_core/events/outbox*.py`,
`services/market-worker/hunter_market_worker/outbox.py`,
`packages/exchange-adapters/hunter_exchanges/rate_limit_gate.py`,
`rate_limit_local.py`, `rate_limit_suspension.py` e
`.claude/state/notes-T2.9.md`. Nada disto substitui o que já está em produção
até ser commitado e a T2.5/S2 confirmarem a migração.

**Outbox genérico.** `hunter_core.events.outbox` separa **enfileirar** (dentro
da transação que grava a linha de negócio, `outbox_store.enqueue`/`enqueue_many`)
de **publicar** (o despachante, fora dela). É o mesmo problema que o outbox do
Shadow Lab (`services/strategy-worker/hunter_strategy_worker/outbox.py`, esse
sim em produção desde a S2) já resolve para `shadow.signals.emitted`: sem essa
separação, um processo que morre entre o `COMMIT` do Postgres e o `XADD` no
Redis perde o evento para sempre, porque nada mais sabe que ele deveria existir.
Com a mesma transação, os três destinos de falha (antes do commit, entre commit
e `XADD`, depois do `XADD` e antes de `dispatched_at`) viram, respectivamente:
nada aconteceu, a próxima varredura publica, ou o evento é publicado duas vezes
— entrega é *at-least-once* por construção (Redis 7 não tem `XADD` idempotente),
e quem fecha a segunda ponta é `hunter_core.events.consume` filtrando
`event_id` já processado. A diferença entre os dois outbox hoje: o genérico
grava o **envelope inteiro** em `payload`; o da S2 grava só o payload de negócio
e monta o envelope no dispatch. A notas-T2.9.md §"Absorção da `shadow_outbox`"
descreve o caminho de migração (drenar a S2, copiar linhas pendentes envolvendo-as
num envelope, trocar o `enqueue`, só então apagar `shadow_outbox`) — planejado,
não feito. Achado da prova operacional: o custo de um `INSERT` por evento
deixava `/ready` do `market-worker` vermelho em `persistence` numa virada de
minuto com 200 mercados; corrigido com `enqueue_many` (um `INSERT ... ON
CONFLICT DO NOTHING` multi-linha por flush).

**Não migrado (bloqueado por arquivos travados da S2):** `market.universe.changed`
continua publicado *best-effort* pelo `universe.py`, fora do outbox — o brief da
T2.9 proíbe tocar em `universe.py`/`universe_repo.py` enquanto a S2 fecha.
Enquanto isso não muda, uma troca de universo perdida por um Redis fora do ar
continua sendo perdida.

**Rate limit fail-closed sem Redis.** Decisão do orquestrador em 2026-09-06,
registrada em `.claude/state/notes-T2.9.md` §"DECIDIDO": quando o Redis que
coordena o rate limit do REST da Binance não responde, o portão **recusa
admissões em vez de cair para um orçamento local por processo**
(`rate_limit_suspension.py`). O motivo é concreto: com `MARKET_SHARD` (T1.6b)
há N processos batendo na mesma API por um único IP de saída, e a Binance
contabiliza `429`/`418` **por IP**, não por processo. Se cada shard caísse para
um bucket local ao perder o Redis, N shards passariam a gastar N orçamentos
contra a cota única que a exchange enxerga — e o preço de estourar essa cota é
um banimento de IP (`418`), que não se desfaz rapidamente. Um gap de dados pode
esperar o Redis voltar (o WS continua ingerindo enquanto isso); um IP banido,
não. Comportamento confirmado no código: `TokenBucketRateLimiter._try_consume`
devolve `None` (nunca assume orçamento) e `acquire` entra em backoff curto com
jitter até o `max_wait_s` do chamador se esgotar, aí sim devolvendo
`RateLimited(reason="redis_unavailable")` — nunca uma exceção crua de Redis. O
bucket local em memória (`rate_limit_local.LocalBuckets`) continua existindo,
mas só para o caso "nunca houve coordenação" (processo único construído sem
`redis=`, hoje só em teste/script); um construtor de produção que esquecesse de
passar `redis=` voltaria a ter orçamento próprio sem alarme — resolvido só pela
única fábrica de produção (`market-worker/config.py:72`) sempre passar
`redis=`, sem uma trava que exija isso explicitamente (`uncoordinated=True`),
que fica como follow-up (T1.6b).

O portão de IP (`rate_limit_gate.py`) tem a mesma disciplina do outro lado: um
bloqueio que o processo já conhece nunca é esquecido (é espelhado localmente
antes da escrita compartilhada), e uma leitura do bloqueio que falha é tratada
como coordenação fora — **não** como "sem bloqueio conhecido" —, porque a Astra
achou, numa revisão do diff, que a versão anterior admitia requisições sem
saber de um banimento que outro shard já estava cumprindo.

**Divergência com o brief original:** o brief da T2.9 pedia "fallback em
memória se o Redis cair (com log)"; a implementação inicial fez isso, mas a
Astra recomendou suspender admissões em vez de cair para orçamento local, pelo
mesmo motivo do parágrafo acima. O orquestrador decidiu a favor da Astra em
2026-09-06 e o fallback foi removido — a versão final do código é a
fail-closed, não a do brief original.

## Infraestrutura já pronta para quando os workers existirem

- Runtime base (`HUNTER_ROLE`, heartbeat, `/health`) em `packages/core`.
- Envelopes de evento (`hunter_core.events`) e cliente Redis já definidos.
- Schema de banco completo (todas as 54 tabelas) já migrado, incluindo as tabelas que só os workers vão escrever (`candles`, `feature_snapshots`, `anomalies`, `trade_proposals`, `orders`, etc.) — ver `docs/DATABASE.md`.

## Relacionadas

[[System Overview]] · [[Data Flow]] · [[Market Collector]] · [[Execution Engine]] · [[Momentum Agent]] · [[Volume Agent]] · [[EXP-0001-momentum-v1]] · [[EXP-0002-volume-anomaly-v1]] · [[Open Bugs]] · [[Dialogos/SHADOW]] · [[Features]] · [[Anomalies]]

## Fontes

`docs/ARCHITECTURE.md` §3–4, `docs/DEPLOYMENT.md` §2–3, `infra/docker/docker-compose.yml`, `.claude/state/notes-T2.9.md` (T2.9, em voo)
