# Revisão T3.0e — banda de saída do universo spot (D12), commit `abf8e80`

**Revisor:** Sexta-feira on Hermes, como `code-reviewer` e `risk-engine-guardian`.
**Base:** `main` em `49281c9`. **Commit revisado:** `abf8e80` (diff `999640a..abf8e80`).
**Escopo:** read-only — só este arquivo foi editado. Não commitei, não empurrei, não rodei
testcontainers, não toquei `.env*`.

---

## Bloqueantes

Nenhum bloqueante encontrado. A admissão não mudou uma vírgula, a banda só age na
saída, a contagem é durável, o caminho perpétuo é intacto, e nenhum par abaixo de 50 M
entra por qualquer caminho.

---

## Antes do deploy

1. **A admissão é byte a byte a mesma.** `tradable_symbols` (`spot_universe.py:80-107`)
   não ganhou nem perdeu um caractere — só a docstring ganhou uma nota apontando para a
   banda. O teste `test_a_pair_exactly_on_the_floor_is_in_and_a_cent_below_is_out`
   (`test_spot_universe.py:88`) continua provando `>=` inclusivo, e
   `test_a_pair_between_the_exit_floor_and_the_admission_floor_never_enters`
   (`test_spot_universe.py:346`) prova que 45 M em 3 refreshes nunca entra. Um par com
   < 50 M não entra por streak restoration (a banda só processa `old_monitored`, nunca
   `eligible`), por ticker ilegível (admissão já recusa `ticker is None`), por reordering
   (a banda itera `sorted(old_monitored)`, ordem determinística) ou pelo código de banda
   (`final_monitored = survivors | (eligible - currently_monitored)` — `survivors` são
   já monitorados, `eligible` passa o piso cheio).

2. **`monitor_by_floor` e a janela de `is_monitored = false`.** O reset bulk
   (`universe_repo.py:226-230`) roda dentro da transação `role_session` de
   `refresh_spot_universe`. Em `READ COMMITTED` (o nível do Postgres), um leitor
   concorrente vê o estado pré-commit até o `COMMIT` — o `UPDATE` só é visível depois.
   O caminho perpétuo não chama `monitor_by_floor` (única chamadora é
   `spot_universe.py:173`; `rank_and_monitor` é o caminho perpétuo, `universe_repo.py:248`).
   O spot é single-writer por construção (`collects_spot` = `shard_index == 0 and
   market_spot_enabled`, `spot.py:92`). Não há leitor concorrente do `is_monitored` spot
   que veja o reset intermediário.

3. **Streak Redis e `FLUSHALL`.** Se Redis perde tudo, `hget` retorna `None`, `streak_in
   = 0`, e a próxima observação "below" começa a contagem em 1 — o par precisa de 3
   leituras abaixo novas, não sai imediatamente, não re-entra errado. É conservador
   (mantém o par por mais tempo). Dois processos ambos como shard 0 só acontece com
   config errada — `MARKET_SHARD` particiona por `crc32`, shard 0 é único. A chave
   `mkt:{exchange}:spot:band_state` segue a gramática de `hunter_core.redis.keys`:
   prefixo `mkt:`, venue `{exchange}:spot` (via `_venue(exchange, MarketType.SPOT)` =
   `f"{exchange}:spot"`), sufixo `band_state`. Consistente com `tape_coverage`
   (`mkt:{exchange}:spot:coverage`).

4. **`removed_reasons` é aditivo.** `enqueue_universe_changed` (`durable.py:301-350`)
   só adiciona `removed_reasons` ao payload se truthy (`if removed_reasons`). O
   `event_id` (`universe_event_id`) não inclui `removed_reasons` — continua derivado de
   `(stream, venue, new_monitored, at)`. Consumidores antigos ignoram o campo novo. O
   `market_type` no payload continua dizendo `"perpetual"` para o perpétuo. Id inalterado.

5. **`market_spot_dropped_events_total`.** `heartbeat.py:283-295` escolhe a série por
   `market_type`: spot incrementa `market_spot_dropped_events_total`, perpétuo
   `market_dropped_events_total`. O laço spot incrementa só a série spot. O teste
   `test_run_heartbeat_writes_spot_drops_to_the_spot_series_never_the_shared_one`
   (`test_heartbeat.py:249`) prova as duas direções: spot sobe 5, perpétuo não se move.

6. **`market_type` em logs.** `backfill.py:269` usa literal `MarketType.PERPETUAL.value`
   — verdadeiro hoje (spot não tem requester de backfill). `persist.py` adiciona
   `market_type=market_type.value` em `market_persist_lag` (L219), `market_persist_flush_failed`
   (L236), `market_persist_lag_report_failed` (L222), `market_persist_report_losses_failed`
   (L189) e `market_loss_report_deferred` (L126). Testes:
   `test_flush_failure_log_carries_the_market_type` (`test_persistence_contracts.py:275`)
   e `test_the_planned_log_line_names_the_product` (`test_backfill_consumer.py:190`).

7. **Prova de restart.** `test_a_restart_between_the_second_and_third_reading_keeps_the_streak`
   (`test_spot_universe.py:422`) cria um `_one_pair_adapter` novo a cada chamada — nenhuma
   variável Python sobrevive entre elas, só o `redis_client`. Após a 2ª leitura,
   `hget` retorna `b"1"`; após a 3ª, `b"2"`; após a 4ª (remove), `None`. Prova que a
   contagem vive no Redis, não em memória Python. Isso é durabilidade.

8. **Orçamento de 350 linhas.** `spot_band.py` 168 (novo), `spot_universe.py` 259,
   `universe_repo.py` 283, `heartbeat.py` 346, `persist.py` 254, `backfill.py` 350,
   `durable.py` 350, `observability.py` 194. Todos dentro do orçamento.

---

## Depois

- Verificar `market_spot_dropped_events_total{exchange}` no Prometheus antes de
  considerar o spot estável — é o quarto sinal da §1d do PIPELINE.
- Rodar `check_file_size.py` no CI (timeout local não permitiu, mas `wc -l` confirma
  todos os arquivos dentro do orçamento de 350).
- A ressava honesta das notes-T3.0e §9: o compose de dev/CI não liga `--appendonly yes`
  no Redis. Se o Redis do dev reiniciar junto do market-worker (não é o caso hoje:
  containers separados), a contagem seria perdida sem aviso. Registrado, não corrigido.

---

## STATUS

`git status -sb`: `## main...origin/main`, ` M .claude/settings.json` (pré-existente),
35 untracked (state files e tmp, pré-existentes). Nenhuma mudança além deste arquivo de
revisão.

---

Bloqueia o deploy da VPS: não
A admissão mudou: não
