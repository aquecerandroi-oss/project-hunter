**MUST-FIX**

- **Heartbeat solo rejeitado ainda pode aparecer conectado.** Sem shards válidos, um solo com `ts` vencido ou mais de 2 segundos no futuro falha em `_fresh`, mas o retorno preserva seu `ws_state="connected"`, com zero reportando. `build_market_status` não corrige isso quando `last_event_at` é passado válido. Retornar `unavailable` nesse ramo. [market_shards.py:175](C:/dev/project-hunter/apps/api/hunter_api/services/market_shards.py:175), [system_status.py:278](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:278).

- **Um shard sem evento desaparece da avaliação de frescor.** Cenário: dois shards conectados, um com `last_event_at=None`, outro com evento recente; o agregado informa conectado e timestamp recente. Além disso, um timestamp futuro individual fica escondido pelo `min` quando outro shard tem timestamp normal, escapando da validação posterior. Validar timestamps individualmente e representar ausência sem atribuir ao conjunto o frescor do único shard conhecido. [market_shards.py:139](C:/dev/project-hunter/apps/api/hunter_api/services/market_shards.py:139), [system_status.py:293](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:293).

**NICE-TO-HAVE**

- **Compose permite topologia incompleta sem erro de índice:** `MARKET_SHARDS=8` com somente perfil `shards` inicia índices 0–3 válidos, deixando 4–7 ausentes; somente `shards8` deixa 1–3 ausentes. Documentar a combinação obrigatória e verificar cobertura operacionalmente. O comentário já mostra corretamente ambos os perfis. [docker-compose.yml:142](C:/dev/project-hunter/infra/docker/docker-compose.yml:142), [docker-compose.yml:179](C:/dev/project-hunter/infra/docker/docker-compose.yml:179).

- **Topologia autodeclarada tem limite:** após todos os `*of4` expirarem, um cluster antigo completo `*of2` volta a parecer saudável. Isso segue o contrato escolhido; detectar divergência da topologia desejada exigiria uma referência externa. [market_shards.py:169](C:/dev/project-hunter/apps/api/hunter_api/services/market_shards.py:169).

**CONCORDO COM**

- `0of2` não completa `0of4`; SCAN repetido não duplica contagem; hash expirado é descartado; PID numérico não satisfaz o sufixo; `ts` futuro além da tolerância é rejeitado nos shards. [market_shards.py:107](C:/dev/project-hunter/apps/api/hunter_api/services/market_shards.py:107), [market_shards.py:159](C:/dev/project-hunter/apps/api/hunter_api/services/market_shards.py:159).
- Assumindo o mesmo `utcnow` da antiga factory, explicitá-lo apenas antecipa ligeiramente a captura. Não vejo mudança de UTC nem introdução de look-ahead nos parsers: fechamento, finalidade e horário do evento continuam separados. Não atesto consumidores fora do recorte. [streams.py:261](C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/streams.py:261).
- Mercados e gaps continuam vindo do repositório. [system_status.py:251](C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:251).

Sem testes ou alterações.

**OBSIDIAN**

- Página de T2.5g/coleta de mercado — registrar os dois casos de falso frescor e a combinação dos perfis; título exato não verificado no recorte autorizado.