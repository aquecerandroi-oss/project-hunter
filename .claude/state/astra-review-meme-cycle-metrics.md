## RESUMO

**REQUEST_CHANGES.** O p95 está correto **para os ciclos concluídos presentes no anel**. O diff ainda não sustenta sozinho a guarda “antes × depois”: falta identificar a geração das métricas e preservar evidência comparável. Há também uma espera adicional de Redis no caminho do laço.

Revisão como `code-reviewer`, seguindo a decisão de instrumentar antes do seed registrada em [EXP-M26:530](/C:/dev/project-hunter/obsidian/05-EXPERIMENTS/EXP-M26-grafico-em-moedas-maduras.md:530). Nenhum arquivo alterado.

## ARQUIVOS

Inspecionados:

- [cycle_metrics.py](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py): 165 linhas.
- [main.py](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py): 329 linhas; diff restrito ao import e aos dois wrappers.
- [test_cycle_metrics.py](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py): 253 linhas.

Todos abaixo de 350 linhas, conforme contagem por leitura dos arquivos.

## TESTES

**Não executados nesta revisão estritamente sem escritas**; não afirmo aprovação de pytest, lint ou tipos.

Os testes cobrem percentis, descarte do anel, throttle, exceção do passo e falha imediata da publicação. Falta cobrir publicação lenta, reinício com hash existente e separação antes/depois. Referências: [test_cycle_metrics.py:46](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:46), [:166](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:166), [:186](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:186), [:203](/C:/dev/project-hunter/services/meme-worker/tests/test_cycle_metrics.py:203).

## MUST-FIX

**1. HIGH — a publicação adicional pode atrasar materialmente o laço sem aparecer na duração.**

O cronômetro termina antes de `await publish(...)`, que executa o HSET diretamente. O cliente tem timeouts de 5 s e três retries. Referências: [cycle_metrics.py:144](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:144), [:160](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:160), [main.py:143](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:143), [redis.py:37](/C:/dev/project-hunter/packages/core/hunter_core/redis.py:37), [:82](/C:/dev/project-hunter/packages/core/hunter_core/redis.py:82).

**Cenário:** a cadeia termina normalmente; o Redis degrada justamente no HSET extra. O próximo passo começa vários segundos mais tarde, mas o p95 continua mostrando apenas o trabalho anterior. Capturar a exceção evita derrubar o processo; não elimina a espera.

**Correção proposta:** publicar por tarefa supervisionada com armazenamento pendente limitado, sem criar tarefas ilimitadas por ciclo; contar perdas/falhas. Se permanecer síncrono, precisa de orçamento próprio curto e aceite explícito desse atraso. A afirmação “sem mudança de comportamento” hoje é forte demais.

**2. HIGH — falta proveniência para distinguir métricas antigas das recém-iniciadas.**

O anel nasce vazio, mas não há publicação inicial nem identificador de boot nos campos. O heartbeat geral atualiza `ts` e renova a chave sem limpar os campos específicos. Referências: [cycle_metrics.py:80](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:80), [:108](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:108), [main.py:247](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:247), [runtime.py:101](/C:/dev/project-hunter/packages/core/hunter_core/runtime.py:101).

**Cenário:** reinício antes de expirar o hash; heartbeat geral volta, mas o primeiro ciclo demora ou falha. O leitor encontra `ts` novo e p95 do processo anterior. Uma coleta espaçada também pode perder a queda do contador e não perceber o reinício.

**Correção proposta:** identificar geração por laço (`run_id`, início UTC, versão), publicar estado inicial vazio/desabilitado e exigir geração válida, atualidade e cobertura no consumidor. `ts` geral nunca deve validar a métrica de ciclo.

**3. HIGH, bloqueante do seed — definir e preservar a comparação antes de usá-la como guarda.**

Os campos publicados guardam resumos móveis e apenas a última duração; não permitem recuperar a distribuição histórica. Referência: [cycle_metrics.py:108](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:108).

**Cenário:** semear com o processo vivo e comparar o primeiro p95 posterior ao seed contra o anterior. O anel posterior ainda contém quase toda a população anterior, diluindo a mudança. Reiniciar elimina essa mistura, mas perde a base caso ela não tenha sido persistida.

Isso **não exige migração neste diff**, mas exige coleta durável e protocolo antes do seed. Além disso, o desenho ainda referencia **72 h antes de I1**, não antes do seed: [desenho:633](/C:/dev/project-hunter/docs/design/exp-m26-grafico-moedas-maduras.md:633). A instrumentação nova não recupera esse passado; a nova referência precisa ficar registrada explicitamente.

## NICE-TO-HAVE

- **Nearest-rank:** não encontrei erro na fórmula; ela ordena e usa `ceil(p·n)`. O p95 cheio ocupa o posto 114/120 ou 456/480. Reinício cria outro anel; **seed sem reinício mistura fases**. Referências: [lab_heartbeat.py:31](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab_heartbeat.py:31), [main.py:307](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/main.py:307).
- **Inteiros:** a saída é inteira, mas o cálculo usa `float` e `round`. Para cumprir literalmente “sem float”, usaria `monotonic_ns()` e conversão inteira com arredondamento documentado. Atualmente, 60.000,4 ms pode virar 60.000 e não contar overrun; o limiar é aplicado **após quantização**. Referências: [cycle_metrics.py:96](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:96), [:128](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:128), [:145](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:145).
- **UTC:** produção usa `utcnow`, corretamente; a validação de `record` aceita qualquer timezone consciente. Normalizar para UTC ou rejeitar offset não zero deixaria o contrato exato. Referências: [cycle_metrics.py:90](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:90), [:129](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:129).
- **Throttle:** a contagem suprimida só aparece no próximo overrun elegível. Se os overruns cessarem, não há resumo final. O total continua sendo a referência durante aquele boot. Referência: [cycle_metrics.py:146](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:146).

## O QUE EU FARIA DIFERENTE

**Definição de ciclo:** manteria o passo inteiro, incluindo `record_tick` e `write_lab_heartbeat`. Ambos fazem parte do trabalho necessário antes da próxima execução: [lab.py:340](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab.py:340).

Discordo de tratar o overrun como início do atraso de cadência. A cadência **sempre** é aproximadamente:

`duração do passo + publicação extra + período de sleep + atraso de agendamento`

O `forever` dorme depois do passo: [collect.py:341](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/collect.py:341). Portanto, `duração > nominal` é um **limiar operacional de trabalho**, não detecção de deadline perdido. Um Lab de 10 s passa para 13 s: piora 30%, sem nenhum overrun. A guarda precisa comparar p95 independentemente desse contador.

Também não chamaria os anéis de “duas horas”: são **120/480 conclusões**, cobrindo aproximadamente duas horas apenas quando o trabalho é desprezível.

**Histórico sem migração:** proporia um coletor supervisionado na infraestrutura existente, persistindo eventos técnicos no Postgres. `system_events` já oferece `event`, `component` e `data JSONB`: [system.py:50](/C:/dev/project-hunter/packages/core/hunter_core/db/models/system.py:50).

Para a primeira versão:

1. Ler a cada **5 s**, após acrescentar a identificação de boot.
2. Persistir cada novo `(run_id, loop, cycles_total)` com duração inteira, horário de término, horário da leitura e fase experimental.
3. Detectar saltos de sequência, reinícios e estagnação; lacunas impedem declarar cobertura completa.
4. Congelar a base anterior e calcular percentis sobre durações individuais, em intervalos previamente definidos.

**HGETALL a cada N minutos não basta para reconstruir o p95 dos ciclos.** No Lab, vários valores de `last_cycle_ms` seriam sobrescritos entre leituras. Guardar p95 móveis permite acompanhar esses resumos, mas **p95 de p95 não é p95 dos ciclos**. Mesmo a coleta de 5 s precisa verificar sequência; frequência sozinha não prova completude.

A tabela horária futura deve preservar amostras ou uma distribuição agregável, não somente percentis. E uma coluna `cycle_ms` escrita pelo próprio `record_tick` não consegue incluir a duração dessa escrita e do heartbeat posterior sem uma segunda etapa: [lab.py:340](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/lab.py:340).

## CONCORDO COM

Anel limitado, relógio monotônico, duração do passo inteiro, ausência representada por vazio e propagação da exceção original: [cycle_metrics.py:80](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:80), [:105](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:105), [:142](/C:/dev/project-hunter/services/meme-worker/hunter_meme_worker/cycle_metrics.py:142).

O volume nominal de cinco HSET/min é pequeno; o risco principal é a espera sob degradação. E excluir passos que lançam exceção respeita o desenho, desde que a guarda trate interrupções como ausência de evidência, nunca como melhora.

## OBSIDIAN

- **EXP-M26 — gráfico em moedas maduras:** registrar base prospectiva, intervalos comparados, cobertura mínima e tratamento de reinícios.
- **Meme — README:** distinguir duração, cadência e overrun; retirar a equivalência automática entre anel e duas horas.
- **Revisões Astra — meme-cycle-metrics:** registrar os bloqueios, a proposta de coleta durável sem migração e a limitação dos percentis amostrados.

Nenhuma página foi modificada.