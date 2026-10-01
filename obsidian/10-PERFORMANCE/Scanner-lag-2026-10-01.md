---
tags: [performance, scanner, radar, redis-streams, diagnostico, persistencia, incidente]
updated: 2026-10-01
status: parcial
owner: backend-specialist
---

# `scanner-worker` ~2 h atrás em `market.candles.closed` — a causa é o scanner não gravar nada (diagnóstico de 01/10/2026)

> **Medido na VPS entre 03:39Z e 04:06Z de 01/10/2026, só leitura** (`redis-cli` de leitura, `docker stats`, `GET /metrics` de dentro do contêiner, `docker logs --since`, consultas em `BEGIN READ ONLY`). Nenhum serviço reiniciado, nenhum `XGROUP`/`XTRIM`/`DEL`, nenhum `git pull`, nada instalado em produção. Origem: o "achado lateral" de [[Late-delay-do-Lab-diagnostico-2026-10-01]]. Revisão da Astra: [[2026-10-01-scanner-lag]].

## Veredito em quatro linhas

1. **O lag é sintoma.** O `scanner-worker` **não persiste nada desde 30/09 ~13:36Z** (14 h): o último `feature_snapshots` é de 13:36:00Z (em 30/09 12:00–12:59Z foram 11.990 linhas; às 13h só 7.321 = 36,6 min), a última linha de `opportunity_history` de 13:36:57Z, a última anomalia detectada de 13:36:40Z. O contêiner continua `healthy` e `/ready` responde 200.
2. **Por quê:** cada `flush_batch` falha com `UniqueViolationError: uq_anomalies_active_per_market_type` (≈ 100 % dos ciclos, um a cada ~9 s; 20 pares `(mercado, tipo)` distintos nos logs retidos). O lote inteiro (200 mercados) é revertido e **descartado**, e os ACKs que esperam o commit se perdem.
3. **O lag nasce daí:** sem ACK o PEL do grupo cresce (17.050 hoje) e `hunter_core.events.consume` faz `XAUTOCLAIM` (ocioso ≥ 30 s, a partir de `0-0`) **antes de cada leitura nova**, reentregando ao próprio consumidor as próprias pendentes: **15,9 milhões de entregas em 13 h contra ~170 mil mensagens produzidas** (+19.324 entregas em 60 s medidos para ~220 novas/min = ~88×). Isso satura o loop de eventos (98 % de um núcleo) e o consumidor lê quase só no ritmo da produção.
4. **Não é** `history_v2` (28/09), nem o número de mercados (200), nem falta de sharding: até 13:36Z de 30/09 o mesmo código gravava 12 mil snapshots/hora sem lag. **O que ainda não sei:** o *primeiro* erro que desencadeou o envenenamento — os logs do Docker e do Postgres só retêm desde ~03:03Z/02:50Z (rotação de ~30 min causada pelos tracebacks de dezenas de KB).

## 1. Medições (comandos e saídas reais)

### 1.1 Grupo, PEL e ritmo

`XINFO GROUPS market.candles.closed` (03:40:09Z) e de novo às 04:06:05Z:

```text
03:40  name scanner-worker.market.candles.closed consumers 110 pending 17121 last-delivered-id 1790818800520-0 entries-read 9576339 lag 32608
04:06  name scanner-worker.market.candles.closed consumers 110 pending 17050 last-delivered-id 1790820721383-0 entries-read 9583529 lag 32630
       (strategy-worker.shadow.{0..3}of4: pending 0, lag 0; strategy-worker.shadow, o grupo órfão: lag 50.005)
```

- `last-delivered` 01:40:00Z às 03:40Z (atraso **2 h 00 min**) → 02:12:01Z às 04:06Z (**1 h 54 min**): ganha ~0,23 min por minuto, ~8 h para zerar *se nada mudar*.
- Margem até perder dado: `first-entry` do stream 00:54:00Z contra `last-delivered` 02:12:01Z = **78 min** (era 72 min às 03:40Z). Hoje a margem **não está encolhendo**; se o grupo parasse de vez, a perda começaria em ~78 min. O que o trim já apagou são mensagens **entregues e pendentes** (o mínimo do PEL, `1790815980976-2`, acompanha a cauda do stream): o `XAUTOCLAIM` as descarta do PEL. Não há perda de mensagem *nunca entregue*.
- `XPENDING`: todas as 17.050 são do consumidor atual (`scanner-worker@fa8e3bf8536d:1`); os outros 109 consumidores do grupo têm `pending 0` (resíduo de reinícios).
- Em amostras de 1,5 s o grupo avança em **saltos de um minuto de stream (~220 entradas) por minuto de relógio** e o `lag` oscila ±220 — o consumidor lê no ritmo da produção.

### 1.2 O reprocessamento (a assinatura do `XAUTOCLAIM` sobre o próprio PEL)

`GET /metrics` do scanner (porta 8001, de dentro do contêiner, 03:50:34Z → 03:51:34Z):

```text
hunter_scanner_consumer_events_total{stream="market.candles.closed"}  15930010 → 15949334   (+19.324 em 60 s)
hunter_scanner_persist_batch_seconds_count                              5780 →     5787   (7 lotes/min, ~8,5 s cada)
hunter_scanner_markets_evaluated_total{outcome="covered"}              999922 →  1001140   (1.218/min)
```

Desde o início do processo (30/09 14:49:26Z, `*_created`): 15,9 M de entregas de vela contra, no stream, ~260 entradas/min (`XLEN` 50.005 em 3 h 12 min) → ~170 mil em 13 h.

### 1.3 O erro (log do scanner, `docker logs --since`, ~03:03Z em diante)

```text
{"event": "scanner_cycle_failed", ... "timestamp": "2026-10-01T03:45:15Z"}
asyncpg.exceptions.UniqueViolationError: duplicate key value violates unique constraint "uq_anomalies_active_per_market_type"
DETAIL:  Key (market_id, type)=(01a073bb-9bab-7704-b083-6ce85d7b72ad, MOMENTUM_SHIFT) already exists.
  File ".../runners.py", line 109, in evaluation_loop    invalidated = await flush_batch(factory, redis, batch, now=now)
  File ".../persist.py", line 172, in flush_batch        await writers.write_anomalies(session, batch.anomalies)
```

- 263 falhas em 43 min (03:03–03:46Z); `hb:scanner:*` mostra `errors 4963`, `evaluations 992398`, `dirty 194`; o Postgres registra o mesmo erro (348 vezes nas 1 h 15 min que retém).
- Pares mais frequentes: `FUNDING_ANOMALY` (123), `ORDERBOOK_IMBALANCE` (93 e 78), `OPEN_INTEREST_SPIKE` (90), `MOMENTUM_SHIFT` (60)…

### 1.4 O banco (só leitura)

```text
feature_snapshots_2026_09 max ts           2026-09-30 13:36:00+00     (feature_snapshots_2026_10: vazia)
opportunity_history_2026_09 max ts         2026-09-30 13:36:57.085+00
opportunities max last_updated_at          2026-09-30 14:50:26.457+00   (29 linhas; as expirações de 60 s depois do boot)
anomalies                                  active 585 (todas com > 4 h) · resolved 120.426 · expired 11.287
```

Linhas ativas dos pares envenenados, todas com `detected_at` ≤ 13:36Z: `MOMENTUM_SHIFT` `01a0f287…` (13:36:07), `ORDERBOOK_IMBALANCE` `01a0f283…` (13:31:55), `FUNDING_ANOMALY` `01a0f1d0…` (10:16:02), `OPEN_INTEREST_SPIKE` `01a0f264…` (12:57:32). O INSERT que o banco recusa é de **outro id** — o scanner acredita que o par está livre.

Contagem de snapshots por hora em 30/09: 08h 12.002 · 09h 11.963 · 10h 12.004 · 11h 12.003 · 12h 11.990 · 13h 7.321 — 200 mercados × 60 min, até a hora em que parou.

### 1.5 CPU

`docker stats --no-stream` (03:44Z): `hunter-scanner-worker-1` **98,2 %** de um núcleo (a VPS tem 12); `strategy-worker-1-1` 37 %, `-3-1` 52 %, os demais shards < 1 %; `market-worker` 24–34 % cada; Redis 23 %; Postgres 17 %. O `py-spy` **não** está instalado no contêiner; não instalei nada — o perfil fino não foi feito, e a fração dos 98 % que cabe à espiral do `XAUTOCLAIM` contra o avaliador é inferência (ver Astra).

## 2. O mecanismo

1. **Memória avança antes do commit.** `collect.collect_anomalies` (`collect.py:85-111`) e `watchdog._expire_anomalies` (`watchdog.py:115-119`) esquecem o id da anomalia (`anomaly_ids.pop`) assim que a máquina de estados a fecha — antes de `flush_batch`.
2. **Falha descarta o lote.** `evaluation_loop` (`runners.py:121-125`) faz `batch = WriteBatch()` no `except`; o `watchdog_loop` idem. A linha `RESOLVE`/`EXPIRE` do id X se perde; o banco fica com X `active`.
3. **A próxima abertura traz id novo Y** (`collect.py:85-88`) e `write_anomalies` só faz `ON CONFLICT (id)` — o índice único parcial `(market_id, type) WHERE status='active'` rejeita Y. Todo lote que contenha o par falha, para sempre, e **cada lote perdido apaga mais transições e envenena mais pares**.
4. **Sem commit não há ACK** (`persist._ack_all`, depois da transação) → PEL cresce → `consume._read_loop` (`consume.py:174-200`) reclaima o PEL inteiro (páginas de 10, até o cursor voltar a `0-0` ou a página vir vazia) **antes** de cada `XREADGROUP`, e cada mensagem reclamada passa por `SISMEMBER` + `handle` + novo `PendingAck`. A Astra lembra que "~1.700 páginas por volta" é cenário possível, não contagem medida; o que está medido é o ~88×.
5. **Os gatilhos possíveis do primeiro erro** (não distinguidos, logs rotacionados): falha transitória de banco; corrida entre `watchdog_loop` (lote próprio, memória mutada antes do `await`) e `evaluation_loop`; `_drop_invalidated` por baseline que sumiu (`persist.py:133`), que remove as linhas de anomalia depois de a memória avançar (apontado pela Astra).

O boot de 30/09 14:49Z **não** curou: o estado carregado do banco era coerente, mas o processo voltou a envenenar (hipótese: expirações em massa de anomalias com > 4 h logo no arranque, sob a mesma corrida) — **não provado**, a Astra lembra que um único boot não distingue "cura seguida de recaída" de "nunca curou".

## 3. Conserto implementado (menor e seguro; **não** é o conserto completo)

`services/scanner-worker/hunter_scanner_worker/writers.py` — `supersede_orphan_anomalies`, chamada de `write_anomalies` **na mesma transação**: uma linha `active` do mesmo `(mercado, tipo)` que o lote **não menciona** e que é **mais antiga** que a linha ativa que chega é fechada (`status = expired`, `resolved_at` = `detected_at` da nova, `metadata.superseded_by`, `metadata.state` atualizado) e a gravação segue. Além disso o lote é ordenado **fechamentos antes de aberturas** (o índice é checado linha a linha dentro do mesmo `INSERT`). Teste com Postgres real: `services/scanner-worker/tests/test_anomaly_supersede.py` (10 casos; o primeiro reproduz exatamente o erro de produção e **falhou antes**; o de ordem invertida **falha sem o `sorted`**).

Os dois furos que a Astra apontou no desenho original viraram guardas e testes: (a) um lote atrasado carregando X **não** expira um Y mais novo (continua falhando alto — `test_a_late_batch_never_expires_a_newer_episode`); (b) `[X resolved, Y open]` em qualquer ordem mantém X `resolved`.

**Custo medido (plano, sem `ANALYZE`, `BEGIN READ ONLY` na VPS):** o `UPDATE … FROM unnest(…)` usa `Index Scan using uq_anomalies_active_per_market_type` como sonda por linha que chega (custo ~8 por linha; ~200 linhas por flush ≈ 1,6 mil unidades de custo do planejador). É **um UPDATE a mais por flush que traz anomalia ativa**, inclusive nas atualizações de episódios existentes; o tempo real não foi medido sob carga. A Astra revisou o diff final (`APPROVE_WITH_NITS`, nenhum must-fix; ela não executou nada); os dois nits viraram teste (retorno 1/0 e idempotência; `metadata.state.reason`/`resolved_at`; e um lote com **dois ids ativos para o mesmo par continua falhando alto** — a ordenação não o resolve e não deve).

**O que isto não faz:** não impede que o lote seja descartado nem que a memória divirja (a causa); só impede que a divergência vire veto permanente do banco. Não limpa as 585 anomalias zumbis (só cura quando o par reabre). Não recompõe os 14 h de snapshots.

## 4. O que propor (não implementado, ordem de prioridade)

1. **Reter o lote em falha e serializar** (`runners.py`, hoje com 344 linhas — exige extrair o laço de flush para outro módulo): `evaluation_loop` e `watchdog_loop` compartilham **um** lote e **um** lock desde a mutação da memória até o commit; falha → o lote e os ACKs ficam e são repetidos com *backoff*, sem novas transições por cima; falha permanente interrompe o progresso em vez de descartar. É a opção que a Astra prefere ("retenção + serialização; a reconciliação é complementar"). Teste que falha primeiro: rollback → retry com Postgres real, `test_flush_retry.py`.
2. **Limitar o reclaim a uma página por volta** em `hunter_core/events/consume.py` (preservando o cursor e intercalando novas leituras) e **não reclamar entradas que o próprio consumidor segura** — contrato compartilhado por todos os workers; precisa de desenho e do revisor de `hunter_core`. Teste: `packages/core/tests` com PEL de 5.000 entradas ociosas do mesmo consumidor — a primeira volta deve ler novas mensagens depois de no máximo uma página reclamada.
3. **Alarme que veja isto.** O `/ready` e o heartbeat estavam verdes com 14 h sem commit. Sugestão: `hb:scanner:*` ganha `last_commit_at` e a prontidão falha quando `now − last_commit_at` passa de alguns minutos com `dirty > 0`; e o log de `scanner_cycle_failed` passa a resumir a exceção (hoje cada falha escreve dezenas de KB de parâmetros SQL e rotaciona o log do Docker em 30 min — é o que apagou a evidência do primeiro erro).
4. **Sharding como o do `strategy-worker`: não agora.** 200 mercados a ~20 avaliações/s cabem em um núcleo quando a espiral não existe; primeiro restabelecer os commits e medir sem reprocessamento (a Astra concorda).

## 5. Mitigação operacional imediata para o Everton

Estado: o Radar **vivo no Redis** (`radar:scores`, `opp:*`, `rt:radar`) é publicado antes do flush e provavelmente segue atualizando (**não verifiquei a tela**); o que está parado há 14 h é tudo o que é **durável**: `feature_snapshots`, `opportunities`/`opportunity_history`, `anomalies`, o outbox `anomalies.detected`/`opportunities.updated`. O Lab **não** depende disto. Não há perda de dado em curso no stream (margem 78 min e não encolhe).

**Opção recomendada — reiniciar só o `scanner-worker`** (a memória é reconstruída do banco por `_rehydrate`; o PEL de 17 mil é reentregue ao novo consumidor, que o processa em segundos num processo sem espiral):

```bash
ssh hunter-vps 'cd /opt/project-hunter && bash infra/vps/compose.sh restart scanner-worker'
# depois, de 2 em 2 min, três checagens (somente leitura):
ssh hunter-vps 'cd /opt/project-hunter && bash infra/vps/compose.sh exec -T redis redis-cli XINFO GROUPS market.candles.closed </dev/null | paste -sd" " | sed "s/name /\nname /g" | grep "^name scanner"'
ssh hunter-vps 'cd /opt/project-hunter && timeout 20 docker logs --since 3m hunter-scanner-worker-1 2>&1 | grep -c scanner_cycle_failed'
ssh hunter-vps 'cd /opt/project-hunter && bash infra/vps/compose.sh exec -T postgres psql -X -A -U hunter -d hunter -c "select max(ts) from feature_snapshots_2026_10"'
```

- **Risco:** (a) pode **recair** em minutos se o gatilho do primeiro erro ainda existir (não o identifiquei); o sinal é `scanner_cycle_failed` voltar, o `max(ts)` parar e o PEL voltar a crescer — nesse caso é só reiniciar de novo, não piora; (b) ~2 min sem avaliação enquanto o processo sobe e refaz o aquecimento (`baselines_state bootstrapping` já aparece no heartbeat de hoje); (c) a expiração em massa das 585 zumbis > 4 h no primeiro minuto será gravada (é o comportamento do código, e foi o que gerou as 7 expirações de 14:50:26Z de ontem).
- **O que se perde:** nada do que o stream ainda guarda (as pendentes dentro do `MAXLEN` são reentregues); **os 14 h de snapshots/anomalias/oportunidades já estão perdidos** — a reentrega só marca o mercado como sujo e a avaliação lê o estado quente de agora, **não reconstrói minutos antigos** (Astra) — e as mensagens já aparadas do stream não voltam. Qualquer análise que use `feature_snapshots`/`anomalies` de 30/09 13:36Z a 01/10 deve tratar a lacuna como ausente, não como zero.
- **Não fazer:** `XGROUP DESTROY/SETID`, `XTRIM`, `DEL` de chaves, `kill` por nome. Para o conserto de código entrar em produção é preciso o deploy normal (`compose.sh` com o comando completo e as flags de perfil — `.claude/memory/deploy-vps-comando-completo.md`); o reinício sozinho **não** carrega o conserto.

Sem reiniciar: a margem é de 78 min e estável; o scanner continua sem persistir. Não é uma situação segura de deixar por muito mais tempo, mas nada se perde de novo enquanto o stream não girar.

## 6. Texto para o Open Bugs

> **`scanner-worker` não persiste nada desde 30/09 ~13:36Z e vira 2 h de lag no stream (achado em 01/10).** `flush_batch` falha em ~100 % dos ciclos com `uq_anomalies_active_per_market_type` (`writers.write_anomalies` só trata conflito em `id`). A memória esquece o id da anomalia antes do commit (`collect.py:85`, `watchdog.py:115`) e o lote que falha é descartado (`runners.py:121`); o par `(mercado, tipo)` fica com a linha X ativa no banco e o scanner tenta abrir Y — veto permanente do lote inteiro e dos ACKs. O PEL (17 mil) é reclaimado pelo próprio consumidor antes de cada leitura nova (`hunter_core/events/consume.py`), reentregando ~88× o volume e saturando um núcleo. `/ready` e o heartbeat continuam verdes. Gatilho do primeiro erro não identificado (logs rotacionados). Mitigação: `supersede_orphan_anomalies` em `writers.py` (aguarda deploy). Aberto: reter o lote em falha e serializar watchdog × avaliação; limitar o reclaim; alarme de `last_commit_at`. Dono: `services/scanner-worker`, `packages/core`. Nota: [[Scanner-lag-2026-10-01]].

## Fontes

`.claude/state/astra-review-scanner-lag.md` · `services/scanner-worker/hunter_scanner_worker/{runners,persist,writers,collect,watchdog,consumers,main}.py` · `packages/core/hunter_core/events/consume.py` · `docs/design/retencao-e-disco-2026-09-27.md` §history_v2 (descartado como causa) · [[2026-09-27-retencao-de-dados-e-backup]]

## Relacionadas

[[Performance Overview]] · [[Late-delay-do-Lab-diagnostico-2026-10-01]] · [[KB-0087-o-atraso-de-decisao-e-as-tres-correcoes]] · [[KB-0089-o-teto-de-cpu-de-um-processo-so]] · [[2026-10-01-scanner-lag]] · [[07-BUGS/Open Bugs|Open Bugs]] · [[Workers]] · [[Features]] · [[Anomalies]]
