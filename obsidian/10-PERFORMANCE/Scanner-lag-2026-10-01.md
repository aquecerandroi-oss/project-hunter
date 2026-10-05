---
tags: [performance, scanner, radar, redis-streams, diagnostico, persistencia, incidente]
updated: 2026-10-05
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

## 7. Segunda parada: 02/10/2026 10:12Z (diagnosticada em 05/10, só leitura)

> **Veredito em quatro linhas.** (1) O `scanner-worker` parou de persistir em **02/10 ~10:12Z** (~21,5 h depois do deploy `9622f087` que levou o `supersede_orphan_anomalies`) e só voltou com o reboot da VPS em 05/10 14:35Z. (2) **Foi o mesmo mecanismo da primeira parada, agora no outro índice único:** 726 das 728 falhas do log retido são `UniqueViolationError` em `uq_opportunities_open_per_market` (`writers.py:256`, `write_opportunities`). (3) A mitigação das anomalias **disparou em todo ciclo** (726 `scanner_anomalies_superseded`) mas dentro da transação que depois falhava nas oportunidades — rollback, **zero** linha com `superseded_by` no banco; o veto das oportunidades nunca esteve no desenho do conserto. (4) **O primeiro erro de 02/10 10:12Z não é recuperável** (logs rotacionados, nenhuma série de heartbeat); o gatilho mais plausível é uma exceção qualquer no ciclo (falha de flush ou `TimeoutError` do Redis dentro de `advance`) que faz o laço descartar um lote cujas transições a memória já aplicou — **hipótese, não prova**.

### 7.1 Evidência durável (comandos de leitura; `BEGIN READ ONLY` no Postgres)

```text
feature_snapshots_2026_10 por hora   02/10 09h 12.005 · 10h 2.587 (último ts 10:12:00Z) · nada até 05/10 14h 1.252 (reboot 14:35Z) · 15h 600 (200/min)
última escrita de oportunidades      10 linhas com last_updated_at = 10:12:00.958588Z (mesmo `now` do ciclo)
última anomalia fechada              expired 10:12:11.701Z · resolved até 10:06 · detected 10h: 204 linhas (até 10:12)
anomalies com metadata.superseded_by 0 em toda a vida do banco  (a mitigação nunca persistiu nada)
anomalies active hoje                313 (min detected_at 11/09); opportunities abertas hoje 185 (121 NORMAL + 64 ANOMALY)
pós-reboot                           44 oportunidades-zumbi (first_seen 02/10 07:26–10:04, last_updated 10:12) expiradas às 14:53–14:56Z; 409 anomalias expiradas às 14:54Z
```

- **O log do contêiner `scanner` sobreviveu ao reboot** (contêiner criado 01/10 12:37:33Z, não recriado; `RestartCount=1`, `OOMKilled=false`): retido de **04/10 07:05:38Z a 09:15:13Z** (a VPS congelou ~09:15Z; último registro do journal do boot anterior 11:15:08 CEST). Nesse trecho: **728 `scanner_cycle_failed`** — **726** `asyncpg.exceptions.UniqueViolationError` com frames `runners.py:109 evaluation_loop` → `persist.py:174 flush_batch` → `writers.py:256 write_opportunities`, `DETAIL: Key (market_id)=(…) already exists.`; **2** `redis.exceptions.TimeoutError` dentro de `scanner.advance` → `context.py:160 build_market_context` (04/10 08:02:15Z e 09:00:54Z — o tipo de falha que descarta um lote **sem** nenhum erro de banco) — e **726 `scanner_anomalies_superseded`** (`closed` 136 no primeiro).
- **Postgres** (log retido só desde 04/10 06:15:45Z): 1.004 `duplicate key … uq_opportunities_open_per_market` e 332 `canceling statement due to statement timeout` (a amostra que li era uma consulta de `meme_tokens`; **não** investiguei as demais).
- **Sem OOM, disco ou IO:** `journalctl -b -1` com 0 ocorrências de `out of memory`/`oom-kill`/`Killed process`; no kernel de 12:05–12:20 CEST (10:05–10:20Z) só eventos de bridge/veth de um contêiner reiniciado às 12:06:17 CEST (não identificado pelo nome) e ruído de firewall. O `dmesg` atual é só do boot novo.
- **Mercado:** o `market-worker` registrou `ws_state_changed connected -> reconnecting` às 10:08:38Z (reconectou em 11 s) — pouco antes da parada, **sem** lacuna nos snapshots (200 por minuto até 10:11). Não estabeleci relação.
- **Retenção de baselines descartada como gatilho:** `feature_baselines` ainda guarda do dia 06/09 em diante (2,6 M linhas; não achei executor de retenção no código, só o protocolo em `docs/DATABASE.md` §17.2) — então `_drop_invalidated` (`persist.py:123`) não pode ter sido o primeiro gatilho de 02/10.
- **Redis agora:** `scanner-worker.market.candles.closed consumers 111 pending 1586 lag 0` (15:07Z de 05/10).
- **Sem série histórica de saúde:** `worker_heartbeats` guarda uma linha por worker (o scanner não tem linha hoje), `hb:scanner:*` expira em 30 s e `system_events` não tem evento do scanner. É a lacuna que o alarme de §7.3 fecha.

### 7.2 O mecanismo (igual ao de §2, em `opportunities`)

`collect_opportunity` (`collect.py:166-170`) esquece `opportunity_id` no `EXPIRE` antes do commit; qualquer exceção no ciclo faz `evaluation_loop` executar `batch = WriteBatch()` e a linha `EXPIRE` do episódio X se perde; o episódio Y seguinte do mesmo mercado viola `UNIQUE (market_id) WHERE expired_at IS NULL` **para sempre**, e cada lote perdido envenena mais mercados. A Astra confirmou o mecanismo e **não achou caminho normal** que gere Y antes do fechamento de X no mesmo lote (`dedupe` preserva a posição; `collect.py:136`).

**Latente, achado pela Astra (sem falha prévia):** `_drop_invalidated` remove a linha `EXPIRE` de X e seu evento depois de a memória esquecer X e a transação **termina bem**; uma avaliação posterior abre Y com X ainda aberto. Hoje não tem produtor (nada deleta baselines), mas reter o lote só no `except` **não basta** — a invalidação precisa restaurar o estado especulativo do mercado.

### 7.3 O alarme implementado (05/10, sem commit)

- **`/ready` ganha `scanner_persistence`** (`health.py`): vermelho quando os ciclos **falham há mais de 120 s (`MAX_FAILING_S`) sem um commit real no meio**. Commit real = `flush_batch` que **escreveu linhas** (`not batch.empty`); flush vazio ou só de ACKs **não** limpa nem inicia o relógio. A primeira versão (relógio "idade da avaliação mais antiga não commitada", limpo por qualquer flush) tinha esse furo e a Astra o apontou com cenário concreto: o lote com dados falha e é descartado; o ciclo seguinte não tem mercado devido, `flush_batch` retorna sem transação e zerava o alarme a cada ciclo quieto. Teste: `test_commit_alarm.py::test_an_empty_flush_after_a_lost_batch_does_not_clear_the_alarm` (**falha** se o commit voltar a ser incondicional — verificado por mutação).
- **Por que não "dirty > 0 e sem commit":** `dirty` oscila entre 0 e ~200 de instante a instante; um alarme sobre ele pisca verde entre as sondas do Docker. O relógio de falhas só depende de o ciclo ter falhado.
- **N = 120 s:** a falha se repete a cada ~1,25 s (1 s de espera + `cycle_s`), então 120 s são ~100 falhas seguidas — mais que um reinício/failover do Postgres, que o laço sobrevive; com o healthcheck (`interval 15 s`, `retries 5`) o contêiner vira `unhealthy` ~3 min depois da primeira falha. A Astra lembra que 120 s é ponto de partida, não distribuição medida: calibrar pela série `failing_for_s`.
- **Heartbeat `hb:scanner:*`** ganha `last_commit_at` (vazio = nenhum neste processo, nunca um horário inventado), `failing_for_s`, `commit_failures` (sequência) e `commit_failures_total` (lotes descartados desde o início — o contador de perda, que continua subindo mesmo com commits no meio).
- **`scanner_cycle_failed` agora é uma linha curta** (`failure_summary.py`): `error_type`, `root_type`, `message`, `constraint`, `detail` (só a chave `Key (cols)=(uuids)` de violação única) e os 3 últimos frames do projeto — nunca o SQL nem um parâmetro. Lista de permissão (Astra): mensagem do servidor só para as classes SQLSTATE `08/23/40/53/55/57`; a classe `22` e as demais viram frase fixa; `Failing row contains (…)` nunca sai. Os laços do watchdog e do regime usam o mesmo resumo.

### 7.4 O que **não** foi feito e o teste que falha hoje

> **Atualização (05/10, noite): a cura entrou em código — ver §8.** O texto abaixo é o registro do que se sabia antes dela; o `xfail` virou teste que passa.

A cura é a **retenção do lote com um único dono da sequência mutação → persistência** (avaliação e watchdog), mais o tratamento explícito da invalidação de baseline (Astra: "um lock só ao redor do SQL chega tarde — a identidade já foi esquecida"; `take()/restore()` só serve se preservar linhas, eventos com os mesmos ids, ACKs, callbacks, a precedência do lote antigo e o estado para desfazer avaliações invalidadas). `runners.py` está em **348** linhas: extrair o laço de flush para outro módulo faz parte do trabalho. Reidratar a memória do banco depois de falha é **complementar**, não rollback completo (o `_rehydrate` apenas dá `continue` quando não acha episódio). Supersede de oportunidades no writer: **não** como conserto principal — a expiração teria de gerar também o evento `opportunities.updated`, que nasce na coleta.

**Teste que falha hoje** (xfail estrito, `services/scanner-worker/tests/test_batch_retention.py`): o mercado A coleta o `EXPIRE` do episódio X e esquece o episódio; o mercado B levanta `TimeoutError` (Redis); depois da recuperação do laço a linha de X **nunca chega ao flush**. Visto falhar pela razão certa com `--runxfail` (`assert UUID(...0a) in []`); no dia em que a retenção entrar, o teste "falha por passar". Regressões que a Astra pede junto: baseline some durante `EXPIRE(X)` (nenhuma memória livre para Y com X aberto) e, com Postgres real, rollback → retry (`test_flush_retry.py`).

**Acompanhamento sem custo de código, até a cura:** alertar externamente em `commit_failures_total` crescendo e em `last_commit_at` mais velho que 3 min com `dirty > 0` (o alarme de `/ready` cobre só a sequência de **falhas**, não "nada para gravar por muito tempo").

Revisão da Astra: [[2026-10-05-scanner-parada-0210]].

## 8. A cura: reter o lote com um único dono (05/10/2026, sem commit, não implantada)

> **Em quatro linhas.** (1) `FlushLane` (`flush_lane.py`) é o lote único e o `asyncio.Lock` que avaliação e watchdog seguram **do primeiro mutar até o fim do flush**; um flush que falha **mantém o lote inteiro** (linhas, eventos com os mesmos `event_id`, ACKs, callbacks, na ordem de coleta) e o repete. (2) Limite de retenção: **60 s** de falha ininterrupta → a lane **bloqueia**: `/ready` vermelho na hora, uma linha CRITICAL `scanner_flush_blocked`, a avaliação e o watchdog **param de coletar** e a lane segue tentando a cada 5 s. **Nada é descartado em silêncio.** (3) Falhas do watchdog (flush e varredura) agora alimentam `scanner_persistence`. (4) A revisão da Astra (`REQUEST_CHANGES`, 5 bloqueadores) foi absorvida e cada correção foi **vista falhar por mutação**.

### 8.1 Desenho

- **Por que lock no ciclo todo e não `take()/restore()`:** `Scanner.advance` recebe o lote antes dos `await` de leitura do Redis e só coleta depois; trocar o lote no meio faria a coleta cair num lote já em voo (perda silenciosa). Com o lock, ninguém apenda durante um flush e não há o que fundir; o custo é o watchdog esperar até um ciclo (a varredura é de 60 em 60 s). A Astra concordou ("manteria o lock amplo").
- **Por que pausar em vez de descartar depois de N tentativas (escolha):** descartar perde exatamente o `EXPIRE`/`RESOLVE` que evita a próxima violação única — reabriria o veto de 30/09 e 02/10. Isolar o mercado venenoso por bissecção pode separar fechamento, abertura, histórico e evento do mesmo mercado. Pausar é o único limite que **não cria divergência**; o preço é que um lote determinísticamente envenenado também para o Radar ao vivo e o `features.updated` (publicado no laço) até alguém reiniciar, e **reiniciar abandona o lote em memória** (o novo processo reidrata do banco): é recuperação com possível perda de trabalho, e a linha CRITICAL diz isso. Antes: perda silenciosa e veto eterno; agora: parada barulhenta com o lote preservado enquanto a falha for transitória.
- **O limite (60 s):** um lote retido cresce até ~200 linhas de snapshot por segundo (o mesmo minuto é refeito até commitar), então 60 s são ~12 mil linhas, dezenas de MB. É verificado **na próxima falha**, não por temporizador independente (tentativas a cada ≤ 5 s).
- **`_drop_invalidated` (baseline sumida sem exceção):** o lote agora lembra os mercados que esvaziou (`WriteBatch.invalidated`), e a lane guarda a obrigação de recarregar a memória do banco (`rehydrate.resync_invalidated`) **antes de qualquer nova mutação** — no começo do ciclo de avaliação e da varredura do watchdog — e só solta os ids depois de o reload dar certo. Sem isso, um `EXPIRE(X)` descartado deixava a memória livre para abrir Y com X aberto no banco.
- **Regime:** `run_regime_once` só expõe o id do novo `market_regimes` depois do commit dele (uma oportunidade que cita regime inexistente é recusada pela FK e, com lote retido, seguraria a lane inteira).
- **Toque velho do watchdog:** `touch_episodes` só atualiza uma linha que **não seja mais nova** (`last_updated_at <=` o do toque). Os toques são aplicados depois das oportunidades e um lote retido pode carregar um toque coletado antes de uma avaliação que já mudou o episódio (`HOT`, `EXPIRED`).
- **ACKs:** com a lane bloqueada, ACKs novos não entram no lote (não passam à frente da avaliação que anunciam). **E o livro de ACKs é deduplicado** (revisão de código, 05/10, HIGH): ver §8.3, a amplificação.
- **Reidratação do universo (mercado que entra):** continua não destrutiva (`authoritative=False`): o reload de um mercado novo roda fora do lock, e apagar o episódio ausente apagaria um `OPEN(Y)` já coletado. Só o resync (sob o lock) é autoritativo.
- **Extração para o limite de 350 linhas:** `cycle_health.py` (CycleHealth, de `health.py`), `evaluation_cycle.py` (o laço de avaliar, de `runners.py`, sem mudar comportamento), `rehydrate.py`; `runners.writer_tasks` cria a lane compartilhada (`main.py` fica em 348).

### 8.2 Evidência de teste (todos locais, sem Docker)

`test_flush_lane.py` (9) e `test_flush_lane_recovery.py` (7), `test_batch_retention.py` (o `xfail` estrito de §7.4, agora passa) e `test_commit_alarm.py`. **Mutações que falham** (executadas): descartar o lote na falha (5 testes caem); não fazer resync / resync depois da avaliação (3); watchdog sem lock; não pausar bloqueado; esquecer a invalidação na falha; remover a guarda do toque; ACKs com a lane bloqueada.

**Não verificado:** `test_flush_retry.py` (rollback → retry com o índice único real, e o toque velho contra Postgres) está escrito e **não rodou** — o Docker não existe nesta máquina e a VPS é só leitura. A suíte do scanner: ver o relatório.

### 8.3 A amplificação que a cura reabria, e o que a limita (revisão de código de 05/10)

**O achado.** Com a lane bloqueada (ou com o flush falhando), os ACKs deixam de sair, a lista pendente (PEL) do Redis cresce, o consumidor faz `XAUTOCLAIM` das **próprias** entradas ociosas (≥ 30 s) antes de cada leitura nova e `handle` (`main.py`) anexava **mais um** `PendingAck` por reentrega: a espiral de ~88× medida em 01/10 (15,9 M entregas para ~170 mil mensagens), agora **na memória** e sem teto. A versão antiga, que descartava o lote, tinha teto. Cada mensagem reentregue só volta a cada ≥ 30 s (a reclamação zera o tempo ocioso), mas o livro crescia uma entrada por entrega.

**O que limita agora (três camadas):**
1. **Livro deduplicado.** `ScannerState.pending_acks` é um dicionário por `(stream, group, message_id)` (`hold_ack`/`take_acks`) e `WriteBatch.add_acks` não guarda a mesma mensagem duas vezes: o tamanho acompanha a PEL (≤ ~50 mil, o `MAXLEN` do stream), não o número de entregas. Teste: 50 reentregas da mesma `message_id` ⇒ 1 entrada; e, com o flush falhando por ~2 s e a mesma mensagem reentregue a cada ciclo, o lote termina com 1 ACK.
2. **Reclaim em páginas por rodada** (`packages/core/hunter_core/events/consume.py`, contrato compartilhado): no máximo `MAX_CLAIM_PAGES_PER_ROUND = 5` páginas de `XAUTOCLAIM` antes de cada leitura, **cursor persistente entre rodadas**, e leitura **sem bloqueio** enquanto sobra backlog (recuperar a lista de uma instância morta não fica lento num stream ocioso). Uma lista pequena cabe numa rodada e é recuperada como antes (todos os 1.423 testes unitários do core e os testes de consumidores do market/strategy-worker seguem verdes). As funções de decodificação foram extraídas para `consume_decode.py` (o arquivo estava em 350 linhas).
3. **Teto de retenção que também conta falhas de avaliação** (ver §8.4).

**O que não foi feito (pedido "de preferência"):** *não reclamar mensagens que o próprio consumidor já segura*. O `XAUTOCLAIM` do Redis não filtra pelo dono: toma e zera o ocioso de qualquer entrada ≥ `min-idle`, inclusive as do mesmo consumidor; excluir as próprias exigiria `XPENDING` por consumidor, outro desenho. Com o livro deduplicado a reentrega é idempotente e, com o orçamento por rodada, deixou de monopolizar o laço.

### 8.4 Dois furos do mesmo review, fechados

- **Falhas de avaliação contam para o limite de 60 s** (`FlushLane.failed`): uma avaliação que levanta a cada ciclo depois de coletar linhas nunca chegava ao flush, e o lote retido crescia sem bloquear. Agora `evaluation_loop` e `watchdog_loop` registram a falha pela lane (o resync que falha também). Teste: avaliação que levanta com o relógio de retenção vencido ⇒ lane bloqueada, `/ready` vermelho, linhas coletadas preservadas.
- **Lane vazia encerra a falha:** o retorno antecipado de `flush()` com lote e ACKs vazios agora limpa `blocked`, `retained_since` e a sequência de falhas (`CycleHealth.recovered`). Com a retenção, "vazio" quer dizer "nada retido, nada em risco" (antes, com o descarte, vazio podia esconder perda). Teste incluído. O comentário velho de `health.py` ("batches discarded") foi corrigido.

### 8.5 O que continua aberto (escrito, não resolvido)

- **Transição de regime perdida:** se o flush da abertura de um regime falha, o id deixa de vazar, mas o classificador já avançou: o próximo minuto não vê `changed` e a linha do novo regime só nasce na próxima troca (dado de pesquisa incompleto; sem veto).
- **Reidratação do universo fora do lock:** um mercado que entra pode ser avaliado antes de seu reload terminar (pré-existente, mercado novo é raro).
- **ACKs pendentes em memória** crescem sem limite enquanto bloqueado (dezenas de bytes por mensagem; reiniciar resolve).
- **Falha pós-commit** (callbacks) repete um lote já commitado: seguro para snapshots, anomalias, oportunidades, histórico e outbox (chaves únicas / `event_id`), mas a Astra lembra que isso vale para o **mesmo** conteúdo — por isso nada é apendado entre tentativas.
- Segunda rodada da Astra **não** foi pedida depois das correções; cada uma tem teste que falha sem ela.

## Fontes

`.claude/state/astra-review-scanner-lag.md` · `services/scanner-worker/hunter_scanner_worker/{runners,persist,writers,collect,watchdog,consumers,main}.py` · `packages/core/hunter_core/events/consume.py` · `docs/design/retencao-e-disco-2026-09-27.md` §history_v2 (descartado como causa) · [[2026-09-27-retencao-de-dados-e-backup]]

## Relacionadas

[[Performance Overview]] · [[Late-delay-do-Lab-diagnostico-2026-10-01]] · [[KB-0087-o-atraso-de-decisao-e-as-tres-correcoes]] · [[KB-0089-o-teto-de-cpu-de-um-processo-so]] · [[2026-10-01-scanner-lag]] · [[2026-10-05-scanner-parada-0210]] · [[07-BUGS/Open Bugs|Open Bugs]] · [[Workers]] · [[Features]] · [[Anomalies]]
