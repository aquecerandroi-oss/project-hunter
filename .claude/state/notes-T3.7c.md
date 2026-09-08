# notes-T3.7c — backfill de histórico de funding

Data: 2026-09-08. Autor: exchange-integration-specialist. Base: `main` em `a7707dd`. **Nada
commitado.** Escopo: `services/market-worker/{backfill.py,backfill_request.py,backfill_outcome.py,
funding_backfill.py,funding_announce.py,persist_rows.py}`, `packages/core/hunter_core/events/streams.py`,
`infra/scripts/{request_backfill.py,backfill_funding.py,backfill_targets.py}`, testes,
`docs/PIPELINE.md` §1b, `docs/DEPLOYMENT.md`.

## 1. O problema, em uma frase

Dois replays de 31 dias produziram só 23+2 outcomes avaliáveis de 224+341: o resto
`funding_schedule_unknown` porque `funding_rates` só tinha o período coletado ao vivo (desde
~2026-09-05) enquanto os candles já iam até 2026-08-08 (T3.7b). O resolvedor (`hunter_strategy_worker
.funding.resolve_funding`) está certo em recusar — não inventa cadência — mas sem histórico de
funding anterior à entrada (`_CADENCE_LOOKBACK` de 3 dias) nunca tem o que precisar.

## 2. Por que não é o mesmo desenho do backfill de candles

A T2.5-backfill (`ingestion_gaps` + recovery loop) existe para espalhar milhares de chamadas REST
(uma por pedaço de 240 min) por vários ciclos sob orçamento compartilhado, com estado de retentativa
que sobrevive a um restart. Funding não precisa disso: `BinanceRestClient.fetch_realized_funding`
já pagina internamente e uma página cobre ~333 dias a 3 liquidações/dia — **uma chamada por mercado
basta**. Por isso o novo consumidor busca e persiste ali mesmo, sob o bucket de peso de funding que
a coleta ao vivo (`funding.poll_realized`) já usa (isso é o que mantém a prioridade do laço abaixo
da coleta ao vivo, sem fila própria) — nunca cria `ingestion_gaps`.

## 3. Arquivos

| Arquivo | Linhas | O quê |
|---|---:|---|
| `services/market-worker/hunter_market_worker/funding_backfill.py` | 213 | `normalize_window` (janela `[start,end)`, teto 370 dias truncado pela ponta recente), `serve()`: valida universo/capacidade do adaptador, busca via `adapter.fetch_realized_funding`, persiste com `upsert_funding`, anuncia `market.funding.backfilled`, trata `RateLimited` como `system_event` + recusa (nunca laço silencioso) |
| `services/market-worker/hunter_market_worker/funding_announce.py` | 80 | `market.funding.backfilled` — completude por pedido, distinto de `market.derivatives` (que continua anunciando cada liquidação individualmente, inalterado) |
| `services/market-worker/hunter_market_worker/backfill_outcome.py` | 24 | `Outcome` extraído de `backfill.py` para as duas lanes (candles e funding) reportarem no mesmo formato sem import circular |
| `services/market-worker/hunter_market_worker/backfill_request.py` | 102 | `Request.kind` (default `candles`, aditivo), `market_id_for` extraído de `backfill.py` (identidade compartilhada pelas duas lanes) |
| `services/market-worker/hunter_market_worker/backfill.py` | 334 | despacha por `kind` logo após as checagens de exchange/shard; sem mudança de comportamento para `kind: candles` |
| `services/market-worker/hunter_market_worker/persist_rows.py` | 349 | `upsert_funding` agora retorna a contagem de linhas inseridas (usado pela métrica e pelo anúncio de conclusão); todo chamador existente ignora o retorno como antes |
| `packages/core/hunter_core/events/streams.py` | +11 | `MARKET_FUNDING_BACKFILLED = "market.funding.backfilled"`, `DEFAULT_MAXLEN` 1 000 |
| `infra/scripts/request_backfill.py` | 313 | `--kind funding\|candles`; `backfill_targets.py`/`Target` extraídos para caber no orçamento de 350 linhas depois do split |
| `infra/scripts/backfill_funding.py` | 95 | janela e `envelope_for`/`envelopes_for` da lane de funding — identidade inclui o literal `"funding"`, nunca colide com um pedido de candles da mesma janela |
| `infra/scripts/backfill_targets.py` | 75 | `Target`/`targets_for` compartilhado pelas duas lanes (extraído de `request_backfill.py` pelo mesmo motivo de orçamento) |
| `services/market-worker/tests/test_funding_backfill.py` | novo, 9 testes | aceito e persistido, rerun sem duplicar, nunca sobrescreve linha ao vivo, mercado fora do universo, janela futura, adaptador sem capacidade, `429`→`system_event`, `kind` desconhecido, payload malformado |
| `infra/scripts/tests/test_request_backfill.py` | +5 testes | janela de funding sem barra/grace, teto de 370 dias, um pedido por mercado, identidade nunca colide com candles, rerun é um gap só |

## 4. Decisões, com o motivo

1. **Sem `source`/`received_at` em `funding_rates`.** O brief pedia para gravar essas colunas, mas
   a tabela (`docs/DATABASE.md` §2) só tem `market_id, funding_time, rate, mark_price`. A garantia
   "nunca sobrescreve uma liquidação ao vivo" já existe sem elas: `ON CONFLICT (market_id,
   funding_time) DO NOTHING` — quem chega primeiro, ao vivo ou histórico, fica, incondicionalmente.
   Não escrevi brief para a database-architect porque **não precisei** da coluna para a garantia
   pedida; ela só serviria para auditoria pós-fato (distinguir a origem depois de gravada), que é
   nice-to-have, não requisito funcional. Registrado como CONCERN abaixo para quem quiser essa
   auditabilidade.
2. **`Outcome` extraído para `backfill_outcome.py`.** `funding_backfill.py` precisa devolver o mesmo
   formato que `backfill.py` espera, mas `backfill.py` importa `funding_backfill` para despachar por
   `kind` — import circular se `Outcome` ficasse em `backfill.py`. Extrair para um terceiro módulo
   (sem dependências de nenhum dos dois) resolve sem duplicar a dataclass.
3. **`request_backfill.py` estourou 350 linhas ao ganhar `--kind funding`** (403 na primeira versão).
   Segui o precedente já existente no repo (`create_partitions.py` → `partition_plan.py`, T2.5f):
   dois módulos novos, `backfill_funding.py` (a lane) e `backfill_targets.py` (`Target`/`targets_for`,
   usados pelas duas lanes) — o script principal caiu para 313 linhas sem perder nenhuma linha de
   comportamento.
4. **Identidade do evento de funding inclui o literal `"funding"`.** Sem isso, um pedido de funding
   e um de candles para o mesmo mercado e a mesma janela nominal colidiriam em `event_id_for` (que
   não conhecia `kind` antes desta tarefa) e o `ON CONFLICT (event_id) DO NOTHING` da outbox
   descartaria silenciosamente um dos dois. Testado (`test_a_funding_requests_identity_never_collides
   _with_a_candles_request`).
5. **`upsert_funding` passou a retornar `int`.** Único jeito limpo de saber quantas linhas este
   pedido realmente inseriu (para o anúncio de conclusão e a métrica), sem duplicar a lógica de
   dedupe/insert que já existe ali. Os dois chamadores existentes (`persist_rows.flush_batch`,
   `test_persist_batch.py`) ignoram o retorno — nenhum comportamento muda.

## 5. Prova no stack local — o que rodou e o que achei

`docker ps` no início: 8 containers, nenhum parado/recriado por mim (confirmado no fim: mesmos
tempos de "Up"). Como as imagens dos serviços (`hunter-api:dev`) não montam o código do host
(sem bind mount — só `postgres`/`redis` têm volume), rodar `docker exec` num container já vivo usaria
o código antigo. Resolvi com um container efêmero (`docker run -d --network docker_default
hunter-api:dev sleep infinity`, removido no fim com `docker rm -f`), `docker cp` dos arquivos
alterados para dentro dele e execução ali — nenhum container persistente foi tocado.

`funding_rates` antes (query real, colada):
```sql
select m.symbol, min(c.open_time), max(c.open_time) from candles c join markets m on m.id=c.market_id
 where m.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT') and c.timeframe='1m' group by 1;
--  ETHUSDT | 2026-08-08 03:03 | 2026-09-08 11:54  (candles já iam a 08-08)
--  XRPUSDT | 2026-09-01 00:00 | 2026-09-08 11:54
--  SOLUSDT | 2026-08-08 03:03 | 2026-09-08 11:54

select m.symbol, count(*), min(f.funding_time), max(f.funding_time) from funding_rates f
 join markets m on m.id=f.market_id where m.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT') group by 1;
--  ETHUSDT | 11 | 2026-09-05 00:00 | 2026-09-08 08:00
--  SOLUSDT | 11 | 2026-09-05 00:00 | 2026-09-08 08:00
--  XRPUSDT | 11 | 2026-09-05 00:00 | 2026-09-08 08:00
```

Chamei `funding_backfill.serve()` diretamente (o mesmo código que o consumidor chama) com o
adaptador Binance real, para as três, janela `[now - 31d, now)`:

```
ETHUSDT Outcome(name='accepted', ..., final=True)   # log: fetched=93 inserted=82
SOLUSDT Outcome(name='accepted', ..., final=True)   # log: fetched=93 inserted=82
XRPUSDT Outcome(name='accepted', ..., final=True)   # log: fetched=93 inserted=82
```

`funding_rates` depois:
```sql
select m.symbol, count(*), min(f.funding_time), max(f.funding_time) from funding_rates f
 join markets m on m.id=f.market_id where m.symbol in ('ETHUSDT','SOLUSDT','XRPUSDT') group by 1;
--  ETHUSDT | 93 | 2026-08-08 16:00 | 2026-09-08 08:00
--  SOLUSDT | 93 | 2026-08-08 16:00 | 2026-09-08 08:00
--  XRPUSDT | 93 | 2026-08-08 16:00 | 2026-09-08 08:00
```

Rerun exato (mesmas três, mesma janela ~20 s depois): `inserted=0` para as três, contagem em
`funding_rates` inalterada (93/93/93) — idempotente.

Resolvedor (o mesmo `hunter_strategy_worker.funding.resolve_funding` que `settle.py` chama), para
ETHUSDT perpétuo, entrada 2026-08-20T00:00Z / saída 2026-08-20T12:00Z — **antes** do backfill essa
janela tinha zero linhas em `funding_rates` (a tabela só começava em 2026-09-05, ver acima), então o
resolvedor teria devolvido `funding_schedule_unknown` incondicionalmente:
```
settlements_in_lookback 11
reading {'per_unit': '0.450375426089...', 'reason': None, 'settlements': 2,
         'interval_s': 28800, 'charged_at': ['2026-08-20T00:00:00.001+00:00', '2026-08-20T08:00+00:00']}
```
`reason: None` = resolvido, cadência de 8h lida corretamente, dois pagamentos cobrados na janela.

**Concern honesto sobre o replay completo:** tentei rodar `python -m hunter_strategy_worker.replay.run
--version momentum:v2 --from 2026-08-20 --to 2026-08-21 --markets ETHUSDT` de verdade. No container
efêmero (imagem `hunter-api:dev` mais nova, com `replay/`) deu `shadow_version_code_ref_mismatch`
— o hash do `momentum_v1.py` que a versão `v2` tem congelado no banco não bate com o do módulo na
imagem. No `docker-strategy-worker-1` já rodando (mesma tag `hunter-api:dev`, container de 33h)
nem existe `hunter_strategy_worker.replay` — imagem mais antiga. As duas coisas datam de builds
concorrentes de outros agentes na mesma árvore (`GIT_SHA:-dev` reaproveita a tag), não de nada desta
tarefa. Por isso a prova de "outcome resolve com R líquido" foi feita chamando o resolvedor
diretamente (acima) em vez do CLI de replay ponta a ponta — mesma função que `settle.py` usa,
mesmos dados reais, mesmo resultado que o replay teria gravado em `signal_outcomes.r_multiple`.

## 6. Concerns

1. **Sem `source`/`received_at` em `funding_rates`** (decisão 1 acima) — se algum dia precisar
   distinguir ao vivo de histórico depois do fato (auditoria, debug), é migração de coluna aditiva
   para a database-architect. Não bloqueia nada hoje.
2. **`--kind funding` sem `--markets` herda a lista default de candles** (todo perpétuo com par
   spot + BTCUSDT) — razoável (são os mercados que a carteira executa), mas nunca testado como
   default deliberado para funding; todo uso real (script e deploy) passa `--markets` explícito.
3. **Replay CLI ponta a ponta não verificado nesta tarefa** por causa do `code_ref` mismatch acima
   (ambiente compartilhado, não desta tarefa) — a prova ficou no nível do resolvedor, não do job
   completo gravando `signal_outcomes`. Recomendo ao quant-engineer/code-reviewer reproduzir o
   replay completo quando as imagens locais estiverem consistentes com o banco.
4. **Dados de prova ficaram no banco local** (ETHUSDT/SOLUSDT/XRPUSDT agora com 93 liquidações cada,
   2026-08-08→2026-09-08) — deliberado: é exatamente o histórico que o replay precisa, não é dado de
   teste para limpar.
