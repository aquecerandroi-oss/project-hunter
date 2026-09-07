# T3.0e — banda de saída do universo spot (D12) e séries por venue

**Data:** 2026-09-07. **Escopo:** `services/market-worker/hunter_market_worker/{spot_universe,
spot_band(novo),universe_repo,heartbeat,persist,backfill,durable}.py`,
`packages/core/hunter_core/observability.py`, `docs/PIPELINE.md` §1d, testes do mesmo serviço.
Sem commit. Sem `.env*`, `infra/migrations/**`, `services/{execution,strategy}-worker/**`,
`packages/core/hunter_core/{admission,strategies,db}/**`, `tests/integration/paper/**`, `apps/**`.

**Astra indisponível até 2026-09-12 (cota)** — nenhuma segunda opinião obtida. D12 já estava
decidida por escrito (`.claude/state/decisions-delegated-2026-09-07.md`); esta entrega implementa
a decisão, não a discute de novo.

---

## 1. A banda (D12), em uma linha

**Admissão não muda uma vírgula; a histerese existe só na saída.** `spot_universe.tradable_symbols`
(admissão, ≥ 50M inclusive, `ACTIVE`, quote `USDT`, fora da blocklist, ticker legível) é exatamente
o que já existia. O que é novo é `spot_band.py`: para cada símbolo **já monitorado**, cada refresh
produz uma observação (`permanence_observation`) e uma contagem durável decide o que fazer com ela
(`resolve_band`):

- `not_trading` (deixou de ser `ACTIVE`, inclusive por ter sumido da listagem), `quote_not_usdt`,
  `blocklisted` → saída **imediata**, sem banda, sem contagem, zerando qualquer contagem em
  andamento;
- ticker ilegível ou `quote_volume_24h < 40.000.000 USDT` (80% do piso) → observação **abaixo**;
  três consecutivas → saída com motivo `below_band_3x`;
- `>= 40.000.000 USDT` → observação **acima**, zera a contagem.

Um símbolo nunca antes monitorado **não** passa por essa função — ele só entra pela admissão cheia
(`tradable_symbols`), nunca por sobreviver a uma banda a que nunca esteve sujeito.

## 2. Onde a contagem durável vive

`mkt:{exchange}:spot:band_state` — um hash Redis, `{symbol: streak}` (`spot_band._band_state_key`,
`_advance_band`). **Por quê Redis e não uma coluna nova:** o brief proibiu migração; `markets` não
tem coluna livre para um contador de série temporal, e `markets.metadata` já é usado com
substituição integral a cada refresh (`upsert_markets`, `write_metadata=True`) para os filtros de
`exchangeInfo` — misturar um contador próprio ali exigiria mudar a semântica de merge daquela coluna
para um propósito que não é dela. Redis já é onde o par leader/snapshot do universo perpétuo vive
(`universe_leader.py`) e a VPS já roda o Redis com `--appendonly yes --appendfsync everysec`
(`infra/vps/docker-compose.prod.yml:48`). A durabilidade que a D12 pede — "sobrevive a restart do
shard 0" — não depende dessa persistência do Redis: o processo que reinicia é o `market-worker`
(shard 0), nunca o Redis, que é um processo/container separado que continua rodando. A prova disso
está em `test_spot_universe.py::test_a_restart_between_the_second_and_third_reading_keeps_the_streak`:
cada chamada usa um `FakeAdapter` novo e nenhuma variável Python sobrevive entre elas — só o
`redis_client`, exatamente como um restart real deixaria.

Um writer só (o coletor spot é dono único do universo spot, `spot.collects_spot`), por isso
`_advance_band` é um `HGET` + `HSET`/`HDEL` simples, sem o script Lua de compare-and-set que o
snapshot do universo perpétuo precisa para vários shards.

## 3. Bug real encontrado pelo TDD: `monitor_by_floor` não zerava `is_monitored` de um símbolo que
saiu de `ACTIVE`

O teste `test_losing_trading_status_removes_immediately_with_no_band` (suspender um par já
monitorado) falhou na primeira versão: `monitor_by_floor` computava `old_monitored`/aplicava ranks
só sobre símbolos com `status == ACTIVE`, então um símbolo suspenso desaparecia da query e nunca
tinha `is_monitored` zerado — a linha ficava com `is_monitored=true` **para sempre**, mesmo a
função devolvendo o símbolo fora de `new_monitored`. Isso não é uma regressão desta tarefa; é um
buraco pré-existente em `monitor_by_floor` (única chamadora: o caminho spot) que a T3.0e expôs ao
exercitar pela primeira vez "sair de `ACTIVE` enquanto ainda listado". Corrigido em
`universe_repo.py::monitor_by_floor`: `old_monitored` agora é lido **antes** de qualquer escrita e
sobre **todo** status, e um `UPDATE ... SET is_monitored=false, monitor_rank=null` roda antes de
reaplicar os ranks — o mesmo padrão que `rank_and_monitor` (perpétuo) já usa. Sem essa correção a
carteira teria lido `is_monitored=true` para um par suspenso indefinidamente.

## 4. `market_spot_dropped_events_total{exchange}` (item 2 do brief)

`run_heartbeat` é compartilhado pelos dois laços e os dois adaptadores respondem
`adapter.code == "binance"` por desenho (T3.0a/b) — exatamente o problema que
`review-T3.0c-T3.0d.md` "Antes do deploy" item 1 registrou para `market_dropped_events_total`.
Série nova (`heartbeat.py` escolhe a série pelo `market_type` recebido), mesmo padrão de
`market_spot_ingestion_gaps`. Teste:
`test_heartbeat.py::test_run_heartbeat_writes_spot_drops_to_the_spot_series_never_the_shared_one`
— prova as duas direções: a série spot sobe, a compartilhada não se move.

## 5. `market_type` nos logs de ingestão (item 3 do brief)

- `persist.py::drain_loop`/`report_losses`: `market_persist_lag`, `market_persist_flush_failed`,
  `market_persist_lag_report_failed`, `market_persist_report_losses_failed`,
  `market_loss_report_deferred` — todos já recebiam `market_type` como parâmetro (T3.0c), só não o
  escreviam no log. Agora escrevem. Teste com `structlog.testing.capture_logs`:
  `test_persistence_contracts.py::test_flush_failure_log_carries_the_market_type`.
- `backfill.py::market_backfill_planned`: literal `MarketType.PERPETUAL.value` — este consumidor só
  planeja histórico de perpétuo hoje (`_market_id` resolve via `load_market_ids` com o default
  `PERPETUAL`; não existe requester de backfill spot). Nomeado mesmo assim, para o operador nunca
  ter de adivinhar. Teste: `test_backfill_consumer.py::test_the_planned_log_line_names_the_product`.

## 6. `market.universe.changed` carrega o motivo da saída (item 1, "evento com o motivo")

`durable.enqueue_universe_changed` ganhou `removed_reasons: dict[str, str] | None = None` —
aditivo, só o caminho spot preenche (o perpétuo cai do top N e nunca teve "motivo" que não fosse
rank). Teste: `test_spot_universe.py::test_the_universe_event_carries_the_removal_reason`.

## 7. Orçamento de 350 linhas

`spot_universe.py` caiu de ~389 (se toda a política de banda tivesse ficado ali) para 259: a
política pura (`permanence_observation`, `resolve_band`, o hash Redis) foi extraída para
`spot_band.py` (168 linhas, novo), no mesmo padrão de `coverage_limits.py`/`heartbeat_events.py`
(T3.0c). `durable.py` e `backfill.py` ficaram exatamente em 350 depois dos acréscimos — comentários
enxugados para caber. `check_file_size.py`: 463 arquivos, 0 acima do orçamento.

## 8. O que NÃO mudou

- Admissão: `tradable_symbols` é byte a byte o que era antes de D12 — só a docstring ganhou uma
  nota apontando para a banda de saída.
- `monitor_rank`, a regra "sem ticker = fora" na admissão, e o hold durável da T3.0 ("sair da
  elegibilidade não encerra gestão") continuam como estavam.
- `market_dropped_events_total` (a série do perpétuo) é lida e nunca escrita pelo caminho spot.

## 9. Ressalva honesta

`spot_band.py` documenta a persistência AOF do Redis da VPS como "segunda linha de defesa", não
como o que garante o restart guarantee — a garantia real é que o Redis é um processo separado do
`market-worker`. Isso está certo para a VPS (`infra/vps/docker-compose.prod.yml`), mas o compose de
dev/CI (`infra/docker/docker-compose.yml`) não liga `--appendonly yes` — se algum dia o Redis do
ambiente de dev também reiniciar junto do market-worker (não é o caso hoje: são containers
separados, um `docker compose restart market-worker` não derruba o Redis), a contagem seria perdida
sem aviso. Registrado, não corrigido, porque não é o cenário que a D12 pede para proteger.
