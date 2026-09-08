# notes-T3.7d — vez justa no estrato histórico + estado terminal para janela antes da listagem

Data: 2026-09-08. Autor: exchange-integration-specialist. Base: `main` em `57b1152`
(brief pedia `96cb101` ou posterior; `57b1152` é o commit mais recente disponível na
árvore local e já contém o diagnóstico/brief T3.7d). Escopo tocado: `services/market-worker/**`,
`docs/PIPELINE.md` §1b, `docs/DEPLOYMENT.md`. **`packages/core/hunter_core/domain/enums.py`
não foi tocado** — decisão registrada abaixo. Nenhum arquivo em `infra/migrations/**` foi
tocado. Nenhum commit feito.

## Decisão: sem migração, sem mudança em `enums.py`

`ingestion_gaps.status` é `sa.Text()` puro (`infra/migrations/versions/0001_initial_schema.py`
linha 1034), sem `CHECK` — confirmado lendo a migração inteira e `ddl/tables.py` (nenhuma
revisão posterior toca `ingestion_gaps`). Não existe hoje nenhum enum `GapStatus` em
`packages/core/hunter_core/domain/enums.py`; todo o código (`recovery.py`, `recovery_queries.py`,
`recovery_drain.py`, `backfill.py`) usa literais de string (`"open"`, `"failed"`, `"recovered"`).
Como o novo valor `"unrecoverable"` cabe sem migração e não há vocabulário formal a estender,
**não editei `enums.py`** — introduzir um enum agora seria um refactor maior (trocar literais em
quatro módulos e em consumidores fora do escopo desta tarefa, como `apps/api` e
`hunter_strategy_worker`) sem necessidade: o padrão vigente do módulo já é string livre.

## Sinal escolhido para "antes da listagem" (item 1) — e por quê

O brief lista três opções: sonda de candle mais antigo, `onboardDate` de `exchangeInfo`, ou a
resposta vazia numa janela anterior à listagem. Escolhi uma quarta, mais barata que as três:
**o mínimo já persistido em `candles` para aquele mercado** (`recovery_lifecycle.earliest`,
espelho de `watermarks` com `min` no lugar de `max`). Motivo:

- **Custo zero de REST.** `onboardDate` não é parseado por nenhum adaptador hoje (verificado em
  `packages/exchange-adapters/hunter_exchanges/binance/normalize.py`) e `markets` não tem coluna
  para ele — persisti-lo seria migração, fora do escopo. Uma sonda dedicada (`fetch_candles` de
  uma janela larga) custa peso de REST extra por mercado.
- **Já é verdade por construção.** A coleta ao vivo persiste a primeira vela dentro de um ciclo de
  detecção da listagem (ou da entrada no universo monitorado) — é exatamente o que o próprio
  diagnóstico mediu: o candle mais antigo de `MARSCOINUSDT` (`2026-09-01 09:45Z`) já existia horas
  antes das quatro lacunas pré-listagem sequer serem tentadas.
- **Aplicado antes de qualquer fetch.** `recover_one` checa `earliest_known` **antes** de chamar
  `adapter.fetch_candles` — uma lacuna classificada assim nunca gasta uma chamada REST nem uma
  tentativa (`gap.attempts` permanece `0`), diferente do caminho anterior que sempre incrementava
  `attempts` mesmo numa resposta vazia.
- **Limite honesto:** se o mercado ainda não tem nenhuma vela persistida (`earliest_known is None`),
  o sinal não se aplica e o caminho comum `attempts`/`failed`/`exhausted` (item 3) segue sendo o
  backstop que impede o laço infinito de qualquer jeito.

Motivo e classificação são gravados em `system_events` (`event=market_gap_unrecoverable`,
`data={"reason": "before_listing", ...}`) na mesma transação da mudança de status — sem coluna
nova em `ingestion_gaps`.

## Vez justa no estrato histórico (item 2)

`recovery_queries.pending_gaps` não faz mais um `ORDER BY gap_end DESC LIMIT` único sobre o shard
inteiro para o estrato histórico. `recovery_lifecycle.history_candidates` busca, por mercado, até
`MAX_HISTORY_GAPS_PER_CYCLE` linhas via `ROW_NUMBER() OVER (PARTITION BY market_id ORDER BY
gap_end DESC)`, e `backfill_priority.interleave` (função pura, sem sessão) intercala essas filas
em rodízio — um slot por mercado por rodada — até esgotar o orçamento do ciclo. Um mercado sem
mais lacunas é pulado sem desperdiçar o slot; um mercado com backlog maior nunca é impedido de
crescer, só de tomar *todos* os seis slots sozinho.

Não implementei "peso por pedido explícito" (a outra opção do brief): `ingestion_gaps` não guarda
quem originou uma lacuna (decisão deliberada da T2.9c, documentada em `pending_gaps`), e dar peso
a "pedido explícito" exigiria uma coluna nova — migração fora do escopo. O rodízio por mercado
resolve o incidente sem essa coluna.

## `failed` não é mais um laço (item 3)

`recovery_lifecycle.reopen_stale_failed` não zera mais `gap.attempts` ao reabrir — o campo passa a
ser o total acumulado de tentativas em todas as "vidas" da lacuna. `life_count = attempts //
MAX_ATTEMPTS` é ao mesmo tempo essa contagem e "quantas vidas já foram esgotadas". Cada reabertura
espera um cooldown que dobra por vida (`FAILED_RETRY_AFTER_S * 2 ** (life_count - 1)`); depois de
`MAX_REOPEN_ATTEMPTS` (3) reaberturas, a próxima falha vira `unrecoverable` (motivo `exhausted`)
em vez de reabrir de novo — com log e `system_events`.

**Efeito colateral que corrigi para manter a semântica de "5 tentativas por vida":** como
`attempts` deixou de ser zerado, o corte de falha em `recovery_drain.recover_registered` não podia
mais ser `attempts >= MAX_ATTEMPTS` (isso faria a lacuna falhar de novo na primeira tentativa após
qualquer reabertura, porque o total acumulado já é ≥ 5). Troquei para `attempts % MAX_ATTEMPTS ==
0` — falha exatamente no 5º, 10º, 15º... tentativa, dando a cada vida seu próprio orçamento cheio
de 5 tentativas. Confirmado pelos testes que já existiam (`test_partial_finality_...`,
`test_empty_fetch_still_increments_attempts_and_eventually_fails`, ambos de vida única, continuam
passando sem mudança) e por um teste novo, pontual, que fixa esse comportamento (`test_recovery_lifecycle.py`).

Um teste existente teve sua asserção atualizada porque a semântica mudou de propósito:
`test_failed_gap_past_cooldown_is_reopened_and_recovered` esperava `attempts == 1` após uma
reabertura bem-sucedida; agora é `attempts == 6` (5 da vida 1 que falhou + 1 da vida 2 que
recuperou), documentado no próprio teste.

## Heartbeat / métricas

`HeartbeatState.unrecoverable_gaps` (novo campo), escrito no hash `hb:market:{exchange}` (e
`:{i}of{N}` sob sharding) e no gauge `market_ingestion_gaps{status="unrecoverable"}` (mesmo gauge,
label novo — não precisou de métrica nova). `open_gaps` já excluía `unrecoverable` por construção
(`count_by_status(..., "open")` só conta linhas com `status='open'`), sem precisar de mudança ali.

## Arquivos

- `services/market-worker/hunter_market_worker/backfill_priority.py` (novo) — `interleave()`, puro,
  sem sessão, no espírito de `backfill_plan.py`.
- `services/market-worker/hunter_market_worker/recovery_lifecycle.py` (novo) — `earliest()`,
  `history_candidates()`, `reopen_stale_failed()`. Extraído para não estourar o orçamento de 350
  linhas de `recovery_queries.py` (o próprio docstring dele já vivia sob essa disciplina).
- `services/market-worker/hunter_market_worker/recovery_queries.py` — `pending_gaps` delega a
  `history_candidates` para o estrato histórico; `reopen_stale_failed`/`earliest` saíram daqui.
- `services/market-worker/hunter_market_worker/recovery_drain.py` — `recover_registered`/`recover_one`
  ganham `earliest_known`; checagem "antes da listagem" antes de qualquer fetch; corte de falha
  virou `attempts % MAX_ATTEMPTS == 0`.
- `services/market-worker/hunter_market_worker/recovery.py` — lê `market_earliest` uma vez por
  ciclo, passa a cada `recover_one`; chama `recovery_lifecycle.reopen_stale_failed`; grava
  `system_events` para lacunas exauridas; conta e publica `unrecoverable_gaps`.
- `services/market-worker/hunter_market_worker/heartbeat.py` — campo `unrecoverable_gaps` em
  `HeartbeatState` e no hash Redis.
- Testes: `test_recovery_lifecycle.py` (novo, 7 casos puros, sem Postgres), `test_backfill_priority.py`
  (+6 casos: 3 puros de `interleave`, 2 de fairness contra Postgres, mantidos os 14 anteriores),
  `test_recovery_contracts.py` (+4 casos: antes/depois da listagem via `recover_registered`, cenário
  ponta a ponta via `check_gaps`, esgotamento de reabertura; 1 asserção existente ajustada),
  `test_heartbeat.py` (asserção estendida para `unrecoverable_gaps`).
- Docs: `docs/PIPELINE.md` §1b (item 7 reescrito, item 11 novo); `docs/DEPLOYMENT.md` (nota
  "Lendo `unrecoverable_gaps`" com as duas queries de leitura, dentro de "Profundidade de histórico
  para o β").

## Verificado, fora do escopo de edição (não tocado)

- `apps/api/hunter_api/repositories/markets.py` já filtra `status.in_(("open","failed"))`/`status
  == "open"` — `unrecoverable` já sai das contagens da API sem mudança nenhuma lá.
- `services/strategy-worker/hunter_strategy_worker/gaps.py` (censura de outcome) só considera
  `_CONSIDERED = ("open", "failed")`; uma lacuna `unrecoverable` cobrindo um minuto cai no ramo
  "nada cobrindo o minuto" — tratado exatamente como "a exchange não tinha candle ali", que é a
  semântica correta e já documentada para esse módulo. Nenhuma mudança necessária.

## Testes (saída real, `uv run pytest`, um arquivo por invocação)

Ver bloco TESTS do relatório final.

## Concerns

1. Ordenar por `market_id` dentro de `history_candidates` é uma escolha arbitrária mas
   determinística — não é "o mercado mais antigo pedido primeiro"; se o time quiser priorizar por
   idade do pedido/mercado dentro do rodízio, dá para trocar a ordenação externa sem tocar
   `interleave`.
2. `MAX_REOPEN_ATTEMPTS = 3` e o cooldown que dobra (1h, 2h, 4h) são escolhas conservadoras do meu
   lado, coerentes com o "(say 3)" do brief — não medidas contra produção; se 3 reaberturas
   provarem ser poucas para uma falha genuinamente transitória e demorada, o número é um só lugar
   para mudar (`recovery_lifecycle.MAX_REOPEN_ATTEMPTS`).
3. Não implementei "peso por pedido explícito" no estrato histórico (a alternativa ao rodízio que o
   brief também citava) porque exigiria uma coluna de origem em `ingestion_gaps` — deliberadamente
   ausente desde a T2.9c. Documentado como decisão, não como pendência.
