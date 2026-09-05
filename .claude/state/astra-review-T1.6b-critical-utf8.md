**RESUMO**

**Sim: UTF-8 estrito é a correção certa. Concordo com CRITICAL e bloqueio do M1 sem o conserto.** O problema também atinge `N=1`: o hash é calculado antes de `universe.set()`, e a exceção impede a inicialização. Se já existia um universo, ele permanece antigo; a exceção não o esvazia. Referências: [universe.py:85](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:85), [universe.py:246](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:246).

Encontrei **mais duas incompatibilidades concretas com os símbolos chineses**: autorização do WS da API e comparação de URL no E2E.

Minha recomendação anterior de ASCII estava errada, registrada em [t16b-sharding.md:31](C:/dev/project-hunter/obsidian/06-DECISIONS/Revisoes-Astra/t16b-sharding.md:31). Assumo essa correção.

**ARQUIVOS**

Nenhum criado ou modificado por mim. Revisei o diff existente de `universe.py` e `test_universe_sharding.py`, além dos caminhos consumidores.

**TESTES**

Não executei pytest nem a prova operacional. O resultado vermelho/verde dos testes e os números da Binance/Postgres são evidências fornecidas por você.

Executei duas reproduções **em memória**, sem arquivos:

- Node: comparação usada pelo E2E contra uma URL construída com cada símbolo. Nos quatro casos: `currentE2eMatches:false`, `decodedPathMatches:true`.
- PowerShell/.NET: gramática extraída de `channels.py`. Resultado: `BTCUSDT=True`; os quatro símbolos chineses `False`. Isso verifica a expressão, não substitui o teste Python do endpoint.

Os testes adicionados cobrem preservação no modo solo e partição completa, sem sobreposição, para `N=1..4`: [test_universe_sharding.py:84](C:/dev/project-hunter/services/market-worker/tests/test_universe_sharding.py:84).

**MUST-FIX**

1. **CRITICAL — aplicar o hotfix UTF-8 antes de aprovar a coleta.**  
   Cenário: um símbolo chinês entra no universo global; cada processo tenta codificá-lo antes de decidir a propriedade do shard; todos falham, inclusive processos que não seriam seus proprietários. No startup, a ingestão fica esperando um universo que nunca chega: [universe.py:246](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:246), [streaming.py:133](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:133). O diff atual corrige essa causa.

2. **HIGH — permitir símbolos Unicode válidos nos canais de mercado da API.**  
   [channels.py:37](C:/dev/project-hunter/apps/api/hunter_api/realtime/channels.py:37) aceita somente `[A-Za-z0-9._-]` no símbolo. Cenário: o cliente solicita `rt:market:binance:牛来USDT`; recebe `forbidden_channel`, sem assinatura, embora o worker publique esse canal: [endpoint.py:287](C:/dev/project-hunter/apps/api/hunter_api/realtime/endpoint.py:287), [coalesce.py:173](C:/dev/project-hunter/services/market-worker/hunter_market_worker/coalesce.py:173).  
   Corrigiria a gramática mantendo limites, segmentos e bloqueio de curingas/controles. Não basta trocar a expressão inteira por `.*`.

3. **MEDIUM — corrigir a comparação de URL do E2E.**  
   [markets.spec.ts:96](C:/dev/project-hunter/tests/e2e/markets.spec.ts:96) compara o símbolo literal com a URL; o link usa `encodeURIComponent`: [market-row.tsx:59](C:/dev/project-hunter/apps/web/components/markets/market-row.tsx:59). Cenário: a primeira linha selecionada tem símbolo chinês; a navegação funciona, mas o teste termina por timeout. Usaria um predicado que compare os segmentos decodificados com os valores esperados. É defeito do teste, não evidência de falha da página.

**NICE-TO-HAVE**

Acrescentaria uma regressão em `run_universe`, com universo misto, provando que ele inicializa e disponibiliza todos os símbolos esperados. Os testes atuais exercitam somente a função de particionamento: [test_universe_sharding.py:84](C:/dev/project-hunter/services/market-worker/tests/test_universe_sharding.py:84).

Também fixaria vetores conhecidos de proprietário para símbolos ASCII e Unicode. Isso protege o contrato entre processos contra futuras alterações de hash/normalização; cobertura e disjunção, sozinhas, não fixam esse contrato.

Nos demais caminhos solicitados, **não identifiquei outra quebra causada pelos quatro símbolos**, por inspeção:

| Caminho | Evidência |
|---|---|
| WS Binance | `lower()` preserva os ideogramas; nomes seguem para o cliente `websockets`: [streams.py:111](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:111), [connection.py:49](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/connection.py:49). A dependência instalada percent-encoda a query Unicode: [uri.py:95](C:/dev/project-hunter/.venv/Lib/site-packages/websockets/uri.py:95). |
| SUBSCRIBE incremental | Usa JSON, sem conversão destrutiva do símbolo: [subscription_plan.py:45](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/subscription_plan.py:45). |
| REST Binance | Símbolo passado por `params` ao HTTPX: [rest.py:148](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/rest.py:148), [rest.py:226](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/rest.py:226). |
| Redis | Chaves preservam o símbolo; cliente instalado usa UTF-8 estrito: [redis.py:139](C:/dev/project-hunter/packages/core/hunter_core/redis.py:139), [connection.py:595](C:/dev/project-hunter/.venv/Lib/site-packages/redis/asyncio/connection.py:595). |
| Logs | Não há codificação ASCII explícita; renderização JSON em produção: [logging.py:67](C:/dev/project-hunter/packages/core/hunter_core/logging.py:67). Não validei o encoding do terminal operacional. |

**O QUE EU FARIA DIFERENTE**

**Manteria exatamente `s.encode("utf-8")`, sem NFC nem `surrogatepass`.**

- UTF-8 mantém os mesmos bytes dos símbolos ASCII, portanto preserva seus proprietários para o mesmo `N`.
- Símbolo é identificador da exchange. Normalizar somente no hash acrescenta uma regra desnecessária de distribuição; normalizar também o identificador pode alterar a chave consultada no REST/banco. Só adotaria normalização com contrato explícito da exchange.
- `surrogatepass` permite surrogates isolados; não é necessário para caracteres chineses nem para Unicode válido. Um `"\ud800USDT"` ainda falha com UTF-8 estrito: isso representa entrada malformada a rejeitar na fronteira, não motivo para permissividade no hash. [Documentação Python](https://docs.python.org/3.12/library/codecs.html#error-handlers).

**Sobre uma exceção por item afetar o lote: sim, existem outros pontos.**

- **Catálogo:** uma entrada elegível sem filtro obrigatório faz `parse_market()` levantar e aborta toda a listagem: [normalize.py:122](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/normalize.py:122), [normalize.py:160](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/normalize.py:160). Isolamento exige cuidado: omitir a entrada e tratar o catálogo parcial como completo pode marcá-la como delistada em [universe.py:156](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:156). Preservaria o último catálogo válido ou representaria explicitamente a incompletude.

- **Tickers bulk:** uma entrada sem `lastPrice` aborta a compreensão inteira; `_fetch_tickers()` captura `ExchangeError` e retorna `{}`: [rest.py:253](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/rest.py:253), [universe.py:110](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:110). Volumes anteriores são preservados pelo `COALESCE`; num banco novo, faltam volumes para ordenar corretamente o top-N: [universe_repo.py:97](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:97), [universe_repo.py:164](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe_repo.py:164). Vale corrigir separadamente, preservando os tickers válidos e sinalizando ranking incompleto.

- **Bootstrap do hot state:** erro em um `write_ticker()` impede o retorno do universo inteiro, depois da etapa de banco: [universe.py:161](C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:161). Exemplo: `WRONGTYPE` numa chave específica. Vale separar publicação do universo de aquecimento do cache.

- **Ingestão:** `handle_event()` não captura erros por evento; eles propagam pelo consumidor, que só trata `ExchangeError` no laço externo: [ingest.py:195](C:/dev/project-hunter/services/market-worker/hunter_market_worker/ingest.py:195), [streaming.py:72](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:72), [streaming.py:159](C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:159). Uma falha Redis específica de símbolo pode encerrar a tarefa e afetar o `TaskGroup` inteiro: [main.py:69](C:/dev/project-hunter/services/market-worker/hunter_market_worker/main.py:69).

Isolaria **falhas de dados identificáveis por símbolo**, com observabilidade e recuperação. Não colocaria `except Exception: continue` indiscriminadamente: indisponibilidade compartilhada de Redis/Postgres precisa continuar visível, e candle final não pode ser descartado silenciosamente.

**CONCORDO COM**

Aprovo tecnicamente o hotfix mínimo e a regressão com símbolos reais. **O M1 continua bloqueado até corrigir e repetir a prova operacional**, incluindo cobertura dos símbolos Unicode e entrega pelo WS da aplicação. CRITICAL descreve corretamente a indisponibilidade total da coleta no cenário relatado.

**OBSIDIAN**

- **Revisão da Astra — t16b-sharding:** acrescentar errata da recomendação ASCII e contrato UTF-8 estrito.
- **Market Collector:** registrar causa, alcance global e resultado da nova prova operacional.
- **WebSockets:** registrar a rejeição Unicode na autorização dos canais da API.
- **Open Bugs / Resolved Bugs:** acompanhar separadamente sharding, autorização WS, E2E e isolamento de lotes.