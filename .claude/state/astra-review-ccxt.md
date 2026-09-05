**Minha opinião: manter Binance própria; fazer Bybit própria no M1b; avaliar CCXT para ampliar cobertura na Fase 3, especialmente nas integrações privadas.** Concordo com a direção do Claude, mas não aprovaria a proposta sem corrigir a configuração numérica e a promessa de isolamento por extra.

Li os documentos e a estrutura solicitados, sem acessar `.env` nem modificar arquivos. Esta é uma avaliação estática; não executei CCXT nem o resolver.

**1. Binance: concordo em não substituir.**

O adaptador já incorpora decisões específicas do HUNTER: duas rotas WS, estado por conexão, watchdog, fila limitada que preserva candles finais, ordenação por `event_ts` e pesos REST. Migrar exige demonstrar equivalência dessas garantias, com pouco benefício imediato para a única exchange já implementada.

A separação existente entre normalização, REST, streams, subscriptions e fila também favorece manutenção. Eu reaproveitaria componentes comprovadamente comuns para Bybit, mantendo dialetos separados.

Há uma divergência documental relevante: `EXCHANGE_INTEGRATION.md` ainda descreve book Binance com snapshot + diffs; o código utiliza snapshots parciais `depth20`. A implementação efetiva deve orientar os testes de equivalência.

**2. Must-fix nos contratos antes de aceitar CCXT.**

| Ponto | Cenário de falha | Exigência |
|---|---|---|
| **Decimal** | Configurar literalmente `number='str'` faz o parser tentar chamar uma string; campos podem virar `None`. Converter um float já arredondado para Decimal tampouco recupera precisão. | Em Python, usar **`{'number': str}`**, com o tipo callable. Verificar precisão desde o payload até `Normalized*`, inclusive livros, limites e ordens. |
| **UTC e origem temporal** | Um ticker sem timestamp recebe `now()` e parece recente; um candle usa horário de abertura como horário do evento. | Separar timestamp da exchange, `event_ts`, recebimento local e relógio monotônico. Ausência de timestamp exige política explícita, sem inventar event time. |
| **Staleness por conexão** | Trades continuam chegando enquanto o book congela; um heartbeat agregado mantém tudo verde. Retorno de cache também pode aparentar atividade. | Instrumentar conexões reais e freshness por canal/mercado relevante. ACK/pong não atualizam último dado. |
| **Watchdog** | Socket responde a ping, mas não entrega dados válidos, ou `watch_*` fica pendurado. | Prazos de conexão, assinatura e silêncio; reconexão, reassinatura e recuperação verificáveis. Canal esparso, como liquidações, precisa de política diferente de book. |
| **Filas e caches** | Consumidor lento perde atualizações antes de elas chegarem à fila HUNTER; cache repete trades e duplica volume. | Limitar também buffers internos, definir `newUpdates` explicitamente, deduplicar e medir perdas. Preservar finais na fila externa não recupera finais já perdidos internamente. |
| **Rate limit** | Duas instâncias respeitam seus limites locais, mas juntas estouram o limite por IP/conta. Backfill esgota orçamento de recuperação. | Manter coordenação Redis por escopo real, pesos e prioridade. Cobrir chamadas internas, como carregamento de mercados, paginação e retries. |
| **OHLCV parcial** | Candle em formação vira final; uma parcial atrasada substitui a final, contaminando features e replay. | Preservar confirmação e ordem temporal; final nunca regride para parcial. Recuperação REST precisa de cutoff confiável, paginação, deduplicação e convenção de intervalo definida. |
| **Símbolos e unidades** | `BTC/USDT:USDT` vira `BTCUSDTUSDT` ao remover separadores; spot e perpétuo colidem; contratos são tratados como quantidade do ativo. | Mapeamento explícito entre chave HUNTER, `market.id` e símbolo CCXT, incluindo tipo, liquidação e `contract_size`. Interpretar `precisionMode`, não assumir que `precision` significa tick. |
| **Cobertura e campos ausentes** | Exchange “suportada” não oferece um canal obrigatório; funding sem mark price é preenchido com zero para caber no modelo. | Matriz por exchange × mercado × operação. Ausência deve produzir indisponibilidade explícita ou revisão do contrato; nunca valor financeiro fabricado. |

Dois achados são concretos na **4.5.77**:

- `parse_number()` chama `self.number(value)` e captura exceções; portanto, **`str` e `'str'` não são equivalentes**. [Código do parser](https://github.com/ccxt/ccxt/blob/v4.5.77/python/ccxt/base/exchange.py).
- O parser WS de candles Bybit devolve seis elementos OHLCV e **descarta `confirm` e os timestamps adicionais**. Um wrapper apenas sobre `watch_ohlcv()` perde informação necessária para nosso `is_final` e `event_ts`. Seria preciso capturar o payload antes dessa redução ou usar ingestão específica. [Código Bybit](https://github.com/ccxt/ccxt/blob/v4.5.77/python/ccxt/pro/bybit.py).

O CCXT Pro tem caches limitados, mas eles são janelas deslizantes, não garantia de entrega; `newUpdates` continua usando esses caches internamente. Isso precisa entrar nos testes de consumidor lento. [Manual CCXT Pro](https://github.com/ccxt/ccxt/wiki/ccxt.pro.manual#newupdates-mode).

Além disso, satisfazer somente `ExchangeAdapter` não basta para equivalência operacional: em [base.py](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/base.py), `connection_states`, `server_time`, funding realizado e atualização incremental estão em `ExchangeAdapterExtras`. Eu exigiria essas capacidades conforme o uso pelo worker, mesmo permanecendo opcionais estruturalmente.

**3. Pins: extra opcional não oferece o isolamento proposto.**

Confirmei o wheel de 6.638.814 bytes e os pins de `orjson==3.11.9`, `typing_extensions==4.16.0` e `certifi==2026.6.17`. Uma correção ao contexto: o metadata consultado declara **`aiohttp>=3.14.3,<3.15` e `cryptography>=50,<51`**, não igualdade exata nesses dois casos. Há vários outros pins exatos. [Metadata PyPI 4.5.77](https://pypi.org/pypi/ccxt/4.5.77/json).

**`orjson>=3.10` é compatível com `==3.11.9`.** O risco imediato é o resolver rebaixar a versão atualmente travada em 3.12, não necessariamente falhar.

| Alternativa | Isola os pins? |
|---|---|
| Extra `hunter-exchanges[ccxt]` | **Não.** Controla instalação opcional; suas restrições participam da resolução. |
| Outro pacote membro do mesmo workspace | **Não.** Continua compartilhando resolução e lockfile. |
| Projeto independente, fora dos membros, com lock e ambiente próprios | **Sim, entre ambientes.** Importá-lo no ambiente principal volta a reunir as dependências. |
| Outro processo usando a mesma `.venv` | **Não.** |
| Processo com ambiente próprio, ou imagem própria | **Sim.** Desde que também use resolução independente. |

Essa distinção consta da documentação de [workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) e [dependências do uv](https://docs.astral.sh/uv/concepts/projects/dependencies/).

Eu começaria a avaliação num projeto independente. Para produção, escolheria conscientemente entre aceitar os pins no workspace após validação ou manter um worker isolado com mensagens versionadas, Decimal como string e timestamps explícitos. A segunda opção exige revisar a decisão arquitetural de imagem única e o modo `HUNTER_ROLE=all`.

Não usaria overrides ou `--no-deps` como suposta solução de isolamento: transferem para nós a responsabilidade por compatibilidade.

**4. Bybit no M1b: prefiro adaptador próprio.**

O escopo é estreito: perpétuos USDT, canais conhecidos e contratos rigorosos. Já temos Protocol, modelos e fixtures. O maior trabalho restante é justamente preservar semântica e resiliência — áreas que a API unificada não resolve integralmente, como demonstra a perda de `confirm`.

Eu faria `BybitAdapter` com testes de precisão, snapshot/delta, reconexão com gap, parcial atrasada após final, silêncio de dados com pong ativo e saturação da fila.

Mudaria essa escolha se uma prova curta com CCXT demonstrasse todos esses comportamentos **com menos código específico e menor custo de manutenção**. Não trataria “exchange suportada” como essa demonstração.

**5. Ordens nas Fases 3/4: sim, CCXT tende a valer mais.**

Autenticação, assinatura, criação/cancelamento e consultas privadas de várias exchanges oferecem maior retorno para reutilização. Ainda assim, CCXT seria infraestrutura sob o `LiveExecutionAdapter`, mantendo risco, autorização e estado de execução no HUNTER.

Os bloqueadores para live seriam:

- **Timeout após envio:** a exchange pode ter aceitado a ordem. Registrar intenção e identificador cliente antes do envio; reconciliar antes de reenviar. Retry cego pode duplicar exposição.
- **Cancelamento concorrente com fill:** cancelar não prova ausência de execução. Reconciliar fills, posição e quantidade remanescente.
- **Semântica da ordem:** validar por exchange contratos versus unidades, `reduceOnly`, hedge/one-way, triggers, precisão e mínimos. Ordem destinada a fechar não pode abrir posição inversa.
- **Permissões desconhecidas:** não presumir um `fetch_permissions()` universal nem interpretar ausência como `withdraw=false`. Credencial só é aceita após comprovação pelo mecanismo específico da exchange.
- **Isolamento por tenant:** instância/cache privado não deve circular entre credenciais. Chaves e execução seguem confinadas ao componente autorizado.

A Fase 3 deve preparar e validar conexões; envio real continua reservado à Fase 4. Também resolveria a fronteira entre validação inicial pela API, descrita na integração, e uso exclusivo de credenciais pelo execution-worker.

**Concordo com CCXT como segunda implementação e com preservar Binance. Faria diferente a entrada: Bybit própria agora; CCXT depois, com capacidades certificadas por exchange e extensões explícitas.** `CcxtAdapter(exchange_id)` pode ser a fachada, mas não deve prometer uniformidade operacional que ainda não foi demonstrada.