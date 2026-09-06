# Notas de desenho — T2.5 (`scanner-worker`)

Decisões tomadas ao implementar `.claude/state/brief-T2.5-scanner-worker.md`, com a segunda
opinião da Astra (`.claude/state/astra-review-T2.5-scanner.md`). Onde a "Decisão conjunta" de
`docs/plans/M2.md` (linhas 46–61) manda, ela manda; onde ela era omissa, a escolha está aqui com o
motivo e com o rótulo **suposição** quando é escolha minha, não contrato.

## 1. Um dono avança um mercado (e por que não são cinco consumidores)

`PIPELINE.md` §3 diz que o gatilho das anomalias é `features.updated`. O scanner **publica** esse
evento, mas não o consome: `evaluate.evaluate_market` roda features → anomalias → estágio → score →
status numa passada só, sobre **um corte**. O motivo não é custo de round-trip, é correção:
`ScoreContext.__post_init__` (T2.4) recusa um score cujo estágio, regime ou anomalias sejam de outro
instante, e cinco tarefas independentes leriam estados que outra já avançou. Aceito pela Astra na
consulta de desenho ("Aceito anomalias+estágio em processo; não exijo consumir o próprio
`features.updated`"), com a exigência — cumprida — de registrar a especialização aqui e no
`PIPELINE.md`.

Os consumidores só **marcam** (`state.touch`). A evidência é o hot state, não a mensagem: um tick diz
"este mercado se mexeu" e o vetor é calculado das quatro chaves do Redis. É isso que torna a
coalescência sã — vinte ticks num segundo são uma avaliação, e descartar dezenove não custa nada
porque nenhum deles *era* a evidência.

## 2. `covered_until`: a prova é do coletor, e o corte é a prova

Sem `covered_until` do tape, `trade_velocity_1m`, `buy_pressure_5m` e `sell_pressure_5m` saem
`insufficient_coverage` e **nenhum EARLY publica** (notes-T2.2 §12.3/§13). Duas decisões:

**A prova nasce no market-worker** (`hunter_market_worker/coverage.py`, ligado em `streaming.py`).
A primeira proposta — derivar de `hb:market:{exchange}` — foi **recusada pela Astra e a recusa está
certa**: aquele hash publica `ws_state` ao lado de um `dropped_events` *cumulativo*, então um socket
conectado que perdeu um trade leria como "coberto". O que o coletor publica é o intervalo que ele
consegue sustentar: sessão (reconexão reinicia), por símbolo (assinatura no meio da sessão cobre só
dali em diante), com o stamp segurado enquanto há escrita em voo e sempre **`now − 0,5 s`**, nunca
`now` — o evento que o adaptador já recebeu pode não ter chegado ao tape.

**O corte da avaliação é `covered_until`, não o relógio.** `trades_between` exige
`covered_until >= end` e `end` é o próprio corte; uma prova é por construção atrasada, então avaliar
em `utcnow()` tornaria toda janela improvável para sempre. O scanner avalia "o mercado como era
observável em `as_of`", que é a definição do tipo. Se a prova ficar mais de 5 s atrás
(`MAX_CUT_LAG_S`), o corte volta para o relógio e as features de tape se recusam sozinhas — tarde e
honesto é melhor que atual e inventado.

**Correção que o teste pegou:** a primeira versão deixava `covers_from` no trade mais antigo do
tape, e aí uma janela de 60 s nunca fechava. A regra certa é a da Astra: sem truncamento, a lista
tem *todos* os trades desde o início da sessão, então a ausência de trades antigos significa que não
houve nenhum e o início da sessão é o piso honesto (é isso que faz um minuto calmo produzir um zero
real); **com** truncamento o anel descartou o começo e o piso é o trade mais antigo retido.

## 3. Onde mora cada estado durável

| Estado | Casa | Por quê |
|---|---|---|
| `AnomalyState` | colunas de `anomalies` + `metadata['state']` | as colunas são a verdade que a API lê; o `as_wire()` guarda o que não tem coluna (contadores de calmaria provada, direção, `baseline_ids`). Escritos na **mesma** instrução, então a linha não pode descrever um estado e o metadata outro |
| `EpisodeState` | colunas de `opportunities` + `feature_snapshot['state_out']['status']` | `below_floor_readings` não tem coluna, e sem ele um restart esquece quanto dos 15 minutos foi de fato observado. `EpisodeState.from_wire` é o inverso. **Caminho corrigido pela Astra**: é `state_out.status`, não `status.state_out` |
| `RegimeState` | `market_regimes.supporting_features['state_out']` da linha aberta | atualizado a **cada observação aceita**, não só quando o par muda (senão o restart perde as confirmações pendentes — achado da Astra) |
| `StageState`, `FeatureState`/ATR, último `HistoryMark` | Redis `scan:state:{exchange}:{symbol}` | não são fatos sobre o mercado, são fatos sobre *esta* recursão. Custo declarado e limitado: perder o Redis reancora o ATR e custa duas observações à histerese do estágio |

**Anomalias encerradas são recarregadas junto com as ativas** (achado da Astra): a guarda de ordem de
`lifecycle.advance` vale para qualquer estado, então um processo que recarregasse só as linhas
`active` deixaria uma reentrega antiga **reabrir** uma anomalia encerrada.

**Correção da Astra sobre o ATR:** perder o checkpoint e passar `None` produz `origin_reason =
"bootstrap"`, **não** `gap_rebuild` — `gap_rebuild` é quando existe checkpoint e o avanço encontra um
buraco. Como `advance_from_context` não distingue partida fria de perda de estado, quem distingue é
`Checkpoint.recovered`, aqui.

## 4. ACK depois do efeito, e a diferença entre notificação e anúncio

Ticks, derivativos e liquidações são **notificações**: não têm efeito durável próprio (o vetor sai do
hot state), então o ACK é imediato e perder uma não custa nada. `market.candles.closed` anuncia um
**minuto que tem de virar snapshot**, então a mensagem fica pendente (`PendingAck`) e o ACK acontece
depois que a transação que gravou o snapshot commitou. A distinção está escrita por stream em
`consumers.py` em vez de ficar para inferência.

## 5. Uma transação por ciclo, e o lock de baseline que o banco recusa

Snapshots do minuto, ciclo de anomalias, episódios, amostras de history, regime, revisões novas de
baseline e as **linhas da outbox** commitam juntos (`persist.flush_batch` + `enqueue_many`). O
`event_id` é determinístico e nomeia a **observação**, não só a linha — chaveado só na oportunidade,
o `ON CONFLICT DO NOTHING` engoliria a *segunda* atualização do mesmo episódio como duplicata
(achado da Astra).

**Achado operacional (BUG-1, é de banco, não meu):** `docs/DATABASE.md` §17.2 manda o escritor tomar
`SELECT … FOR SHARE` nos `baseline_ids` antes de gravar o envelope, e a `0003` concede a
`hunter_worker` `SELECT, INSERT, DELETE` em `feature_baselines` e **deliberadamente nenhum `UPDATE`**
(`infra/migrations/ddl/analysis.py::ANALYSIS_WORKER_APPEND_TABLES`). O PostgreSQL exige `UPDATE` para
travar linha, então a instrução falha com *permission denied* contra um banco corretamente migrado —
reproduzido em teste e no stack local. Como uma falha de privilégio **aborta a transação em que
acontece**, o scanner descobre isso **uma vez, na partida** (`writers.probe_baseline_lock`), registra
em `error` e degrada para uma leitura simples de existência. O que continua valendo: uma amostra cuja
baseline sumiu **não é gravada** (o mercado é reavaliado, não é gravado com o id removido — exigência
da Astra). O que se perde: a serialização contra um DELETE concorrente da retenção. A correção é um
grant, e conceder `UPDATE` não afeta a imutabilidade — o trigger `feature_baselines_immutable` recusa
todo `UPDATE` para todos os papéis, dono incluído.

## 6. O envelope é gravado como o motor o produz (e a lição de ter tentado o contrário)

Escrevi primeiro um rename `vector` -> `features` em `rows.storage_envelope`, porque
`apps/api/hunter_api/repositories/radar_common.py` lia `feature_snapshot["features"]…` no commit em
que comecei (`5bd17db`). **Estava errado, e a Astra provou com o histórico:** `98bcfea` já havia
corrigido a API para ler `feature_snapshot["vector"]["values"][key]["value"]`
(`FEATURE_ENVELOPE_PATH`), com um teste de contrato construído do próprio `opportunity_envelope()` —
publicado depois de eu ler o arquivo. Manter o rename quebraria o filtro de volatilidade e a
ordenação por volume exatamente como aquele commit existiu para consertar.

O envelope agora vai para a coluna **sem alteração**; só o `history_mark` viaja junto, sob chave
própria e fora de qualquer caminho que um leitor nomeie (a regra de amostragem compara com a
**última amostra persistida**, e um restart não teria com o que comparar). O teste afirma contra a
constante da própria API, importada, para que as duas pontas não possam divergir em silêncio de
novo. Lição registrada: um arquivo lido no início de uma tarefa longa pode ter mudado no meio dela.

## 7. Custo: o teto medido, e por que ele não foi otimizado aqui

`tests/test_load.py` mede o que o brief pede (200 mercados × 1 tick/s) e o resultado é **negativo e
está registrado como tal**: ~31,5 ms por mercado na mediana, ~96,5 ms no p99, **7,2 s por passada
completa** contra o **p99 ≤ 3 s** da decisão conjunta. Não é surpresa: é exatamente o teto que a
revisão cruzada da T2.2 mediu e **entregou à T2.5** (notes-T2.2 §16: ~50 ms/vetor, 53 % em
`windows._epoch_minutes`, chamado 17× por vetor, `bars_15m` recomputado 3×).

O remédio prescrito lá é um memo por `(mercado, as_of)` **dentro de**
`packages/indicators/hunter_indicators/features/windows.py`, e este brief autoriza
`packages/indicators/**` apenas para adaptadores finos de IO. Então o teste fica como
`xfail(strict=True)` com o número medido no motivo: a suíte é verde, o defeito é visível, e no dia em
que o memo entrar o teste **falha por passar** em vez de continuar afirmando um número que ninguém
remediu. Consequência que a prova de 30 minutos confirma: a cadência real é uma passada a cada ~7 s,
não a cada 1 s.

## 8. O que a prova de 30 minutos mostrou, e o que ela não pôde mostrar

Registro completo em `.claude/state/t25-proof.md`. O resumo honesto: o pipeline roda, escreve
`feature_snapshots` por minuto para os 200 mercados, `/ready` fica verde, não há exceções — e
**nenhuma oportunidade é aberta**, porque com o arquivo de baselines vazio nenhum componente MAD está
disponível, o scorer devolve `score=None` (`no_eligible_evidence`) e `advance_status` com amostra
inelegível não abre episódio. Isso é o comportamento **correto e declarado** ("degradado não é
evidência", T2.4 §4), não uma falha do worker — mas significa que o item do brief "o Radar da API
devolvendo linhas reais" fica **não demonstrado**, exatamente como a Astra antecipou na consulta de
desenho.

O caminho para demonstrá-lo é o **bootstrap** sobre candles persistidas
(`hunter_indicators.baselines.bootstrap`), e ele esbarra no mesmo teto do §7: o replay são 10 080
cortes por mercado, ~30 ms cada, ≈ 5 min por mercado, ≈ 16 h para 200. Os módulos de leitura estão
prontos (`baselines.py`: cache, janela horária, leitura das observações do minuto, `revisions_for`),
o laço que os agenda **não foi entregue** — entregá-lo antes de resolver o custo produziria um worker
que passa horas em warm-up sem avaliar nada. Fica como o primeiro item do NEXT STEP, na mesma tarefa
que o memo do §7.

## 9. Suposições numéricas declaradas (nenhuma vem da decisão conjunta)

1. `COVERAGE_SAFETY_S = 0,5` e stamp a cada 0,25 s (§2).
2. `MAX_PROOF_AGE_S = 15` para a prova ainda provar algo; `MAX_CUT_LAG_S = 5` para o corte.
3. `SILENCE_S = 120` no watchdog: um ciclo perdido sob carga não é um outage, e declarar que é
   zeraria contadores que estavam legitimamente acumulando.
4. `cycle_s = 0,25` — o laço acorda mais rápido que os throttles de propósito: o orçamento defendido
   é a **idade da entrada**, e dormir 1 s somaria até 1 s de espera pura a cada tick (correção da
   Astra: "os timers precisam compartilhar orçamento").
5. `CHECKPOINT_TTL_S = 7 dias`: um mercado que saiu do universo há uma semana recomeça frio em vez de
   retomar uma histerese de outro regime.
6. `max_markets = 400` como guarda: 200 é o configurado, o dobro é bug a montante, e avaliar em
   silêncio estouraria o orçamento em vez de dizer.

## 10. O que ficou como requisito para outras tarefas

- **quant-engineer (T2.2, `features/windows.py`):** o memo por `(mercado, as_of)` do §7. Critério de
  aceite é o teste de reprodutibilidade (byte-idêntico), não o benchmark — e `test_load.py` vira
  vermelho por `xpass` no dia em que entrar, o que é o sinal desejado.
- **database-architect:** o grant de `UPDATE` em `feature_baselines` para `hunter_worker` (§5), ou
  uma revisão de `DATABASE.md` §17.2 que descreva o protocolo que o grant atual permite.
- **T2.4 / seed:** `components_frozen` continua `false` no banco local (verificado). A ratificação é
  a tarefa coordenada de dois arquivos do notes-T2.4 §2 e **não foi executada aqui** — nada em T2.5
  depende dela, e executá-la sem o par de testes do core deixaria a suíte vermelha.
- **T2.6:** o §6 (o nome da chave do vetor no envelope).
- **T2.8:** a retenção com o protocolo de lock, que hoje só é meio-executável (§5).
- **exchange-integration-specialist (`packages/exchange-adapters/**`):** os dois buracos que a
  margem de 0,5 s da cobertura só *complementa*, nunca prova (achado da Astra, escrito por extenso no
  cabeçalho de `hunter_market_worker/coverage.py`): (a) uma **geração de conexão** que o adaptador
  incremente a cada reconexão interna, para que uma queda tratada sem encerrar o gerador quebre o
  intervalo; (b) um **marcador de progresso entregue**, confirmado depois da escrita — profundidade
  de fila não basta, porque um item já retirado pela task saiu da fila e ainda não chegou ao
  consumidor. Enquanto isso não existir, o intervalo publicado é otimista nesses dois cenários, e
  está dito no módulo.

## 10b. Revisão de diff da Astra — cinco achados, quatro corrigidos aqui

`.claude/state/astra-review-T2.5-scanner-diff.md`. Veredito dela: **REQUEST_CHANGES / BLOCKED para
aceite**, e concordo com o veredito (ver o §7 da prova). Os achados:

1. **O envelope** (§6 acima) — corrigido, com o teste ancorado na constante da API.
2. **A invalidação por baseline sumida deixava efeitos passarem** — removia a oportunidade e a
   amostra de history, mas mantinha as anomalias, os eventos e os callbacks pós-commit, publicando
   `opportunities.updated` de uma linha não gravada. Corrigido: `WriteBatch.event_market` e o dono de
   cada callback permitem derrubar **todos** os efeitos do mercado afetado. Teste novo.
3. **Um lote que falha perdia o minuto para sempre** — `last_snapshot_minute` avançava ao montar o
   lote. Corrigido: a promoção acontece depois do commit. **E isso introduziu um defeito novo**, que
   a prova encontrou em seguida: várias avaliações do mesmo minuto no mesmo lote e
   `CardinalityViolationError`. Corrigido com de-duplicação por chave de conflito (fica a última, a
   do hot state mais fresco). Dois testes.
4. **Cobertura: a margem de 0,5 s não prova completude** — ela está certa, e o limite está agora
   escrito no §2 e no módulo: o `CoverageTracker` não enxerga a fila interna do adaptador nem uma
   reconexão que o adaptador trate sem encerrar o gerador. **Aceito como pendência declarada**, não
   corrigido: o remédio é o adaptador declarar geração de conexão e progresso entregue, o que é
   `packages/exchange-adapters/**`, fora dos arquivos deste brief. Registrado no NEXT STEP.
5. **Recusar a partida quando o `FOR SHARE` é negado** — divergência registrada. Ela prefere recusar
   (ou um modo explicitamente limitado a coleta de features); eu mantive a degradação com `error` no
   log, porque a propriedade que protege o score continua valendo (a amostra cuja baseline sumiu não
   é gravada) e recusar a partida deixaria o M2 inteiro parado por um grant que não é meu. Quem
   decidir o contrário muda uma linha em `writers.probe_baseline_lock`.

Também aceitei a correção de fato dela sobre o `xfail`: o teste de carga roda **cinco passadas** e
mede o ciclo sem persistência nem publicação — não é a carga de 60 s ponta a ponta. O texto do
`xfail` e o §4 da prova dizem isso.

## 11. Segunda opinião da Astra

Consulta de desenho antes de implementar: `.claude/state/astra-review-T2.5-scanner.md`, 6 perguntas.
Aceitos e implementados: caminho real da reidratação do episódio (`state_out.status`), preservar as
anomalias encerradas, checkpoint do regime a cada observação aceita, avaliação em processo com dono
único, ACK depois do efeito durável, `event_id` por episódio **e** observação, `FOR SHARE` só nos
envelopes que serão gravados, reavaliar (não desidratar) a amostra cuja baseline sumiu, a ponte de
backfill nesta tarefa, e o mínimo honesto da prova. **Divergência registrada:** ela recusou o
heartbeat como prova de cobertura e propôs que a declaração nasça no coletor — concordei e foi o que
foi feito (§2), o que custou tocar em `streaming.py`.

**Registrado, não implementado:** o laço de bootstrap (§8) e o `BackfillRequester` — o módulo está
pronto e testado no seu contrato, mas nada o chama ainda, porque o único chamador previsto é o
bootstrap. `main.py` marca a lacuna com `del requester` em vez de fingir que está ligado.
