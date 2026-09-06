**RESUMO**

**REQUEST_CHANGES.** Concordo com o rebuild, com o cursor tipado e com adiar o `producer` por instância no backfill. Não reportaria a T2.9 inteira como DONE: encontrei três problemas reproduzíveis, além da migração de universo ainda pendente.

**ARQUIVOS**

Nenhum arquivo criado ou modificado. Revisei os arquivos indicados, incluindo os novos ainda não rastreados e as alterações nos três testes existentes relacionados.

**TESTES**

Executei verificações sem sincronização de dependências, bytecode ou cache:

| Comando | Saída real |
|---|---|
| `uv run python infra/scripts/check_file_size.py` | `scanned 258 files; 4 over budget, 0 grandfathered` |
| `uv run ruff check .` | Última execução: `Found 6 errors.` |
| `uv run ruff format --check .` | `12 files would be reformatted, 604 files already formatted` |

Os apontamentos desses gates estão fora dos arquivos da T2.9. O diretório continua recebendo alterações concorrentes; o lint passou de cinco para seis erros entre leituras.

Também executei sondas Python em memória, usando as funções reais e dublês nas fronteiras de IO:

```text
build_envelope import: OK
WHERE (outbox_events.created_at, outbox_events.id)
  > ($1::TIMESTAMP WITH TIME ZONE, $2::BIGINT)

Redis down: two processes admitted 4800 tokens without waiting
No successful health observation, now + 1 day: True
Replay 5001 retained rows, two default calls: 5000, 5000;
unique=5000; last_row_recovered=False
```

Essas sondas não substituem integração com Postgres/Redis. Não executei pytest, pyright nem alterei o stack nesta revisão.

**MUST-FIX**

1. **HIGH — O fallback contraria a decisão conjunta final.**  
   Em [rate_limit.py:176](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/rate_limit.py:176), uma falha do Redis encaminha a admissão para um bucket local, inicialmente cheio em `:205`. Dois processos admitiram 4.800 tokens imediatamente na reprodução. **Cenário:** Redis indisponível, shards continuam REST com cotas independentes e excedem a quota compartilhada.

   A [decisão conjunta M2:251](C:/dev/project-hunter/.claude/state/dialogue-M2.md:251) exige explicitamente **“sem orçamento independente durante indisponibilidade”**. Portanto, não é apenas uma preferência anterior minha: as notas registram um conflito entre brief e aceite. Recomendo suspender novas admissões enquanto a coordenação estiver indisponível, preservando os bloqueios conhecidos.

2. **HIGH — Readiness pode ficar verde indefinidamente sem uma única observação válida.**  
   [outbox.py:140](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:140) retorna `True` quando `last_sweep_at is None`; a proteção contra observação antiga nunca entra nesse caso.

   **Cenário:** desde o boot, consultas à outbox falham — por exemplo, falta de permissão de leitura — enquanto o banco responde ao health check e os produtores conseguem inserir. O dispatcher apenas registra erros e tenta novamente, mas a checagem `outbox` permanece verde. A sonda confirmou `True` mesmo simulando um dia depois. Exigir primeira observação bem-sucedida, ou uma tolerância de startup efetivamente limitada.

3. **MEDIUM — Replay limitado não oferece continuação nem explicita recuperação incompleta.**  
   [outbox.py:265](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:265) limita a recuperação a 5.000 eventos. O cursor existe apenas dentro de [_replay():301](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:301); o retorno contém somente a contagem.

   **Cenário reproduzido:** 5.001 linhas retidas, stream perdido, duas chamadas com o mesmo `since`: ambas republicam as mesmas 5.000; a última continua ausente. Aumentar `limit` permite contornar, mas o contrato operacional precisa indicar truncamento e permitir continuação pelo par `(created_at, id)`. Testar acima do limite e com timestamps empatados.

**Bloqueio de fechamento já conhecido:** [universe.py:139](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:139) committa a composição antes da publicação em `:178`. Se o processo morrer nesse intervalo, o próximo refresh encontra a composição já atualizada e pode não emitir a mudança. As [notas:9](C:/dev/project-hunter/.claude/state/notes-T2.9.md:9) reconhecem isso. Respeitar o arquivo travado foi correto; registrar a dependência não equivale a fechar a durabilidade de todos os produtores.

**NICE-TO-HAVE**

- **Índice:** a correção do cursor não prejudica a indexabilidade. Contudo, o índice existente é parcial sobre `id`, e não sobre `(created_at, id)`; além disso, replay inclui linhas despachadas e não pode depender desse índice parcial. Ver [system.py:148](C:/dev/project-hunter/packages/core/hunter_core/db/models/system.py:148). Avaliar índices de pending e replay separadamente com `EXPLAIN`.
- **Prova operacional:** 9.311 é a contagem acumulada da última amostra, não o total demonstrado durante os 16 minutos. Entre primeira e última amostra, o incremento foi 5.937. Os 15 reconciliados comprovam recuperação de pendências; o log isolado não identifica qual processo as criou nem prova a janela exata da morte. Ver [t29-proof.md:37](C:/dev/project-hunter/.claude/state/t29-proof.md:37).
- **Limite da garantia:** o teste de rollback injeta uma exceção dentro da transação; não prova reentrega da origem WS. Há uma fila em memória antes da persistência, inclusive para liquidações ([ingest.py:199](C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:199)). A documentação não deve prometer reentrega universal antes do commit.
- **Timers:** os novos testes cobrem cooldown de gap e pendência de publicação, não os confirmadores do scanner ([test_recoverable_timers.py:50](C:/dev/project-hunter/services/market-worker/tests/test_recoverable_timers.py:50)). Delimitar isso no relatório.

**O QUE EU FARIA DIFERENTE**

**Dividiria `outbox.py` agora, junto da correção do replay:** extrair `reconcile` e `_replay` para `outbox_recovery.py`, mantendo a reexportação pública. O corte começa em [outbox.py:260](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:260), separa recuperação de despacho contínuo e abre espaço real sem fragmentar artificialmente o código.

A prova de 16 minutos serve como smoke operacional. Antes de declarar resiliência, recomendo **Redis indisponível por 60 segundos com o cliente real**, seguido de recuperação, observando readiness, admissões REST, pendências e efeitos únicos no consumidor. O teste chamado “Redis outage” usa um dublê que lança erro imediatamente ([test_outbox_integration.py:315](C:/dev/project-hunter/packages/core/tests/integration/test_outbox_integration.py:315)); não exercita timeouts, retries e supervisão juntos. Não exigiria repetir um ensaio de 24 horas para esta retomada.

**CONCORDO COM**

1. **Import:** no fonte atual não há correção a fazer. A reexportação existe em [outbox.py:46](C:/dev/project-hunter/packages/core/hunter_core/events/outbox.py:46), e o import executado funcionou. A inspeção histórica da imagem relatada é compatível com imagem obsoleta.
2. **Cursor:** mantenha `literal(..., Coluna.type)`. A compilação real confirmou `TIMESTAMP WITH TIME ZONE` e `BIGINT`, sem cast textual nem função aplicada às colunas ([outbox_store.py:281](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:281)). Não executei `EXPLAIN` ou round-trip com asyncpg nesta rodada.
3. **Producer REST:** concordo em adiar. A identidade usa exchange, símbolo, timeframe e abertura, sem `producer` ([durable.py:72](C:/dev/project-hunter/services/market-worker/hunter_market_worker/durable.py:72)). A perda é de diagnóstico por instância, já explicitada; não justifica bloquear a entrega.
4. **Enqueue em lote:** colocar a publicação durável no caminho compartilhado dos upserts e usar os registros efetivamente inseridos é a decisão correta ([persist_rows.py:140](C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:140)).

**OBSIDIAN**

- **Market Collector** — registrar produtores migrados, exceção do universo e limite da garantia antes do commit.
- **Exchange Adapters** — reconciliar o fallback com o aceite final da M2.
- **Data Flow** — documentar replay, continuação e dependências restantes da T2.9.
- **Open Bugs** — registrar readiness sem primeira observação e recuperação truncada.
- **Revisoes-Astra / T2.9-retomada** — guardar este veredito, reproduções e critérios de fechamento.