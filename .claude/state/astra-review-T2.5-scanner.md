**RESUMO**

Concordo com a estrutura geral, **com ajustes antes de implementar**. Os principais são: corrigir o caminho de reidratação do episódio, não transformar heartbeat em prova de cobertura e preservar efeitos duráveis até o commit. Assumi o papel de `backend-specialist`.

**1. Onde guardar os estados**

- **AnomalyState:** concordo com colunas + `metadata["state"]`, atualizados atomicamente. O adaptador de leitura precisa receber `market_id` da coluna: `as_wire()` não o inclui, embora seja obrigatório no estado. Preserve também o último estado encerrado, ou um marcador temporal equivalente: o bloqueio de eventos antigos depende dele. Reiniciar carregando apenas anomalias ativas permite que uma avaliação antiga reabra uma anomalia já encerrada. [lifecycle.py:76](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:76), [lifecycle.py:114](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:114), [lifecycle.py:230](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:230).

- **EpisodeState:** concordo, mas o caminho real é **`feature_snapshot["state_out"]["status"]`**. Não existe `["status"]["state_out"]` nesse envelope. `EpisodeState.from_wire()` atende à reidratação. Persista também os `HOLD`: eles zeram confirmadores mesmo preservando o score anterior. [envelope.py:51](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/envelope.py:51), [episode.py:166](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/episode.py:166), [status.py:177](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/status.py:177).

- **RegimeState:** concordo com a linha aberta **por `scope`**, inclusive `UNKNOWN` na partida. Atualize o checkpoint a cada observação aceita, não apenas quando `changed=True`; senão um restart perde as confirmações pendentes. Preserve separadamente a evidência que abriu o intervalo. Mudança do **par** fecha a linha anterior, abre outra e publica; `label_changed` acompanha o evento. [analysis.py:125](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:125), [decision.py:74](C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/decision.py:74), [decision.py:143](C:/dev/project-hunter/packages/indicators/hunter_indicators/regime/decision.py:143).

- **StageState/FeatureState:** Redis é aceitável como checkpoint quente e perdível, mas **existe uma alternativa no schema atual**: acrescentar um bloco versionado de checkpoint ao JSONB `feature_snapshots.features`, junto ao vetor do minuto fechado, inclusive para mercados sem episódio. Eu faria **Redis para continuidade entre avaliações + checkpoint por minuto no Postgres para recuperação**. Isso não promete recuperar a trajetória intraminuto; após uma lacuna não observada, a histerese precisa ser invalidada. [analysis.py:69](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:69), [stage/model.py:96](C:/dev/project-hunter/packages/indicators/hunter_indicators/stage/model.py:96).

Uma correção adicional: perder o checkpoint e passar `None` **não produz automaticamente `gap_rebuild`**. Hoje isso produz `bootstrap`; `gap_rebuild` ocorre quando existe checkpoint e seu avanço encontra um gap. Se escolher Redis como armazenamento exclusivo, a distinção entre primeira partida e perda de estado precisa ser implementada explicitamente. [atr.py:272](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/atr.py:272).

**2. Cadências e execução em processo**

**Aceito anomalias+estágio em processo; não exijo consumir o próprio `features.updated`.** Porém, registre essa especialização em `PIPELINE.md`: a arquitetura atualmente descreve etapas por streams e explicitamente distingue isso de chamadas síncronas. [ARCHITECTURE.md:8](C:/dev/project-hunter/docs/ARCHITECTURE.md:8).

Eu exigiria estas condições:

- Um único responsável por avançar cada mercado, com vetor, projeção de baselines, estágio, anomalias e regime capturados para o corte da avaliação. Runners independentes não podem montar o score lendo referências mutáveis que já avançaram. [scorer.py:94](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/scorer.py:94).
- Consumidores podem enfileirar trabalho rapidamente, mas **marcar dirty em memória não conclui um efeito durável**. Para esses efeitos, ACK somente depois do commit ou de uma transferência durável equivalente. O filtro Redis não substitui idempotência no Postgres. [consume.py:10](C:/dev/project-hunter/packages/core/hunter_core/events/consume.py:10).
- Regime, baseline, universo e vencimento de qualidade também invalidam mercados para oportunidade; não apenas ticks.
- O watchdog deve preencher a interrupção **antes da próxima leitura válida**, inclusive após restart. E atenção: `advance_status` com amostra inelegível **interrompe a sequência, não expira o episódio**; anomalias têm expiração absoluta de quatro horas. [status.py:18](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/status.py:18), [lifecycle.py:245](C:/dev/project-hunter/packages/indicators/hunter_indicators/anomalies/lifecycle.py:245).

Os timers precisam compartilhar orçamento: esperas independentes de 1 s + 2 s + 1 s podem ultrapassar o alvo antes mesmo do custo computacional. O contrato é **p99 ≤ 3 s**, não apenas “cada runner respeita seu intervalo”. [M2.md:58](C:/dev/project-hunter/docs/plans/M2.md:58).

**3. `covered_until` do tape**

**Não considero o heartbeat atual prova suficiente.** Há três problemas concretos:

1. Ele já informa `dropped_events`; descartes podem acontecer mantendo `connected` e sem alteração de `reconnects`. Sua regra declararia cobertura sobre trades perdidos. [heartbeat.py:78](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:78).
2. `ts` é o relógio da publicação do heartbeat, não um marcador de ingestão concluída. Ele não demonstra que todos os trades até aquele instante chegaram ao tape disponível ao scanner. [heartbeat.py:266](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:266).
3. O heartbeat periódico é de 5 s. Normalmente `hb.ts < as_of` de uma avaliação atual; como `trades_between` exige `covered_until >= end`, essa proposta continuaria recusando as janelas. Extrapolar para `now` fabricaria cobertura. [heartbeat.py:42](C:/dev/project-hunter/services/market-worker/hunter_market_worker/heartbeat.py:42), [windows.py:174](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/windows.py:174).

Eu colocaria a declaração de cobertura **no coletor**, vinculada à sessão/shard, à subscrição do símbolo e ao progresso efetivamente entregue. Reconexão, descarte, perda de escrita e mudança de subscrição quebram o intervalo. O scanner precisa consumir um corte coerente entre tape e cobertura.

Além disso, `covers_from` não pode anteceder o início efetivamente retido quando houve truncamento. O decoder já distingue o trade mais antigo disponível e buffer cheio; não sobrescreva isso apenas com a entrada no universo. [hotstate.py:214](C:/dev/project-hunter/packages/indicators/hunter_indicators/features/hotstate.py:214).

Até existir essa evidência, manter `insufficient_coverage` é correto. **Heartbeat saudável é condição necessária, não suficiente.**

**4. Backfill**

**Entregaria a ponte nesta T2.5.** Só métrica + `system_event` deixa incompleto um requisito explícito do plano e do brief. [M2.md:59](C:/dev/project-hunter/docs/plans/M2.md:59), [brief-T2.5:14](C:/dev/project-hunter/.claude/state/brief-T2.5-scanner-worker.md:14).

O consumidor novo deve validar e registrar intervalos ausentes em `ingestion_gaps`, com deduplicação e ACK após commit. O recovery existente já procura gaps abertos dos mercados monitorados e os processa; não criaria outro executor REST concorrente. [recovery.py:274](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:274).

Correção de referência: nessa árvore a função é **`recover_registered`**, não `backfill_gap`. O caminho externo `_recover_one` faz REST fora da transação e revalida o gap com lock antes de persistir. [recovery.py:103](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:103), [recovery.py:191](C:/dev/project-hunter/services/market-worker/hunter_market_worker/recovery.py:191).

Divida pedidos grandes em intervalos limitados, respeite propriedade do mercado por shard e permita retentativa/reconciliação do pedido. O bootstrap precisa de **sete dias amostrados mais o histórico anterior necessário ao warm-up**, não apenas sete dias brutos. [bootstrap.py:25](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/bootstrap.py:25).

**5. Lote e retenção**

**Sim: `FOR SHARE` apenas para envelopes que serão persistidos.** Esse é precisamente o contrato; não há exigência de lock a cada vetor. Faça uma consulta com a união dos IDs distintos do lote, revalide todos e mantenha os locks até o commit. [DATABASE.md:1139](C:/dev/project-hunter/docs/DATABASE.md:1139).

Se uma baseline desapareceu, **não basta retirar seu ID do JSON mantendo o score calculado com ela**. Reavalie a amostra afetada, incluindo estágio/status quando dependentes, e produza um envelope coerente com a indisponibilidade.

Concordo com negócio + history + `enqueue_many` na mesma transação; inclua também `market_regimes` e os checkpoints pertinentes. `enqueue_many` já faz inserção multilinha idempotente dentro da transação do chamador. [outbox_store.py:162](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:162).

Dois cuidados:

- Encerrar episódio é atualização **por identidade**. Uma inserção já com `expired_at` preenchido não conflita com o índice parcial de episódios abertos. [analysis.py:190](C:/dev/project-hunter/packages/core/hunter_core/db/models/analysis.py:190).
- O `event_id` de atualizações precisa distinguir **episódio + observação/transição**. Usar só o ID da oportunidade faz a outbox descartar suas atualizações seguintes como duplicadas. [outbox_store.py:178](C:/dev/project-hunter/packages/core/hunter_core/events/outbox_store.py:178).

**6. Aceite honesto dos 30 minutos**

Aceito baselines em construção, regime `UNKNOWN` com motivo e ausência de EARLY/HOT quando os dados não os sustentarem. O bootstrap exclui explicitamente tape, book, derivativos e `_live`; `trade_velocity_1m` tem motivo próprio de equivalência não provada. [bootstrap.py:9](C:/dev/project-hunter/packages/indicators/hunter_indicators/baselines/bootstrap.py:9).

Meu mínimo seria:

- **Cobertura contabilizada:** universo esperado, mercados avaliados, vetores por qualidade, baselines utilizáveis/em construção e motivos por feature. Gate respeitado: ≥120 observações válidas e ≥3 dias distintos; denominador esperado de 420 por bucket. [DATABASE.md:1092](C:/dev/project-hunter/docs/DATABASE.md:1092), [DATABASE.md:1110](C:/dev/project-hunter/docs/DATABASE.md:1110).
- **Progresso real:** snapshots por minuto, bootstrap/backfill avançando, regime sendo avaliado e exemplos reais de features calculadas. Uma execução inteira sem qualquer amostra pontuável prova operação em aquecimento, mas ainda não prova o caminho operacional completo do score.
- **Explicabilidade:** recomputação de amostras realmente gravadas, com componentes, versões, baselines e estados; ausência não vira score zero. O scorer retorna `score=None` quando não há componente MAD disponível. [scorer.py:294](C:/dev/project-hunter/packages/indicators/hunter_indicators/opportunity/scorer.py:294).
- **Operação:** p95/p99 com denominadores, CPU, filas, atraso da persistência/outbox, `/ready`, erros e progresso durante bootstrap. Prova real de 30 minutos e carga sintética de 200 mercados são requisitos distintos do brief. [brief-T2.5:17](C:/dev/project-hunter/.claude/state/brief-T2.5-scanner-worker.md:17).
- **Recuperação em testes:** restart, falhas entre commit/publicação/ACK, eventos duplicados e antigos, perda de Redis, watchdog e concorrência com retenção. Cenários sintéticos ficam nos testes.

**Não exigiria uma quantidade de anomalias ou oportunidades naturais em 30 minutos.** Mas registraria a divergência com o brief que pede linhas reais no Radar: a API consulta somente `opportunities`; mercados sem episódio ficam ausentes. Se não surgir episódio, esse item fica **não demonstrado**, sem inventar linhas e sem declarar o aceite integral cumprido. [radar.py:1](C:/dev/project-hunter/apps/api/hunter_api/repositories/radar.py:1), [brief-T2.5:18](C:/dev/project-hunter/.claude/state/brief-T2.5-scanner-worker.md:18).

**ARQUIVOS**

Nenhum criado ou modificado.

**TESTES**

Não executados. Parecer baseado em leitura de código, contratos e memória; nenhuma prova operacional realizada nesta consulta.

**MUST-FIX**

Antes da implementação:

- Corrigir reidratação e preservar confirmadores/identidades: restart não pode esquecer um `HOLD` nem reabrir episódio antigo.
- Substituir a inferência de cobertura por evidência do coletor: descarte com WS conectado não pode produzir tape “completo”.
- Garantir ACK após efeito durável e IDs por atualização: crash não pode perder trabalho nem deduplicar atualizações legítimas.
- Reavaliar amostras quando faltar baseline no lock: não persistir número cuja evidência foi removida.

**NICE-TO-HAVE**

Checkpoint por minuto no Postgres como recuperação do Redis; métricas separadas de espera, cálculo e persistência para localizar violações do p99.

**O QUE EU FARIA DIFERENTE**

Usaria um coordenador por mercado para avançar os estados, um escritor de lotes e tarefas separadas de IO/manutenção. Manteria o corte da avaliação explícito entre eles.

**CONCORDO COM**

Avaliação em processo, mercados sujos, contexto incremental, baselines horárias, REST exclusivamente no market-worker e outbox no mesmo commit do negócio.

**OBSIDIAN**

- **Workers** — registrar coordenação, ACK/commit, recuperação e critérios de readiness do scanner.
- **Features (Feature Engine)** — documentar cobertura do tape, checkpoints e limites honestos do bootstrap.
- **Anomalies (Anomaly Engine)** — registrar reidratação de estados encerrados e interrupções pelo watchdog.
- **Data Flow** — explicitar execução em processo e ponte de backfill.
- **Revisões-Astra / T2.5 — desenho do scanner** — registrar este parecer, decisões aceitas e itens ainda não demonstrados na prova.