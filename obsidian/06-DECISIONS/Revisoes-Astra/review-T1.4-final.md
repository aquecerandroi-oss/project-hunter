---
tags: [astra, revisao]
updated: 2026-09-05
fonte: .claude/state/astra-review-review-T1.4-final.md
---

# Revisão da Astra — review-T1.4-final

Parte da [[Mente da Sexta-feira]]. Índice: [[Index|todas as revisões]]. Diálogos relacionados: [[Dialogos/M1|M1]], [[Dialogos/M2|M2]].

**Eu ainda não aprovaria T1.4.** As duas correções anteriores estão corretas, mas encontrei falhas adicionais de freshness, validação e isolamento de erros. Esta revisão foi estática: li o código e os testes, sem executá-los, modificar arquivos, acessar `.env` ou fazer commit.

**Must-fix**

1. **Um preço de trade congelado pode receber o horário novo do bookTicker.**

   Cenário concreto: chega um `aggTrade` às 12:00:00 com preço `100`; esse canal para de entregar trades, mas `bookTicker`, book e mark continuam chegando. Às 12:01:00, a API pode devolver `last_price="100"`, `last_update` próximo de 12:01:00 e `data_quality="ok"`.

   O adaptador guarda preço **e timestamp**, mas passa apenas o preço do cache ao parser: [ws.py:267](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:267). O parser associa esse preço ao timestamp novo do bookTicker: [streams.py:175](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:175). A API usa esse único timestamp para qualificar o ticker e apresentar `last_update`: [services/markets.py:172](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:172), [services/markets.py:196](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:196).

   **Correção:** preservar a origem temporal de `last_price` no contrato produtor→API. A idade das cotações bid/ask não demonstra a atualidade do último preço de trade. A origem atravessa T1.2/T1.3, mas o resultado incorreto é exposto em T1.4.

2. **Timestamp futuro é considerado atual; o instante usado para calcular idade também antecede leituras.**

   Cenário concreto: `deriv.mark_ts="2026-09-05T13:00:00Z"` quando são 12:00:00. Com ticker/book atuais, o mark congelado recebe `quality="ok"`, idade negativa e não torna o agregado stale enquanto a chave existir. A condição verifica apenas `now - ts <= stale_after_s`: [services/markets.py:103](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:103). Heartbeats futuros recebem `alive` pelo mesmo motivo: [system_status.py:39](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:39).

   Há ainda um cenário sem relógio externo errado: a listagem captura `now`, depois aguarda Redis e Postgres. Um componente com 9,9 segundos na captura pode ultrapassar 10 segundos durante uma espera de 200 ms e continuar classificado `ok`. Uma publicação posterior à captura pode produzir idade negativa: [services/markets.py:248](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:248). O SCAN usa igualmente um relógio anterior a toda a varredura: [system_status.py:122](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:122).

   **Correção:** calcular idades com uma referência comum após as leituras necessárias e tratar timestamps além de uma tolerância explícita de clock skew como inválidos. Apenas zerar idade negativa esconderia o defeito.

3. **Uma chave corrompida derruba a listagem inteira; um payload incompleto pode receber `ok`.**

   Cenários concretos:

   - Book contendo JSON textual, MessagePack inválido ou MessagePack de uma lista: `_unpack` não valida o tipo retornado, e `_book_ts` chama `.get` diretamente. Um mercado contaminado derruba `/markets`, inclusive com `limit=1`, porque todos os mercados filtrados são interpretados antes da paginação: [services/markets.py:70](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:70), [services/markets.py:158](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:158), [services/markets.py:249](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:249).
   - Trade com `ts` válido e sem `price`: `KeyError` derruba o detalhe. O descarte atual protege apenas timestamp ausente/inválido: [services/markets.py:323](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:323).
   - Ticker contendo somente `ts`, deriv contendo somente `mark_ts` e book contendo somente `ts`, todos atuais: o agregado pode ser `ok`, com preços nulos e book vazio. Qualidade depende apenas dos timestamps; campos ausentes viram `None` ou listas vazias: [services/markets.py:178](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:178), [services/markets.py:196](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:196), [services/markets.py:307](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:307).

   **Correção:** validar estrutura, campos essenciais e números finitos antes de qualificar o componente; isolar corrupção por componente/mercado e descartar trades inválidos individualmente. Timestamp válido sozinho não comprova dado utilizável.

4. **`before` aceita datetime naive e deixa o fuso do processo alterar a consulta.**

   Cenário concreto: `GET .../candles?before=2026-09-05T12:00:00`. A rota aceita `datetime` sem exigir timezone e o repositório entrega esse valor diretamente ao filtro: [routers/markets.py:98](C:/dev/project-hunter/apps/api/hunter_api/routers/markets.py:98), [repositories/markets.py:242](C:/dev/project-hunter/apps/api/hunter_api/repositories/markets.py:242).

   Conferi o driver instalado: ele aplica `obj.astimezone(utc)` no encoding de TIMESTAMPTZ, interpretando um datetime naive pelo fuso local: [datetime.pyx:222](C:/dev/project-hunter/.venv/Lib/site-packages/asyncpg/pgproto/codecs/datetime.pyx:222). Assim, a mesma requisição pode cortar em 12:00Z num processo UTC e 15:00Z num processo UTC−3.

   **Correção:** exigir datetime aware, retornar 422 para naive e normalizar offsets explícitos para UTC.

5. **Erros do pipeline vazam o nome da chave Redis no log.**

   Cenário concreto: a chave de ticker existe como STRING. `HGETALL` produz `WRONGTYPE`; o cliente Redis acrescenta comando e argumentos à exceção: [client.py:2148](C:/dev/project-hunter/.venv/Lib/site-packages/redis/asyncio/client.py:2148). Essa exceção chega integralmente ao logger: [errors.py:201](C:/dev/project-hunter/apps/api/hunter_api/errors.py:201).

   A redação atual filtra nomes de campos sensíveis, mas não sanitiza o texto de `exception`: [logging.py:20](C:/dev/project-hunter/packages/core/hunter_core/logging.py:20), [logging.py:64](C:/dev/project-hunter/packages/core/hunter_core/logging.py:64).

   **Correção:** traduzir erros esperados do Redis para eventos estruturados sem comando/chave brutos. O corpo HTTP 500 já é genérico; não encontrei evidência de vazamento de credenciais ou valores de ambiente nesses corpos: [errors.py:202](C:/dev/project-hunter/apps/api/hunter_api/errors.py:202).

**Nice-to-have**

- **SCAN percorre a keyspace inteira.** `match="hb:*"` filtra resultados; não cria um índice de prefixo. A API consome o iterador até o fim e faz um `HGETALL` sequencial por resultado: [system_status.py:124](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:124). O iterador instalado continua até cursor zero: [core.py:6377](C:/dev/project-hunter/.venv/Lib/site-packages/redis/commands/core.py:6377). Eu colocaria orçamento de execução e, conforme o volume, um registro explícito de workers. `COUNT` sozinho não limita o trabalho total.

- **Cursor inválido é validado tarde.** `cursor` vazio, malformado ou maior que 64 caracteres produz 422, mas somente depois de buscar e interpretar o universo filtrado: [repositories/markets.py:54](C:/dev/project-hunter/apps/api/hunter_api/repositories/markets.py:54), [services/markets.py:263](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:263). Validaria antes do I/O. Cursor UUID válido fora do conjunto devolve página vazia, comportamento que merece documentação: [services/markets.py:265](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:265).

- **Depth é declarado, mas não imposto pelo leitor.** Não existe parâmetro `depth` na rota de detalhe; o schema fixa `20`, mas o parser aceita qualquer quantidade de níveis: [routers/markets.py:74](C:/dev/project-hunter/apps/api/hunter_api/routers/markets.py:74), [schemas/markets.py:201](C:/dev/project-hunter/apps/api/hunter_api/schemas/markets.py:201), [services/markets.py:309](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:309). O produtor atual corta corretamente em 20: [hot_state.py:82](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:82). Aplicaria a mesma garantia no leitor.

- **Redis indisponível vira 500 genérico.** Não há tradução das falhas nas leituras dos serviços: [services/markets.py:287](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:287), [system_status.py:56](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:56). Preferiria 503 explícito para indisponibilidade da dependência, mantendo distinto o caso de chave ausente.

**O que faria diferente nos testes**

- O teste de `monitored` passa mesmo removendo o filtro: o mercado não monitorado pertence a **outra exchange**, já excluída pela requisição. Também pode passar com lista vazia por usar `all(...)`: [test_markets_api.py:343](C:/dev/project-hunter/apps/api/tests/integration/test_markets_api.py:343). Usaria dois mercados da mesma exchange e verificaria IDs e quantidade.
- O teste de duração do candle fornece ele próprio `close_time` calculado e depois confere a diferença: [test_markets_quality.py:257](C:/dev/project-hunter/apps/api/tests/unit/test_markets_quality.py:257). É tautológico quanto à transformação da API. O teste seguinte, que chama `from_candle`, é útil: [test_markets_quality.py:273](C:/dev/project-hunter/apps/api/tests/unit/test_markets_quality.py:273).
- O teste chamado “rejects a naive” não fornece nenhum datetime naive: [test_system_workers_status.py:57](C:/dev/project-hunter/apps/api/tests/unit/test_system_workers_status.py:57).
- “Expired key” fornece `None`, sem exercitar expiração real: [test_markets_quality.py:179](C:/dev/project-hunter/apps/api/tests/unit/test_markets_quality.py:179).
- O novo teste HTTP de trades usa três elementos. Verifica inversão, mas não distingue cabeça de cauda quando cabem todos no limite de 50. Usaria 60 e exigiria exatamente `60…11`: [test_markets_api.py:397](C:/dev/project-hunter/apps/api/tests/integration/test_markets_api.py:397).

**No que concordo**

- **Correção dos trades confirmada:** produtor usa `LPUSH`; leitor usa `LRANGE 0 49`; parser preserva a ordem: [hot_state.py:116](C:/dev/project-hunter/services/market-worker/hunter_market_worker/hot_state.py:116), [services/markets.py:286](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:286), [services/markets.py:322](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:322).
- **Correção do motivo da degradação confirmada:** `open` e `failed` alimentam `has_open_gap`, independentemente das qualidades individuais. Há teste HTTP persistindo ambos os estados: [repositories/markets.py:198](C:/dev/project-hunter/apps/api/hunter_api/repositories/markets.py:198), [services/markets.py:209](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:209), [test_markets_api.py:298](C:/dev/project-hunter/apps/api/tests/integration/test_markets_api.py:298).
- **Limites HTTP principais estão corretos:** listagem aceita 1–200; candles, 1–1500. Zero, negativos e valores acima desses máximos são rejeitados com 422. Timeframe desconhecido também é rejeitado: [routers/markets.py:59](C:/dev/project-hunter/apps/api/hunter_api/routers/markets.py:59), [repositories/base.py:34](C:/dev/project-hunter/apps/api/hunter_api/repositories/base.py:34), [routers/markets.py:96](C:/dev/project-hunter/apps/api/hunter_api/routers/markets.py:96).
- **Não encontrei key injection via `symbol/exchange/q`:** o detalhe resolve a identidade no banco antes do Redis; a listagem constrói chaves a partir das linhas retornadas; o SCAN usa padrão constante. `q` permite curingas SQL `%` e `_`, ampliando a busca, sem alterar o padrão Redis: [repositories/markets.py:149](C:/dev/project-hunter/apps/api/hunter_api/repositories/markets.py:149), [routers/markets.py:81](C:/dev/project-hunter/apps/api/hunter_api/routers/markets.py:81), [services/markets.py:148](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:148).
- **Não encontrei conversão de Decimal para float no caminho monetário normal.** Redis textual vira `Decimal`, spread usa aritmética Decimal e a serialização produz strings; candles usam `Numeric`: [services/markets.py:52](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:52), [services/markets.py:85](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:85), [schemas/markets.py:77](C:/dev/project-hunter/apps/api/hunter_api/schemas/markets.py:77), [db/base.py:36](C:/dev/project-hunter/packages/core/hunter_core/db/base.py:36).
- **O detalhe reutiliza o mesmo book bruto para timestamp e níveis**, evitando misturar duas versões desse componente: [services/markets.py:287](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:287), [services/markets.py:298](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:298). O pipeline é não transacional, portanto não garante snapshot atômico entre componentes: [services/markets.py:282](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:282).
- **Parsers de timestamps Redis normalizam offsets para UTC e rejeitam naive**, por `ensure_utc`; a lacuna está em `before`: [services/markets.py:65](C:/dev/project-hunter/apps/api/hunter_api/services/markets.py:65), [system_status.py:64](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:64), [types.py:47](C:/dev/project-hunter/packages/core/hunter_core/domain/types.py:47).

Mantenho como decisões encerradas os cinco endpoints aprovados e o adiamento da idade própria de liquidações para M2.