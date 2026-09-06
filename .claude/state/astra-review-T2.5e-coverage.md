## RESUMO

**(a) Sim: aceito a prova standalone com Redis real como evidência do mecanismo.** Ela complementa os testes, mas não comprova a correção operacional do worker com WS real nem que o fix está carregado nos processos. Os números dos 15 minutos são evidência relatada por você; não os reproduzi nesta revisão.

**(b) Não encontrei nova falha funcional no tratamento das pendências válidas.** O mínimo inclui a deque e o resultado de `_pending_get`; sua transferência para `delivered` ocorre sem `await` intermediário. Isso fecha o achado 1. [event_queue.py:256](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:256), [event_queue.py:291](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:291)

**(c) O assert está correto como invariante interno.** A entrada em interrupção estabelece `_broken_since`, e a retomada limpa os dois campos. O log está correto como **retomada detectada**, com as ressalvas abaixo. [coverage.py:367](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:367), [coverage.py:393](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:393)

**Veredito: REQUEST_CHANGES pelos gates objetivos abaixo; concordo com o mecanismo.**

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisão como `code-reviewer`, em modo OPINIÃO.

## TESTES

Executei com sincronização do ambiente, bytecode e cache do pytest desativados:

```text
uv run pytest packages/exchange-adapters/tests/unit/test_event_queue.py packages/exchange-adapters/tests/unit/test_ws_client_states.py services/market-worker/tests/test_tape_coverage.py services/market-worker/tests/test_tape_coverage_backlog.py -q
56 passed in 6.22s

uv run ruff check .
All checks passed!

uv run python infra/scripts/check_file_size.py
error   437 > 350  services/market-worker/hunter_market_worker/coverage.py
error   352 > 350  packages/exchange-adapters/hunter_exchanges/binance/ws.py
error   351 > 350  infra/scripts/seed.py
scanned 352 files; 3 over budget, 0 grandfathered

uv run ruff format --check .
6 files would be reformatted, 857 files already formatted
```

Pyright e prova com WS real não executados.

## MUST-FIX

**MEDIUM — corrigir os gates introduzidos neste diff:**

- Reduzir [coverage.py:1](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:1) de 437 para ≤350 linhas e [ws.py:1](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:1) de 352 para ≤350. Enxugar a documentação extensa deve bastar, sem fragmentar a lógica.
- Formatar a asserção em [test_tape_coverage_backlog.py:219](C:/dev/project-hunter/services/market-worker/tests/test_tape_coverage_backlog.py:219).

**Cenário concreto:** o CI executa esses gates e falha mesmo com os testes verdes. [ci.yml:37](C:/dev/project-hunter/.github/workflows/ci.yml:37)

`seed.py` e os outros cinco arquivos apontados pelo formatador ficam fora desta revisão.

## NICE-TO-HAVE

- **Teste de fluxo:** `exact_equality_hits < total_stamps` prova apenas que houve alguma amostra com backlog, não que igualdade é rara. Também pode falhar legitimamente se todas as amostras pegarem a fila drenada. Eu usaria sincronização explícita para garantir o estado pendente. A verificação final contra `datetime.now()` tampouco prova a margem de 0,5 s em cada stamp. [test_tape_coverage_backlog.py:138](C:/dev/project-hunter/services/market-worker/tests/test_tape_coverage_backlog.py:138), [test_tape_coverage_backlog.py:154](C:/dev/project-hunter/services/market-worker/tests/test_tape_coverage_backlog.py:154)
- **Duração do log:** `frozen_for_s` usa relógio de parede. Um ajuste regressivo pode produzir duração negativa. Monotônico é apropriado **para essa duração diagnóstica**, mantendo timestamps UTC no critério de cobertura. [coverage.py:373](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:373)
- **Significado do log:** ele antecede o `HSET`; se Redis falhar, houve retomada interna, mas não publicação confirmada. Documente essa distinção. [coverage.py:369](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:369), [coverage.py:422](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:422)

## O QUE EU FARIA DIFERENTE

Acrescentaria testes determinísticos para **item antigo em voo + item novo na deque**, igualdade exata no corte e salto do relógio.

Também corrigiria a justificativa do fallback de candle: “nunca cedo demais” não significa conservador neste predicado; timestamp mais tardio facilita liberar cobertura. Uma candle parcial pode representar informação anterior ao fechamento. Isso não demonstrou falha nova no tape de trades, mas a explicação atual generaliza demais. [event_queue.py:89](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:89)

## CONCORDO COM

Concordo com eliminar o teto de contagem, usar o mínimo temporal e bloquear também na igualdade (`<=`). [coverage.py:347](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:347)

A limitação anterior permanece: observar todas as pendências **já aceitas** não prova ausência de eventos antigos que chegarão depois. O standalone não fecha essa fronteira de transporte.

## OBSIDIAN

- **Market Collector** — registrar mecanismo validado, gates pendentes e prova operacional com WS ainda não realizada.
- **Exchange Adapters** — documentar o mínimo incluindo `_pending_get` e esclarecer o fallback de candles.
- **Revisoes-Astra / T2.5e-coverage** — registrar fechamento dos achados anteriores, resultados desta execução e ressalvas do log.