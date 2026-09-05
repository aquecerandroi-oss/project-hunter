**Eu não aprovaria T1.3 como concluída.** Há falhas funcionais além dos bloqueios já reconhecidos no [relatório](/C:/dev/project-hunter/services/market-worker/T1.3-report.md:1). Não demonstrei nenhum CRITICAL; os principais achados são HIGH.

Fiz revisão estática, sem executar testes, criar/modificar arquivos, ler `.env` ou fazer commit. Os “73 passed” são evidência histórica do [relatório](/C:/dev/project-hunter/services/market-worker/T1.3-report.md:53), não uma execução desta revisão.

Uma correção de contagem: a seção indicada contém **12 itens**, nas [linhas 15–26 da checklist](/C:/dev/project-hunter/.claude/state/review-T1.3.md:15). Abaixo sigo essa ordem.

**1. Checklist, item por item — lacuna, prova e cenário**

1. **Bootstrap e candles finais — MEDIUM: confundo histórico indisponível com perda de ingestão.**  
   O bootstrap calcula `start = end - MINUTE * 1499` e registra todas as aberturas ausentes, sem considerar quando o mercado começou a existir: [recovery.py:149](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:149).  
   **Cenário:** um perpétuo listado há duas horas entrega todas as suas velas disponíveis. As horas anteriores à listagem continuam sendo exigidas; após cinco tentativas, o gap vira `failed`: [recovery.py:129](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:129). O mercado ganha uma pendência impossível de recuperar.  
   O filtro de finais e `ON CONFLICT ... DO NOTHING` estão presentes: [persist_rows.py:73](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:73). A paginação existe no adapter: [rest.py:169](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/rest.py:169).

2. **Lista Redis de candles — HIGH: parciais reais são rejeitados.**  
   O worker faz `getattr(candle, "ts", None)` e retorna `False` para parcial sem esse atributo: [hot_state.py:130](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:130). O tipo normalizado oferece **`event_ts`**, não `ts`: [market.py:268](/C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:268). Além disso, o parser WS não preenche esse campo: [streams.py:236](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:236).  
   **Cenário:** chegam duas atualizações válidas da vela aberta; ambas são descartadas. Mesmo corrigindo apenas o parser para preencher `event_ts`, o worker continuará rejeitando-as.  
   **Outra lacuna, MEDIUM:** com timestamp fornecido, um final com timestamp igual ao último parcial também é rejeitado por `not _newer(...)`: [hot_state.py:144](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:144). Nesse cenário, a precedência de final sobre parcial não é respeitada.

3. **Gaps internos e recuperação — MEDIUM: não garanto a varredura a cada minuto.**  
   A recuperação percorre mercados e gaps sequencialmente, aguardando cada REST dentro da transação: [recovery.py:152](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:152). O loop só volta a verificar o relógio depois de concluir tudo: [recovery.py:188](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:188).  
   **Cenário:** 200 mercados precisam de backfill e cada chamada leva um segundo; apenas as chamadas já consomem mais de três minutos. Buracos novos deixam de ser detectados na cadência contratada. Uma chamada presa bloqueia os mercados seguintes.  
   A confirmação de cobertura e a transação conjunta estão implementadas: [recovery.py:126](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:126).

4. **Filas limitadas e descarte observável — HIGH: o limite não cobre o pipeline real.**  
   Antes da fila limitada do worker existe `asyncio.Queue()` sem limite no adapter: [ws.py:139](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:139). Os leitores usam `queue.put_nowait(event)`: [ws.py:287](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:287).  
   **Cenário:** Redis fica lento enquanto WS continua recebendo. O consumidor desacelera, mas os leitores acumulam eventos sem limites de itens, bytes ou idade; o processo pode esgotar memória antes de a política de descarte do worker agir.

   **HIGH adicional:** `report_losses(...)` e o registro de `persistence_lag` ficam fora do `try` de retry: [persist.py:80](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:80), [persist.py:110](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:110).  
   **Cenário:** há um descarte e Postgres está indisponível. A tentativa de registrar a perda levanta exceção, derruba a tarefa e cancela o grupo; liquidações ainda em memória são perdidas. O próprio mecanismo de observabilidade impede o retry.

5. **Snapshots/OI em buckets e escrita em lote — HIGH: o caminho de produção insere um registro por round-trip.**  
   `flush_batch` usa `for snapshot ... await session.execute(...)`, repetindo o padrão para OI: [persist_rows.py:150](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:150). O flush inteiro tem timeout de dez segundos: [persist.py:115](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:115).  
   **Cenário:** um lote com 200 snapshots e latência de 60 ms por execução precisa de pelo menos 12 segundos. A transação é cancelada antes do commit, repete o mesmo trabalho e acaba descartada por idade.  
   Os buckets são preservados no objeto pendente; isso não compensa a ausência de inserção em lote.

6. **Deduplicação de liquidações — MEDIUM: não conto duplicatas detectadas.**  
   O insert termina em `ON CONFLICT (id, ts) DO NOTHING` seguido de `await session.execute(stmt)`, sem obter quantidade inserida ou incrementar contador de duplicatas: [persist_rows.py:131](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:131).  
   **Cenário:** uma sobreposição WS reentrega milhares de liquidações. O histórico fica único, mas a tempestade de duplicatas permanece invisível e consome fila/DB/publicação. Cada item do lote ainda é publicado: [persist.py:131](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:131).  
   UUID5 delimitado e normalização decimal existem: [publication.py:29](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/publication.py:29). Não encontrei no README a ressalva exigida de que eventos reais com a mesma tupla colapsam: [README.md:25](/C:/dev/project-hunter/services/market-worker/README.md:25).

7. **Publicação de liquidações depois do commit — sem desvio funcional adicional demonstrado.**  
   A publicação ocorre depois do flush, usa UUID determinístico e registra falha detectada de publicação: [persist.py:115](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist.py:115), [ingest.py:239](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:239), [publication.py:54](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/publication.py:54).  
   A perda na morte entre commit e XADD é uma limitação **explicitamente aceita**, não a classifico como bug: [M1.md:65](/C:/dev/project-hunter/docs/plans/M1.md:65). A validação exigida dessa morte e da deduplicação pelo consumidor continua sem prova nos testes examinados.

8. **Supervisão de tarefas filhas — HIGH: leitores reais escapam do grupo.**  
   O worker envolve suas tarefas com `forever`: [main.py:79](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/main.py:79). Entretanto, o adapter cria leitores com `ensure_future`; seu consumidor apenas espera a fila: [ws.py:151](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:151), [ws.py:162](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:162).  
   **Cenário:** um leitor termina por exceção fora do tratamento interno. A exceção não chega imediatamente ao TaskGroup; o consumidor continua esperando enquanto o processo permanece vivo. Detecção posterior pelo watchdog não cumpre supervisão fatal imediata.

9. **Watchdog por conexão — HIGH: duplicatas contam como progresso e o restart afeta conexões saudáveis.**  
   O watchdog usa `last_data_event_monotonic`: [supervision.py:121](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/supervision.py:121). O adapter renova esse valor para todo frame reconhecido, antes de qualquer rejeição do worker: [ws.py:274](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:274).  
   **Cenário:** a conexão entrega repetidamente o mesmo book. O hot state rejeita a duplicata, mas o watchdog vê progresso e nunca reinicia a conexão.

   Na ausência de `restart_connection`, o fallback é `restart_stream = True`: [supervision.py:132](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/supervision.py:132).  
   **Cenário:** public silencia e market continua saudável. O worker encerra o stream inteiro, cujo fechamento cancela todos os leitores: [streaming.py:40](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:40), [ws.py:298](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:298). Isso diverge da checklist, embora o relatório reconheça um fallback autorizado pelo brief: [T1.3-report.md:102](/C:/dev/project-hunter/services/market-worker/T1.3-report.md:102).

10. **Readiness — HIGH: renovo saúde antes de saber se aceitei o evento.**  
    `health.data_event()` executa antes de `accepted = await handle_event(...)`: [streaming.py:66](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:66).  
    **Cenário:** só chegam duplicatas rejeitadas. `last_data` continua avançando, e `/ready` pode permanecer positivo mesmo sem progresso aceito.

    **MEDIUM adicional:** no primeiro `connecting`, sem nenhum dado, a readiness retorna verdadeiro durante os primeiros 15 segundos: [supervision.py:68](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/supervision.py:68).  
    **Cenário:** a primeira conexão está pendente; DB e Redis respondem, e o processo pode anunciar prontidão antes de receber qualquer evento. O timeout de dois segundos dos hooks existe: [runtime.py:122](/C:/dev/project-hunter/packages/core/hunter_core/runtime.py:122).

11. **Coalescer e frescor independente — HIGH: republico campos congelados com timestamp novo.**  
    `reset` limpa contadores e `dirty`, preservando preço/bid/ask; `on_book` marca o acumulador como sujo e avança seu único `ts`: [ingest.py:98](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:98). O payload inclui novamente todos esses campos: [ingest.py:118](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:118).  
    **Cenário:** ticker e trades param, mas book continua. O worker publica o preço antigo com timestamp do book recente, sem indicar a idade própria do preço.  
    A independência de `mark_ts` e `oi_ts` no hash Redis está implementada: [hot_state.py:181](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:181).

12. **Universo incremental — HIGH: a primeira mudança real derruba o worker.**  
    O código exige `update_subscriptions` e levanta `RuntimeError` quando ausente: [streaming.py:50](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:50). O `BinanceAdapter` atual não oferece esse método: [__init__.py:71](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/__init__.py:71).  
    **Cenário:** SOL entra no top N e outro símbolo sai; a atualização do universo provoca saída fatal, em vez de alterar somente as assinaturas afetadas.

**2. Outros bugs que um revisor hostil encontraria**

- **HIGH — funding realizado não funciona com Binance.**  
  Sem `fetch_realized_funding`, o worker registra warning e executa `await asyncio.Event().wait()`: [funding.py:71](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/funding.py:71).  
  **Cenário:** ocorre um settlement durante operação normal; nenhuma taxa realizada entra por esse produtor, que ficou estacionado permanentemente. A linha T1.3 exige esse histórico: [M1.md:28](/C:/dev/project-hunter/docs/plans/M1.md:28).

- **HIGH — snapshots transformam mark antigo em observação atual.**  
  O snapshot recebe `snapshot_ts` atual e copia `mark_price` sem consultar `mark_ts`: [sampling.py:94](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:94).  
  **Cenário:** mark para, mas OI continua renovando o TTL compartilhado. O mesmo mark antigo é gravado em sucessivos minutos, sem timestamp de origem ou qualidade que permita distinguir a ausência de atualização.

- **HIGH — campos opcionais antigos sobrevivem com frescor novo.**  
  `_mapping` omite `None`, mas `_hash` usa `HSET`, sem remover os campos omitidos: [hot_state.py:29](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:29), [hot_state.py:50](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:50).  
  **Cenário:** um ticker contém volume; o seguinte tem volume desconhecido. O volume anterior permanece no hash com o `ts` novo do ticker. O consumidor interpreta um valor antigo como atual.

- **MEDIUM — `spread_pct` tem unidade errada no snapshot.**  
  `_spread_pct` retorna `(ask - bid) / mid`: [sampling.py:57](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:57). O domínio retorna essa razão multiplicada por 100: [market.py:176](/C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:176).  
  **Cenário:** bid 99 e ask 101 produzem `0.02` no histórico e `2` no domínio. Um consumidor que compara percentuais subestima o spread histórico em cem vezes.

- **MEDIUM — polling deriva e pula buckets.**  
  O loop dorme 300 segundos e só então percorre os símbolos sequencialmente: [sampling.py:146](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:146).  
  **Cenário:** uma rodada demora dois minutos. Cada mercado passa a ser consultado aproximadamente a cada sete minutos; alinhar a amostra ao bucket de cinco minutos não recupera os buckets pulados.

**3. Testes verdes que não sustentam o aceite**

Não considero todo mock um problema. Estes são os pontos em que o teste pode continuar verde apesar de uma falha concreta:

- **HIGH — parciais:** o teste injeta `event_ts=` diretamente em `push_candle`, contornando parser e dispatcher: [test_contracts.py:76](/C:/dev/project-hunter/services/market-worker/tests/test_contracts.py:76). Passa mesmo quando todas as parciais reais são rejeitadas.
- **HIGH — assinaturas incrementais:** o teste usa um fake cujo método apenas registra argumentos: [fakes.py:63](/C:/dev/project-hunter/services/market-worker/tests/fakes.py:63). Verifica a lista de chamadas: [test_ingest_integration.py:176](/C:/dev/project-hunter/services/market-worker/tests/test_ingest_integration.py:176). Passa sem provar subscribe/unsubscribe real ou continuidade dos símbolos mantidos.
- **HIGH — funding:** o teste cria uma subclasse que oferece justamente o método ausente no adapter real: [test_funding.py:34](/C:/dev/project-hunter/services/market-worker/tests/test_funding.py:34). Passa enquanto o produtor de produção espera indefinidamente.
- **HIGH — supervisão:** o teste substitui ingestão e demais loops por funções que esperam, e faz o coalescer artificial levantar exceção: [test_supervision.py:128](/C:/dev/project-hunter/services/market-worker/tests/test_supervision.py:128). Prova o TaskGroup externo, mas não detecta leitor privado morto.
- **HIGH — frescor:** o teste de coalescência verifica apenas um trade seguido de flush ocioso: [test_contracts.py:62](/C:/dev/project-hunter/services/market-worker/tests/test_contracts.py:62). Passa se book novo republicar preço congelado.
- **HIGH — opcionais:** o teste escreve ticker com campos ausentes em chave inicialmente vazia: [test_hot_state.py:34](/C:/dev/project-hunter/services/market-worker/tests/test_hot_state.py:34). Não testa a transição “valor conhecido → desconhecido”, que mantém o valor antigo.
- **MEDIUM — bootstrap:** o fake devolve a lista inteira, ignorando paginação e limites: [fakes.py:54](/C:/dev/project-hunter/services/market-worker/tests/fakes.py:54). O teste de 1500 candles não cobre listagem recente nem respostas paginadas incompletas: [test_recovery_contracts.py:36](/C:/dev/project-hunter/services/market-worker/tests/test_recovery_contracts.py:36).
- **MEDIUM — timeout inicial:** o teste só consulta readiness aos 16 segundos: [test_supervision.py:155](/C:/dev/project-hunter/services/market-worker/tests/test_supervision.py:155). Não percebe que ela ficou verdadeira antes disso, sem dados.
- **MEDIUM — buckets:** duas chamadas diretas a `flush_batch` com os mesmos objetos provam idempotência, não cadência dos produtores: [test_persistence_contracts.py:105](/C:/dev/project-hunter/services/market-worker/tests/test_persistence_contracts.py:105). O polling de sete minutos descrito acima passa nesse teste.

Não encontrei espera arbitrária por segundos usada como prova nos testes do worker. O `sleep(0)` encontrado apenas cede execução antes do cancelamento: [test_supervision.py:36](/C:/dev/project-hunter/services/market-worker/tests/test_supervision.py:36). Também não confundiria o teste de retry com mock vazio: ele chama o flush original antes de simular resposta de commit perdida, o que é uma verificação útil: [test_persistence_contracts.py:146](/C:/dev/project-hunter/services/market-worker/tests/test_persistence_contracts.py:146).

**4. Float, datetime naive, print e disco**

- **Float chegando a NUMERIC:** não identifiquei um caminho concreto nos produtores examinados. Snapshots convertem texto com `Decimal`: [sampling.py:42](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/sampling.py:42); candles/liquidações usam campos normalizados diretamente: [persist_rows.py:61](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/persist_rows.py:61). Há float em controle de tempo e em `timestamp()` para identidade, mas isso não é valor financeiro enviado a NUMERIC: [publication.py:34](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/publication.py:34).
- **Datetime naive persistido:** não identifiquei caminho concreto. Os tipos normalizados validam UTC e `utcnow()` usa `datetime.now(UTC)`: [market.py:119](/C:/dev/project-hunter/packages/core/hunter_core/domain/market.py:119), [types.py:42](/C:/dev/project-hunter/packages/core/hunter_core/domain/types.py:42).
- **`print` ou estado persistente local:** não encontrei no worker/runtime/settings examinados. Os buffers identificados são memória, não disco: [queues.py:131](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/queues.py:131), [ingest.py:75](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:75).

**5. O que eu faria diferente**

Eu começaria pelo contrato executável entre worker e adapter: `event_ts`, funding realizado, alterações incrementais, restart individual e propagação de falhas. Essas capacidades precisariam ser testadas com o **adapter concreto**, substituindo somente transporte externo.

Depois corrigiria aceitação antes de progresso, timestamps por campo no coalescer, tratamento de opcionais desconhecidos e snapshots com frescor verificável. Fecharia limites desde a entrada WS até a persistência, faria inserts realmente em lote e impediria falhas no registro de perdas de escapar do retry.

Por fim, acrescentaria os cenários adversariais descritos acima e os aceites ainda sem prova: consumidor além da retenção, deduplicação no consumidor e morte entre commit/XADD. Manteria essa última perda como limitação documentada do M1, conforme a decisão conjunta.