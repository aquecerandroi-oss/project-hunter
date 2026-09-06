**RESUMO**

**REQUEST_CHANGES. Eu reportaria T2.5 como BLOCKED para aceite, com implementação parcial e prova operacional registrada.** Há requisitos ausentes e falhas de correção; não é apenas desempenho abaixo do alvo.

Duas premissas das notas já não correspondem à árvore atual: **a API lê `vector`** e **também falta o refresh horário das baselines**.

**ARQUIVOS**

Nenhum arquivo criado ou modificado; nenhum commit. Revisão focada nos cinco pontos e nos caminhos de persistência relacionados.

**TESTES**

Não executei testes, lint, migrações nem nova prova operacional nesta revisão somente leitura. Os resultados informados são evidência do seu relato, não uma execução minha.

Conferi o histórico da API com `git log`: o commit `98bcfea` corrigiu o caminho para `feature_snapshot.vector.values`, depois de `5bd17db`.

**MUST-FIX**

**1. Cobertura — HIGH: a margem de 0,5 s não demonstra completude.**

Há dois cenários concretos:

- **Reconexão interna:** o adaptador trata a falha e reconecta sem encerrar o gerador. O tracker, porém, inicia a sessão em `consume_once` e só a quebra no encerramento desse laço. O housekeeping passa apenas `dropped_events`, sem verificar conexão ou geração. Uma desconexão pode, portanto, ficar dentro de um intervalo declarado contínuo. Fontes: [connection.py:194](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:194), [streaming.py:47](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:47), [streaming.py:58](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:58).
- **Fila atrasada sem descarte:** depois de `written()`, o gerador aguarda a próxima entrega por uma task. Nesse intervalo, `_in_flight == 0` pode coexistir com trades antigos ainda na fila. Se o backlog superar 0,5 s, o stamp ultrapassa dados ainda não persistidos. Fontes: [event_queue.py:153](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/event_queue.py:153), [streaming.py:96](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:96), [coverage.py:141](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:141).

**Exigiria participação explícita do adaptador:** geração da conexão/subscrição e um marcador de progresso entregue, confirmado depois da escrita. Expor apenas o tamanho da fila também não basta: há item já retirado pela task, mas ainda não entregue ao consumer. A margem pode ser complementar; não pode ser a prova.

Avaliar em `as_of = covered_until` continua sendo uma escolha correta **quando esse limite é confiável**. Os 179/202 resultados `ok` demonstram que o caminho foi habilitado, não que a cobertura declarada seja verdadeira.

**3. Envelope — HIGH: manter `vector`; remover o rename atual.**

A API atual define `FEATURE_ENVELOPE_PATH = ("vector", "values")`. O scanner retira `vector` e grava `features`. Cenário: oportunidades existem, mas os filtros de volatilidade não encontram seus valores e a ordenação por volume passa a tratar esses valores como ausentes. Fontes: [radar_common.py:65](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar_common.py:65), [rows.py:70](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/rows.py:70).

Concordo com evitar duplicação, mas **não há correção pendente da T2.6 que justifique essa transformação**. Preserve o envelope canônico e teste a leitura da API contra o resultado de `storage_envelope`, incluindo a persistência.

**4. Retenção — HIGH: não aceito o fallback para SELECT simples.**

O diagnóstico do privilégio está correto: o DDL concede `SELECT/INSERT/DELETE`, enquanto o PostgreSQL exige `UPDATE` em pelo menos uma coluna para esse lock. Fontes: [analysis.py:322](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:322), [documentação PostgreSQL 16](https://www.postgresql.org/docs/16/sql-select.html).

O fallback elimina a garantia justamente no cenário que ela precisa cobrir:

1. O scanner verifica que B existe.
2. A retenção verifica que B ainda não tem referência persistida e a apaga.
3. O scanner grava o envelope apontando para B.

Não há FK no JSONB que impeça isso. Fontes: [writers.py:108](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/writers.py:108), [DATABASE.md:1182](C:/dev/project-hunter/docs/DATABASE.md:1182).

**Entre as duas opções, prefiro recusar a partida normal.** Alternativamente, um modo explicitamente limitado a coleta de features poderia continuar, com readiness degradada e sem escrita/publicação dependente de baseline.

Recomendaria uma migração de privilégio mínima, preservando o trigger que rejeita atualizações; não um grant manual. O trigger existente continua protegendo a imutabilidade: [analysis.py:129](C:/dev/project-hunter/infra/migrations/ddl/analysis.py:129).

**4b. Baseline desaparecida — HIGH: a invalidação atual deixa efeitos passar.**

`_drop_invalidated` remove oportunidades e parte do history, mas deixa anomalias, eventos e callbacks. Depois, `flush_batch` grava as anomalias, enfileira os eventos e executa os callbacks. Cenário: a oportunidade é recusada, mas sai `opportunities.updated` para uma alteração não persistida; o marcador de history também pode avançar sem a amostra correspondente. Fontes: [persist.py:112](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:112), [persist.py:148](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/persist.py:148), [scanner.py:271](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:271).

A invalidação precisa abranger **todos os efeitos dependentes da avaliação**, além de retirar a revisão desaparecida da projeção usada na retentativa.

**5. Entrega — HIGH: faltam bootstrap, refresh e acionamento do backfill.**

O `TaskGroup` não agenda processamento de baselines; `_warm` apenas carrega revisões existentes uma vez. O `BackfillRequester` é construído e depois descartado. Fontes: [main.py:104](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:104), [main.py:142](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:142), [main.py:215](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/main.py:215).

Portanto, **“em três dias amadurece” não vale para esta implementação**: numa instalação vazia, acumular snapshots não cria revisões automaticamente. Isso é funcionalidade ausente, expressamente exigida no [brief:10](C:/dev/project-hunter/.claude/state/brief-T2.5-scanner-worker.md:10).

O desempenho também bloqueia o aceite. A prova registra p99 **>21 s**, contra **≤3 s** exigidos no plano. O limite de escopo justifica solicitar uma tarefa de otimização; não transforma o requisito descumprido em preocupação secundária. Fontes: [t25-proof.md:75](C:/dev/project-hunter/.claude/state/t25-proof.md:75), [M2.md:58](C:/dev/project-hunter/docs/plans/M2.md:58).

**Achado adicional — HIGH: falha de commit pode perder snapshot.**

`last_snapshot_minute` avança ao montar o lote, antes do commit. Se a persistência falhar, o runner descarta o lote, mas mantém esse estado. Uma nova avaliação no mesmo minuto não recria o snapshot perdido. Fontes: [scanner.py:206](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/scanner.py:206), [runners.py:99](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/runners.py:99).

É necessário preservar o lote para retentativa ou restaurar/promover os estados conforme o resultado da transação.

**NICE-TO-HAVE**

Ampliar os buckets da latência para quantificar a cauda hoje registrada apenas como `>21 s`.

A validação obrigatória também precisa ser descrita corretamente: o teste atual executa **cinco passadas**, mede duração de ciclo e não inclui persistência/publicação. Não equivale à carga de 60 s nem prova latência ponta a ponta. Fontes: [test_load.py:42](C:/dev/project-hunter/services/scanner-worker/tests/test_load.py:42), [test_load.py:113](C:/dev/project-hunter/services/scanner-worker/tests/test_load.py:113).

**O QUE EU FARIA DIFERENTE**

Reportaria assim:

> **BLOCKED para aceite da T2.5.** Prova de operação registrada, mas bootstrap/refresh/backfill ainda não integrados, latência fora do alvo e correções obrigatórias de cobertura, envelope e persistência. Radar real ainda não demonstrado.

Separaria a otimização do motor numa tarefa com escopo explícito. Manteria a integração dos runners como pendência própria da T2.5. Depois, repetiria a prova com baselines sendo efetivamente produzidas e os cenários de falha corrigidos.

**CONCORDO COM**

**2. Concordo com a assimetria de `covers_from`**, condicionada à continuidade real da coleta e à integridade do buffer: sem truncamento, início da sessão; com truncamento, `max(sessão, mais antigo retido)`. É o que [context.py:127](C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/context.py:127) implementa.

Uma ressalva: tape inteiramente vazio ainda vira `missing`, não zero; a assimetria não altera isso. Fontes: [hotstate.py:224](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:224), [windows.py:170](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:170).

Concordo também com não fabricar oportunidades para preencher o Radar e com evitar duplicar o vetor no envelope.

**OBSIDIAN**

- **Workers** — registrar T2.5 parcial, bloqueios de aceite e runners ainda ausentes.
- **Market Collector** — distinguir cobertura comprovada de margem temporal; registrar reconexão interna e fila.
- **Features (Feature Engine)** — documentar corte temporal, truncamento e limite do tape vazio.
- **Anomalies (Anomaly Engine)** — registrar produção de baselines pendente e proteção contra retenção.
- **Revisões-Astra / T2.5 — revisão do diff** — registrar `REQUEST_CHANGES`, cenários acima e evidências necessárias para fechamento.