**RESUMO**

**APPROVE**, para esta rodada da T2.5-backfill. Os três must-fix fecham. Aceito o `try-lock`. **Ainda existem caminhos de `partial` indefinido**; a aprovação não significa garantia de conclusão do histórico.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Respeitei os três diretórios excluídos.

**TESTES**

Executei sem sincronização do ambiente, bytecode, cache do pytest ou carregamento automático de plugins:

```text
uv run pytest services/market-worker/tests/test_backfill_plan.py -q
22 passed, 1 warning in 2.75s
```

O aviso foi `Unknown config option: asyncio_mode`, decorrente dos plugins desabilitados. Não reexecutei integração, lint ou pyright; os resultados informados por você permanecem evidência relatada.

**MUST-FIX**

Nenhum pendente dos três anteriores:

- **MF1 fechado.** O recorte recente fica em `clamped_minutes`, separado do truncamento definitivo; entra em `left_out`, que controla tanto `partial` quanto `final`. [backfill_plan.py:183](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_plan.py:183), [backfill.py:262](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill.py:262).
- **MF2 fechado.** O prazo considera o início do ciclo e envolve `recover_one` inteiro. O cancelamento externo não é capturado pelos `except Exception` internos; a escrita está em contexto transacional. [recovery.py:112](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:112), [recovery.py:208](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:208), [recovery_drain.py:157](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_drain.py:157).
- **MF3 fechado.** Os dois locks usam o mesmo namespace/chave. `report_losses` só consulta cobertura e escreve depois de adquirir o lock; se falhar, retorna antes da drenagem. **Isso preserva a exclusão mútua exigida**, embora não garanta atendimento imediato. [recovery_queries.py:144](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:144), [recovery_queries.py:265](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:265), [persist.py:117](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:117).

**NICE-TO-HAVE**

- Completar MF1 com republicação efetiva do mesmo ID após avançar o relógio: o teste atual verifica apenas a primeira passagem. [test_backfill_consumer.py:662](C:/dev/project-hunter/services/market-worker/tests/test_backfill_consumer.py:662).
- Injetar cancelamento durante a escrita para provar rollback de alterações já iniciadas; o teste atual interrompe o fetch, antes dessa transação. [test_backfill_priority.py:226](C:/dev/project-hunter/services/market-worker/tests/test_backfill_priority.py:226).
- Ajustar a documentação restante: ainda promete proteção de prontidão pela aritmética de 240 e descreve os três escritores usando lock bloqueante. [backfill_plan.py:52](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill_plan.py:52), [PIPELINE.md:64](C:/dev/project-hunter/docs/PIPELINE.md:64), [PIPELINE.md:68](C:/dev/project-hunter/docs/PIPELINE.md:68).

**O QUE EU FARIA DIFERENTE**

Registraria explicitamente estes caminhos de **`partial` sem conclusão**, condicionados à republicação:

1. **Partição antiga nunca provisionada:** os minutos continuam bloqueados, mesmo depois de recuperar a parte armazenável. [backfill.py:231](C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill.py:231).
2. **Fonte permanentemente vazia:** o gap alterna entre tentativas, `failed` e reabertura; suas lacunas continuam bloqueando o pedido. [recovery_drain.py:118](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_drain.py:118), [recovery_queries.py:161](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:161).
3. **Falta persistente de orçamento:** vivo consome as vagas ou o tempo. Mesmo havendo 10 s históricos por ciclo, uma unidade que sempre precisa de 12 s pode ser cancelada repetidamente, sem gastar tentativa; a ordenação fixa pode recolocá-la à frente. [recovery_queries.py:210](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery_queries.py:210), [recovery.py:193](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:193).

São limites de progresso a acompanhar, não motivos para reabrir estes três must-fix.

**CONCORDO COM**

O `try-lock` é adequado para esse escritor best-effort. A ressalva é que “fica enfileirado” não significa retenção ilimitada: o deque de perdas é limitado e pode sofrer evicção durante contenção prolongada. Isso não reintroduz a duplicidade de MF3. [queues.py:166](C:/dev/project-hunter/services/market-worker/hunter_market_worker/queues.py:166).

**OBSIDIAN**

- **Market Collector** — registrar fechamento dos três must-fix e funcionamento do `try-lock`.
- **Workers** — documentar os cenários de histórico sem progresso.
- **Data Flow** — distinguir planejamento definitivo de recuperação concluída.
- **Revisões da Astra — T2.5-backfill** — registrar APPROVE da rodada 2, validação executada e ressalvas.