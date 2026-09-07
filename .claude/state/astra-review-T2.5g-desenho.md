## RESUMO

**Concordo com quatro processos explícitos e manter `tick_coalesce_ms` inicialmente.** O desenho precisa de ajustes antes de implementar: cobertura atômica com tratamento de restart, agregação também no caminho realtime, contagem correta dos gaps e proteção contra resets dos contadores.

## ARQUIVOS

Nenhum arquivo criado ou modificado. Revisão em modo OPINIÃO, pelos escopos de exchange-integration-specialist e backend-specialist.

## TESTES

Não executei testes nem medi o stack. Os números de desempenho abaixo são os que você forneceu; as conclusões sobre implementação vêm da leitura do código.

## MUST-FIX

**1. Agregar apenas `build_market_status` não impede a System de mentir.**

Cada worker publica `market_status` por exchange em [heartbeat.py:106](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:106). O frontend substitui a linha inteira da exchange pelo último evento recebido em [live-status.tsx:62](/C:/dev/project-hunter/apps/web/components/system/live-status.tsx:62).

**Cenário:** HTTP responde `stale`, com 3/4 shards; imediatamente um shard saudável publica `connected` e 50 mercados, sobrescrevendo o agregado.

O `rt:system` precisa entregar a mesma semântica agregada. Pode haver agregação na API ou invalidação seguida de leitura do agregado; não basta acrescentar `shard_index` ao payload atual.

**2. `open_gaps=max` está errado; preserve preferencialmente a consulta global existente.**

O recovery seleciona os IDs dos símbolos da fatia em [recovery.py:129](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:129) e conta os gaps desses IDs em [recovery.py:219](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:219).

**Cenário:** quatro shards com dez gaps cada resultam em dez apresentados, embora existam quarenta.

Para contadores dos shards, seria **soma**. Porém `build_market_status` já usa gaps e mercados monitorados do Postgres em [system_status.py:302](/C:/dev/project-hunter/apps/api/hunter_api/services/system_status.py:302). Eu preservaria isso: a soma dos heartbeats também perde a parcela do shard ausente e não representa gaps de mercados fora da coleta atual.

**3. Identidade, frescor e topologia precisam ser validados antes da agregação.**

`max(shard_total)` serve como descoberta numa topologia homogênea, mas não como autoridade sobre qual topologia deveria estar rodando.

**Cenário:** coexistem `0of2`, `1of2`, `0of4`, `1of4`. Contar quatro entradas e tomar `N=4` declara completude sem `2of4` e `3of4`. Outro caso: os heartbeats de N=4 expiram e sobra um processo legado solo; o fallback clássico pode declarar saudável uma topologia incorreta. Os heartbeats atuais expiram em 30 segundos: [heartbeat.py:43](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:43).

Exigir:

- conjunto exato de índices `0..N-1`, com chave e campos coerentes;
- nenhuma mistura silenciosa de totais ou clássico com shards;
- validade e frescor de **cada** `ts` e `last_event_at`, antes de reduzir;
- deduplicação de chaves: `SCAN` pode devolver o mesmo elemento mais de uma vez. [Contrato do Redis](https://redis.io/docs/latest/commands/scan/).

Sem uma expectativa independente dos heartbeats vivos, quando todos desaparecem o correto é **indisponível, N desconhecido**, nunca inferir um cluster saudável menor.

**4. A cobertura precisa mudar de escritor, não apenas ganhar um Lua posterior.**

Concordo com a interseção:

`session_since = MAX(since_i)`  
`covered_until = MIN(until_i)`

Mas a atualização dos campos do shard, símbolos e agregado deve acontecer **na mesma operação atômica**, sem os HSET atuais dos limites globais.

**Cenário:** o shard saudável escreve seu `covered_until` na hash principal; antes do Lua corretivo, o scanner lê e aceita cobertura além do shard travado. Hoje essa escrita direta acontece em [coverage.py:326](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:326).

Além disso:

- Verificar os **N pares esperados da mesma topologia**, não a quantidade geral de campos presentes.
- Ausência, vazio, valor inválido ou `MAX(since) > MIN(until)` devem produzir limites vazios. **Nunca aumentar `until` para fazê-lo alcançar `since`.**
- Ruptura de sessão deve invalidar o registro do próprio shard e recalcular o agregado; adaptar também `_clear`, hoje global em [coverage.py:340](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:340).
- Definir limpeza/reconciliação de `sym:*` após restart. `_published` começa vazio e só conhece campos escritos pelo processo atual: [coverage.py:140](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:140), [coverage.py:332](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:332).

**Cenário adicional:** um shard reinicia com universo menor; seus símbolos antigos permanecem na hash compartilhada, cujo TTL os demais renovam. O leitor aceita qualquer `sym:*` válido presente, em [scanner coverage.py:115](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/coverage.py:115). Isso ressuscita prova de um símbolo que ninguém mais coleta.

**5. Corrigir `dropped_events` é parte necessária desta tarefa.**

Confirmado: a chamada está atualmente em [streaming.py:72](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:72); `connection_field` faz `getattr(..., None)` em [supervision.py:13](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/supervision.py:13), enquanto o adapter oferece `connection_states()` em [binance/__init__.py:92](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/__init__.py:92).

**Cenário:** descarta-se um trade, a fila depois esvazia e a cobertura retoma a sessão anterior como contínua. A ruptura por drops depende de incremento do contador em [coverage.py:245](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coverage.py:245).

**Somar os snapshots resolve o atributo errado, mas não resolve resets.** `_start_group` substitui o estado da conexão em [ws.py:271](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:271).

Exemplo: A tinha 100 drops; A reinicia zerada e B descarta cinco. A soma cai de 100 para cinco; `max(0, delta)` vira zero e oculta os cinco. O contador bruto entregue ao tracker é ainda pior: ele só atualiza a referência quando aumenta.

Eu acumularia deltas **por conexão**, tratando redução como reset e contando o valor novo; mudança de geração deve também invalidar/reestabelecer a referência de cobertura. A geração já detecta recriação em [ws.py:263](/C:/dev/project-hunter/packages/exchange-adapters/hunter_exchanges/binance/ws.py:263). Não reutilizaria cegamente o helper atual do heartbeat: ele também usa `max(0, delta)` em [heartbeat.py:174](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:174).

**6. O perfil local precisa alterar também a configuração do primeiro worker.**

Perfis habilitam serviços; não reconfiguram automaticamente um serviço sem perfil. [Documentação do Compose](https://docs.docker.com/compose/how-tos/profiles/).

**Cenário:** `--profile shards` adiciona `1/4`, `2/4`, `3/4`, mas `market-worker` continua `0/1`. Há sobreposição de coleta e escritores incompatíveis. O modo solo inclusive dispensa a eleição de líder em [universe.py:265](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:265).

## NICE-TO-HAVE

Deixaria a otimização de defaults/Pydantic como dívida separada, condicionada ao resultado da prova. Os percentuais cumulativos do perfil são sobrepostos; não devem ser somados como custos independentes.

Acrescentaria à prova: CPU e mercados reais por shard, incremento de drops, avanço de `covered_until`, latência por stream e teste de morte/restart de um shard com a System aberta.

## O QUE EU FARIA DIFERENTE

**(1) Heartbeat:** usaria **`min(last_event_at)`**, documentado como “menor último evento entre shards”. Validaria valores individualmente; um timestamp futuro pode desaparecer dentro de um `min` aparentemente válido. Shard esperado ativo sem timestamp não pode ser ignorado na redução.

Isso ainda não prova frescor de todos os mercados: cada heartbeat já guarda o **máximo** dos eventos aceitos dentro do shard em [streaming.py:119](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/streaming.py:119). É saúde da fatia, não cobertura completa da fita.

Somaria subscriptions/reconnects/drops, preservaria os contadores globais do banco e aplicaria pior estado e `rest_gate=suspended` se qualquer shard suspender. Para expectativa de N, preferiria um pequeno registro de topologia publicado pelo coletor e compartilhado entre os leitores. Sem ele, aceitaria a autodeclaração apenas com a limitação explícita descrita acima.

**(2) Coverage:** sua hash auxiliar com Lua é uma solução pequena e compatível com o leitor. Não vejo alternativa mais simples que preserve simultaneamente atomicidade e honestidade. O shard travado pode manter seu limite congelado: o leitor já rejeita prova com mais de 15 segundos em [scanner coverage.py:81](/C:/dev/project-hunter/services/scanner-worker/hunter_scanner_worker/coverage.py:81). Isso dispensa usar heartbeat como prova de cobertura.

**(4) Compose:** prefiro serviços explícitos. No local, usaria override ou comando operacional que selecione conjuntamente `0/4` e os três serviços adicionais. Na VPS, garantir quatro serviços efetivos, todos com ambiente de produção, healthcheck individual e mesma configuração global de universo.

Não exigiria subida do shard zero primeiro: a eleição é por lock em [universe.py:270](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:270). Não faria readiness de cada shard depender dos irmãos.

Ao mudar N, registraria a transição dos grupos de backfill: seus nomes incluem a topologia em [backfill.py:126](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/backfill.py:126); grupos novos começam no ID `0` em [produce.py:41](/C:/dev/project-hunter/packages/core/hunter_core/events/produce.py:41). Há replay do histórico ainda retido e grupos antigos permanecem. Limpeza exige reconciliação das pendências, nunca exclusão automática.

**(5) Latência:** o perfil aponta fortemente para saturação no caminho de recepção/parse/fila. **Não prova que todo o atraso antecede o coalescer.** O envelope é criado dentro de `flush_ticks`, em [coalesce.py:167](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/coalesce.py:167); portanto seus 18 ms excluem a espera pelo flush.

Manteria os 250 ms e mediria primeiro com quatro shards. Quatro processos são uma hipótese bem sustentada, mas “4×50 resolve” ainda requer prova: a distribuição é por `crc32 % N`, não balanceamento exato de quantidade ou tráfego, em [universe.py:78](/C:/dev/project-hunter/services/market-worker/hunter_market_worker/universe.py:78).

## CONCORDO COM

A direção geral está correta: chaves por shard, compatibilidade solo, interseção conservadora da cobertura, correção dos drops nesta tarefa e processos explícitos.

Só não usaria `/ready` verde da API como evidência de coleta saudável: hoje ele verifica exclusivamente Postgres e Redis em [health.py:63](/C:/dev/project-hunter/apps/api/hunter_api/health.py:63). O aceite precisa verificar o agregado de mercado separadamente.

## OBSIDIAN

- **Market Collector** — contrato de cobertura por shards, resets dos contadores e resultado da nova prova.
- **WebSockets** — agregação consistente entre HTTP e `rt:system`.
- **Monitoring** — significado de `last_event_at`, shards esperados/reportando e limites da readiness.
- **Deployment** — topologias solo/quatro shards e transição dos grupos de backfill.
- **Open Bugs** — registrar o atributo incorreto de drops e sua regressão obrigatória.
- **Revisoes-Astra/T2.5g** — registrar este parecer e as decisões efetivamente adotadas.