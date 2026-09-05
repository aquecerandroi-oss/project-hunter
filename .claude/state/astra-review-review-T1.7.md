**Eu não fecharia T1.7 ainda.** Há cobertura útil, mas alguns testes passam sem exercer a regressão anunciada. Esta foi uma revisão estática dos arquivos novos do `git status`, incluindo o teste adicional da API; não executei testes nem mutações, não modifiquei arquivos e não li `.env`.

As lacunas abaixo são **da suíte nova**, não uma afirmação de ausência em todos os testes anteriores.

**Testes que passariam com o contrato quebrado**

| Teste | Regressão que ele deixa passar |
|---|---|
| [TTL sem eventos:216](C:/dev/project-hunter/tests/integration/test_market_invariants.py:216) | Escreve um ticker, executa `EXPIRE 5` e verifica `TTL == 5`. **Nenhum ciclo do coalescer roda.** Passaria com o bug de renovar TTL continuamente sem evento novo. |
| [Tempo avançando:442](C:/dev/project-hunter/tests/integration/test_market_invariants.py:442) | Não avança o relógio: altera `ts` diretamente no Redis. Testa reação a um timestamp alterado; passaria se a idade não evoluísse enquanto o timestamp permanecesse igual. |
| [Book parado:301](C:/dev/project-hunter/tests/integration/test_market_invariants.py:301), [mark parado:316](C:/dev/project-hunter/tests/integration/test_market_invariants.py:316), [OI independente:330](C:/dev/project-hunter/tests/integration/test_market_invariants.py:330) | Book/mark **nunca existiram** nesses cenários. Detectam ausência, mas passariam com o bug de rejuvenescer um mark antigo quando chega OI novo, por exemplo. |
| [Recovery atômico:129](C:/dev/project-hunter/tests/integration/test_market_recovery.py:129) | Confere candle e gap depois de `check_gaps`. Passaria se fossem gravados em **duas transações**, deixando uma janela de inconsistência em caso de crash. Mesma chamada não prova mesma transação. |
| [Cinco tentativas:163](C:/dev/project-hunter/tests/integration/test_market_recovery.py:163) | O número de iterações vem de `recovery.MAX_ATTEMPTS`. Alterar o contrato de cinco para quatro ou seis faria o teste acompanhar a implementação e continuar verde. Também não tenta reabrir **antes** do cooldown. |
| [Reconexão com recovery:187](C:/dev/project-hunter/tests/integration/test_market_live.py:187) | Depois do corte, verifica apenas `ws_state == connected`. Passaria com recovery totalmente desativado: não consulta candles ausentes nem `ingestion_gaps`. |
| [Espera por healthy:235](C:/dev/project-hunter/tests/integration/test_market_live.py:235) | `"healthy" in "unhealthy"` é verdadeiro; além disso, `State == running` basta. A espera pode terminar com o container unhealthy. Isso enfraquece ambos os testes operacionais. |
| [Detalhe e busca E2E:93](C:/dev/project-hunter/tests/e2e/markets.spec.ts:93) | Detalhe exige apenas mudança de URL; busca exige apenas listbox visível. Passariam com detalhe vazio ou resultados incorretos. |

Também há asserções insuficientes dentro do pipeline: só existe **um trade**, então inverter `LPUSH` para `RPUSH` não seria detectado; há apenas **um snapshot de book**, então não se prova que níveis antigos desaparecem na substituição. [Trades:181](C:/dev/project-hunter/tests/integration/test_market_pipeline.py:181), [book:204](C:/dev/project-hunter/tests/integration/test_market_pipeline.py:204).

**Cenários do M1 ainda sem prova integrada**

1. **Adapter → worker em execução → gateway WS.** O teste entrega eventos construídos diretamente a `handle_event`; não consome `adapter.stream()`. As mensagens são lidas por Redis Pub/Sub, sem cliente conectado ao gateway. Uma quebra da assinatura/consumo do adapter ou da ponte Redis→WS pode escapar. Isso vale para `rt:market` e `rt:system`. [Dispatch:153](C:/dev/project-hunter/tests/integration/test_market_pipeline.py:153), [Pub/Sub:193](C:/dev/project-hunter/tests/integration/test_market_pipeline.py:193), [heartbeat:311](C:/dev/project-hunter/tests/integration/test_market_pipeline.py:311).

2. **Frescor independente sob tráfego contínuo.** Falta preço/trade congelado enquanto book continua, com asserções de `price_ts`, `book_ts` e idade na API/WS; book ou mark existentes envelhecendo enquanto os demais avançam; expiração efetiva; precedência com condições simultâneas — nenhum dado + gap, gap + stale. O teste chamado `open_or_failed_gap` só insere `failed`. [Contrato:95](C:/dev/project-hunter/docs/plans/M1.md:95), [gap:398](C:/dev/project-hunter/tests/integration/test_market_invariants.py:398).

3. **Recovery adversarial.** Faltam bootstrap sem watermark com corte pelo relógio da exchange; REST atrasado após avanço WS sem alterar Redis; resposta parcialmente completa mantendo pendência; falha entre insert e transição para provar rollback conjunto. O conflito de candle existente está coberto por chamadas diretas a `flush_batch`, mas não pela corrida REST→recovery→WS. [Contrato:92](C:/dev/project-hunter/docs/plans/M1.md:92), [conflito:102](C:/dev/project-hunter/tests/integration/test_market_invariants.py:102).

4. **Liquidações além do replay simples.** Faltam reentrega após perda/expiração do cache, retry após commit incerto, deduplicação pelo consumidor, falha de XADD com métrica/evento e crash entre commit/publicação. O teste de `event_id` chama o publicador diretamente e compara com o mesmo helper de ID; não atravessa persistência→publicação→consumidor nem valida independentemente a canonicalização. [Contrato:93](C:/dev/project-hunter/docs/plans/M1.md:93), [teste:244](C:/dev/project-hunter/tests/integration/test_market_invariants.py:244).

5. **Persistência periódica.** Faltam `open_interest_history` com bucket único por ciclo e funding realizado persistido. O comentário “nenhum snapshot sem hot state” também não tem cenário correspondente: as duas chamadas usam o mercado já aquecido. [Funding estimado:177](C:/dev/project-hunter/tests/integration/test_market_pipeline.py:177), [snapshots:258](C:/dev/project-hunter/tests/integration/test_market_pipeline.py:258).

6. **Supervisão completa.** Há boa prova de exceção do coalescer derrubando `run_market`, watchdog e `/ready`. Faltam retorno **normal** de tarefa permanente, código de saída real do processo, universo vazio→idle, conexão sem evento aceito por 60 s, orçamento de reconexão acumulado entre oscilações e timeout/exceção dos readiness checks. [Contrato:94](C:/dev/project-hunter/docs/plans/M1.md:94), [falha injetada:63](C:/dev/project-hunter/tests/integration/test_market_supervision.py:63), [reconexão única:179](C:/dev/project-hunter/tests/integration/test_market_supervision.py:179).

7. **Universo e rotas Binance.** Falta provar atualização por diferenças, permanência das assinaturas mantidas, remoção por delisting/blocklist e recebimento de payload nas duas rotas. O pipeline faz apenas uma carga de universo com um símbolo. [Contrato:96](C:/dev/project-hunter/docs/plans/M1.md:96), [carga:95](C:/dev/project-hunter/tests/integration/test_market_pipeline.py:95).

8. **Operação por 120 s em todos os mercados.** O live consulta apenas o primeiro ticker encontrado e o candle mais recente global; isso pode passar enquanto quase todo o universo está sem atualização. Não observa progresso durante 120 s. [Ticker:103](C:/dev/project-hunter/tests/integration/test_market_live.py:103), [candle:112](C:/dev/project-hunter/tests/integration/test_market_live.py:112).

**O E2E de staleness precisa ser redesenhado.** Ele corta WS antes da navegação e espera “atrasado”, sem comprovar estado inicial `OK`. Pode passar com dado já atrasado; também pode falhar com produto correto, porque a página mantém refresh HTTP trazendo dados frescos. É necessário fixar o mesmo mercado, comprovar `OK`, interromper/controlar todas as fontes de atualização e observar a transição. [Teste:114](C:/dev/project-hunter/tests/e2e/markets.spec.ts:114), [refresh montado:65](C:/dev/project-hunter/apps/web/app/(app)/[orgSlug]/markets/page.tsx:65), [refresh HTTP:30](C:/dev/project-hunter/apps/web/components/auto-refresh.tsx:30).

**Há testes que eu manteria:** final substituindo parcial e bloqueando parcial posterior; rejeição de parcial antigo/duplicado; conflito preservando o primeiro candle; detecção do buraco interno; leitura da API usando o formato produzido pelo worker. Eles possuem asserções relevantes contra regressões concretas. [Candles:168](C:/dev/project-hunter/tests/integration/test_market_invariants.py:168), [contrato worker/API:138](C:/dev/project-hunter/apps/api/tests/integration/test_t17_market_pipeline_contract.py:138).

Não encontrei, nos materiais T1.7 consultados, a saída vermelho→verde da mutação exigida pelo [brief:12](C:/dev/project-hunter/.claude/state/brief-T1.7-tests.md:12). Portanto, “passaria com o bug” acima é análise das entradas e asserções, não resultado de execução contra código antigo.

## OBSIDIAN

- **Revisoes-Astra/review-T1.7** — Registrar esta revisão, lacunas e testes que não detectam a regressão anunciada.
- **Market Collector** — Separar cobertura integrada comprovada das pendências de recovery, persistência e operação.
- **WebSockets** — Registrar a ausência de prova pelo gateway e corrigir o cenário E2E considerando refresh HTTP.
- **Workers** — Atualizar o estado implementado e distinguir supervisão testada de saída/restart real ainda não comprovados pela T1.7.