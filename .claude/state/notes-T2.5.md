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

---

# T2.5b — o que faltava para o scanner ser aceito

Continuação das notas acima. A T2.5 fechou BLOCKED com cinco itens ausentes (§8, §11 e o
achado 5 da revisão de diff da Astra); esta parte entrega os quatro que eram do
`scanner-worker` e mede o quinto. Segunda opinião de desenho:
`.claude/state/astra-review-T2.5b-runners.md` (6 must-fix, todos endereçados abaixo).

## 12. Bootstrap: o custo é do minuto, não da feature

`hunter_indicators.baselines.bootstrap.replay_vectors` já calcula o **vetor inteiro** por corte e
um único `ObservationCollector` o espalha por todos os buckets. Então o laço que faltava não podia
iterar features: itera minutos, uma vez, e é isso que torna o custo proporcional a
`minutos × mercados` em vez de `features × minutos × mercados`. Não há um `for feature` em
`replay.py` — deliberadamente.

Medido nesta máquina (`replay_vectors`, 150 cortes, série sintética):

| `buffer_minutes` | ms por corte |
|---|---|
| 60 | 2,20 |
| 120 | 2,91 |
| 500 | 13,80 |
| **1500 (produção)** | **31,57** |

10 080 cortes × 31,6 ms = **5,3 min de CPU por mercado**, ~17,7 h para 200 — com o motor de hoje.
Com a T2.2b (≤ 5 ms/vetor) cai para ~50 s por mercado, ~2,8 h para 200. Os dois números estão aqui
porque a decisão de operação depende de qual está na árvore.

**Fatia cooperativa, verificada por vetor** (correção da Astra: "orçamento por tempo verificado a
cada vetor, fatias curtas"). `BootstrapJob.run_slice` segura o loop por `slice_s = 50 ms` e devolve
`pause_s = slice_s × (1/duty − 1)`; com `duty = 0,4` o bootstrap fica com 40 % do relógio. Um
*chunk* de 250 cortes — a alternativa óbvia — seriam 7,5 s de silêncio, o suficiente para derrubar
`/ready` e travar os consumidores. O gerador e o coletor **sobrevivem entre fatias**: recriá-los
reanchoraria a recursão de Wilder e pagaria os cortes de novo. Teste:
`test_slicing_the_replay_does_not_change_a_single_number` (mesmos `input_fingerprint` em uma passada
e em N).

**Suposição declarada:** `bootstrap_budget_s = 120` é quanto uma visita gasta num mercado antes de o
laço olhar o relógio de novo — é o teto do atraso que o refresh horário pode sofrer. `duty` e
`budget` são as duas únicas cadências do scanner lidas do ambiente
(`SCANNER_BOOTSTRAP_DUTY`, `SCANNER_BOOTSTRAP_BUDGET_S`), porque o repartição certa depende de quão
atrasado o loop vivo já está; limiar nenhum vem do ambiente.

## 13. "Já bootstrapado" precisa de duas fontes, e nenhuma delas sozinha

A primeira ideia era `max(window_end)` por mercado no arquivo. **A Astra a recusou com um cenário
concreto** e ela está certa: um mercado com duas horas de candles grava algumas revisões, o
`max(window_end)` fica recente, e o mercado é pulado por 24 h mesmo depois de o backfill chegar. O
arquivo não distingue "escreveu 288 buckets porque é só isso que existe" de "escreveu 288 e morreu".

A regra entregue exige **as duas fontes concordando** (`ledger.pending_markets`):

| Fonte | O que prova | O que não prova |
|---|---|---|
| `feature_baselines` (`source='bootstrap'`, `max(window_end) ≥ janela − 24 h`) | que as linhas existem | que a corrida terminou |
| `scan:bootstrap:{exchange}` (hash Redis) | que aquela corrida terminou, contra qual roster | nada durável — perder o Redis **não autoriza** pular |

Perder o Redis custa **uma passada de bootstrap inteira**, nunca um número errado (o `ON CONFLICT`
por `input_fingerprint` transforma a reescrita em no-op). Custo declarado e aceito.

O `roster_id` (sha256 de `(feature, versão)` ordenado + `window_days` + `algo_version`) fecha o
segundo cenário da Astra: subir a versão de uma feature invalida o registro anterior, porque as
revisões de ontem descrevem outra população.

**Backoff exponencial** para o mercado que terminou incompleto: `retry_s = 6 h`, dobrando até 7
dias. O reparo que ele espera é trabalho de outro serviço, e insistir antes de o dado chegar só
queima o orçamento de replay.

## 14. O refresh horário podia apagar o bootstrap — e apagaria

Achado da Astra que eu não tinha visto e que teria tornado a tarefa inútil uma hora depois de
entregue. `select_projection` ordena por `available_at DESC` e **não sabe o que é maturidade**: numa
instalação nova, o primeiro refresh (60 observações, 1 dia distinto) sobrepõe um bootstrap de 420
observações e depois reprova no portão. O detector perderia a baseline que acabara de ganhar.

`refresh._admissible` **retém** (não grava) a revisão que seria menos madura que a em vigor, conta em
`hunter_scanner_baseline_revisions_total{outcome="withheld"}` e registra no log. É política
explícita e **provisória**, dita como tal no módulo: o certo é uma população só, histórica e viva,
uma observação por minuto — e medianas já calculadas não se somam para reconstruí-la. A retenção
para sozinha quando a população viva amadurece. Teste:
`test_an_immature_live_revision_does_not_supersede_a_usable_bootstrap`.

**Segundo defeito da mesma família, encontrado ao ligar o laço:** os detectores leem o *cache*, e o
cache só era recarregado no refresh horário — um bootstrap que terminasse às 10:05 ficaria invisível
até as 11:00. `refresh.reload_market` recarrega a projeção do mercado logo após a escrita. Teste:
`test_a_bootstrapped_market_is_usable_without_waiting_for_the_next_hour`.

## 15. Lacunas: todo buraco conta, e o intervalo é semiaberto

`MIN_REQUEST_MINUTES = 5` estava errado duas vezes, e a Astra pegou as duas:

1. **recusava exatamente os buracos que mais doem.** Um minuto faltando custa a
   `relative_volume_1h` um dia inteiro de observações (a janela de 1 440 minutos nunca fecha). "Pequeno
   demais para pedir" não é propriedade do tamanho do buraco;
2. **media o intervalo como fechado.** Os cinco minutos ausentes 10:00–10:04 têm diferença de
   quatro minutos e eram recusados.

Agora: intervalo **semiaberto** `[gap_start, gap_end)`, piso de um minuto, e "isto é só o minuto
ainda sendo coletado" decidido pelo chamador contra o relógio (`tail_lag_minutes = 3`), não por
comprimento. Buracos a menos de 60 min um do outro viram um pedido só (refazer os minutos do meio é
inofensivo — o market-worker faz upsert por chave natural), e acima de 5 pedidos o casco de tudo vai
num só: um pedido limitado é reparável, uma fila ilimitada não.

## 16. Derivativos: capacidade ausente ≠ warm-up

`repo.load_deriv_history` existia desde a T2.5 e **ninguém o chamava**, então
`open_interest_change_1h/4h` eram `missing_input` para sempre e `OPEN_INTEREST_SPIKE` ficava **armado
e mudo** nos 200 mercados. Agora um `deriv_loop` recarrega 9 h de leituras a cada 5 min (a janela
cobre `funding_change_8h` com as 48 min de tolerância), e o `_warm` da partida as carrega **antes** da
primeira avaliação.

**Reidratação com sobreposição, não com cursor** (nice-to-have da Astra): a consulta filtra pelo
`ts` da observação, não pela ordem de inserção, então um cursor estritamente depois da leitura mais
nova perde uma linha inserida atrasada atrás dele. Relê os últimos 30 min e funde por `ts`. Teste:
`test_the_incremental_reload_still_sees_a_row_inserted_behind_the_cursor`.

**Desarmar é declaração, não silêncio.** `deriv.detector_roster` remonta o roster **por mercado, por
ciclo**, a partir do estado atual: sem nenhuma leitura de OI, `OPEN_INTEREST_SPIKE` vira
`enabled=False, disabled_reason="deriv_history_unavailable"`, e a avaliação passa a dizer
`detector_disabled` + o motivo em vez de não dizer nada. Rearma sozinho no ciclo seguinte à chegada
do dado — foi por isso que o roster é reconstruído em vez de fixado na partida (must-fix 6 da Astra).
E a fronteira é **capacidade**, não maturidade: "não há histórico nenhum" é declaração deste módulo;
"há histórico e ele não alcança uma hora atrás" continua sendo o `warmup` da própria feature.
Divergência registrada com a Astra: ela juntaria `funding_rates` ao `deriv_history` só se a semântica
fosse preservada; mantive a recusa da T2.5 (settlement não é amostra), então `funding_change_8h`
continua indisponível **com motivo**, e `FUNDING_ANOMALY` depende de `funding_rate` (do hash), não
dela.

## 17. Readiness: declarar não é reprovar, mas parar é

`scanner_baselines` era "o arquivo foi lido". Agora:

- verde quando ≥ 80 % do universo tem estado **declarado** (utilizável ou em construção com motivo);
- verde **enquanto o bootstrap avança**, mesmo abaixo disso — uma instalação nova é uma fase, não uma
  falha;
- **vermelho quando ele para de avançar** abaixo do limiar: um scanner que nunca terá baseline nunca
  pontuará nada, e isso é falha.

A frase vai no corpo do `/ready` como *status detail* (`runtime.status_details`, o mesmo canal do
`rest_gate` do market-worker): `"baselines":"bootstrapping BEATUSDT (26/200)"` — diagnóstico ao lado
do veredito, nunca no lugar dele. Três testes em `test_health.py`.

## 18. O que a prova mostrou (resumo; o registro é `t25-proof.md`)

28 mercados bootstrapados em 30 min, 9 909 revisões, **1 065 buckets utilizáveis**, 0 exceções,
`/ready` verde com o progresso ao lado, 28 pedidos de backfill publicados, 7 164 leituras de OI
carregadas. O scorer **passou a produzir score elegível** (`eligible=True`) para os mercados com ≥ 3
dias distintos de histórico — era `None` em 200 de 200 na T2.5.

Dois itens continuam não cumpridos, e nenhum deles é código deste worker:

- **p99 ≤ 3 s**: medido > 21 s. Metade da causa é o custo por vetor da T2.2b (não estava na árvore
  durante a prova), metade é o próprio bootstrap dividindo o loop (temporária por construção);
- **Radar com linhas reais**: 0 linhas, agora por um motivo medido componente a componente
  (t25-proof §8) — só `volume` está disponível, porque `liquidity`/`order_flow` não têm fonte
  histórica (declarado desde a T2.3) e 192 dos 200 mercados têm 2,1 dias de candles locais.

## 19. O que ficou como requisito para outras tarefas (novo)

- **market-worker (`services/market-worker/**`): não existe consumidor de
  `market.backfill.requested`.** Verificado nesta prova: 29 mensagens no stream,
  `XINFO GROUPS` vazio. O `recovery.py` acha lacunas pela própria janela de detecção (1 439 min), que
  não alcança o histórico de 7 dias que o bootstrap pede. Enquanto isso não existir, um mercado sem
  histórico fica "em construção" para sempre. **Este é o bloqueio mais alto do M2 hoje**, e está fora
  dos arquivos desta tarefa.
- **quant-engineer / T2.2b:** o memo de `windows._epoch_minutes` continua sendo o item 1. Ele
  divide por ~6 o custo do bootstrap **e** a latência.
- **T2.4 / decisão de produto:** com livro e tape sem fonte histórica, um mercado recém-bootstrapado
  pontua com 1 componente de 8 e nunca abre episódio. Ou se espera 7 dias de snapshots ao vivo, ou
  alguém decide explicitamente o mínimo de componentes que autoriza um score — não é decisão de
  worker.
- **database-architect:** o BUG-1 (§5) está **fechado** por `0005_baseline_lock_grant`, que chegou
  durante esta tarefa. O teste que afirmava a ausência do grant foi reescrito para afirmar o
  protocolo (`test_the_row_lock_is_taken_now_that_the_grant_exists`) e a nota em
  `writers.probe_baseline_lock` foi atualizada; a sonda continua, porque ela responde sobre *este*
  deployment e não sobre o histórico de migrações.

## 20. Suposições numéricas novas (nenhuma vem da decisão conjunta)

1. `bootstrap_duty = 0,4` e `slice_s = 50 ms` (§12).
2. `bootstrap_budget_s = 120` — teto do atraso do refresh horário.
3. `max_age_h = 24` para considerar um bootstrap recente; `retry_s = 6 h` dobrando até 7 dias.
4. `deriv_refresh_s = 300` e janela de 9 h com sobreposição de 30 min (§16).
5. `baseline_ready_ratio = 0,80` (o número está no brief) e `BootstrapProgress.active` com 15 min de
   tolerância.
6. `tail_lag_minutes = 3`, `merge_gap_minutes = 60`, `max_gap_requests = 5` (§15).
7. `CHUNK = 25` mercados por leitura no refresh horário.

## 21. Revisão de diff da Astra — cinco achados, cinco corrigidos

`.claude/state/astra-review-T2.5b-diff.md`. Veredito dela: **REQUEST_CHANGES**. Concordo com os
cinco e todos foram corrigidos nesta mesma entrega:

1. **`available_at` podia anteceder a disponibilidade real.** O `run_bootstrap` carimbava o
   instante capturado *antes* do replay, e o `refresh_hour` reusava um único `now` para todos os
   lotes. Cenário dela: um snapshot de 09:59 persistido às 10:00:20 entra no lote lido às 10:00:30
   e sai publicado como se fosse conhecido às 10:00:01 — um corte com `as_of = 10:00:10` passaria
   nos dois filtros causais lendo dado que ninguém tinha. Corrigido: o carimbo é dado **depois** do
   cálculo, por lote no refresh e no `finish_job` no bootstrap, e nunca antes do relógio real
   (`utcnow() if now is None else max(now, utcnow())` — o `max` existe para que um teste que
   raciocina num instante fixo continue determinístico).
2. **Um bootstrap imaturo podia derrubar uma baseline utilizável.** Eu tinha posto a política de
   maturidade só no refresh; o `finish_job` publicava tudo. Cenário: perdido o ledger (ou passadas
   as 24 h), o bootstrap roda de novo sobre uma janela com lacunas, produz um bucket não vazio
   abaixo do portão, e ele vence a projeção por ser mais novo — com o `reload_market` tornando a
   perda imediata. Corrigido: `refresh.admissible` passou a ser público e o bootstrap o usa antes
   de gravar; `BootstrapOutcome.withheld` e
   `hunter_scanner_baseline_revisions_total{source="bootstrap",outcome="withheld"}` contam.
   Teste: `test_an_immature_bootstrap_does_not_demote_a_usable_baseline`.
3. **Uma falha monopolizava o bootstrap, e uma falha do refresh descartava trabalho alheio.** Um
   único `except` limpava o `job`, e a escolha seguinte voltava ao mesmo mercado a cada 5 min
   enquanto os outros 199 nunca começavam. Corrigido: os dois trabalhos falham em separado; o
   mercado que levanta exceção recebe um registro de tentativa (`bootstrap_failed`) **com o mesmo
   backoff** de uma corrida incompleta, e o replay em voo sobrevive a um refresh que falhou.
4. **O agendador pulava horas e podia dormir por cima de uma virada.** `closed_hour_before(now)`
   direto abandona toda hora em que o processo esteve fora: falhou na hora 09, voltou às 11:02,
   atualiza a 10 e a 09 nunca mais. Corrigido: `due_hour` anda **uma hora por vez** até alcançar a
   última fechada, e `sleep_for` dorme até a virada ou até a próxima checagem, o que vier antes
   (dormir 5 min às 10:59:59 começava o refresh quase 5 min atrasado). Teste:
   `test_the_scheduler_walks_the_hours_it_missed_instead_of_jumping`.
5. **A mudança de roster não invalidava o backoff antigo.** O `roster_id` só protegia o caminho
   "completo"; o `retry_at` valia para qualquer roster. Cenário: uma tentativa da v1 acumulou 7
   dias de espera, entra a v2 com uma feature nova e o mercado fica dispensado até o prazo da v1 —
   com os buckets da feature nova nunca calculados. Corrigido em uma condição; teste:
   `test_a_roster_change_clears_a_backoff_earned_by_the_previous_one`.

Nice-to-have aceitos: validação de `duty`/`budget` (um `duty = 0` era divisão por zero), zerar a
série de `scanner_detectors_disarmed` quando o último mercado rearma, e o texto da métrica dizendo
que "written" conta o que foi **oferecido** ao INSERT idempotente, não linhas novas. Também aceitei
a crítica ao meu teste de reidratação de OI: ele inseria uma leitura *mais nova* que a mais nova
retida, o que um cursor pegaria de qualquer jeito — reescrito para inserir uma **mais antiga**, que
é o único caso que a sobreposição existe para cobrir.

Registrado e **não** implementado: (a) um prazo de expiração para a retenção de revisão imatura —
ela pode segurar indefinidamente se a população viva nunca amadurecer, e pôr um prazo é decisão de
política, não de worker; (b) testes do próprio `baseline_loop` (falha persistente, refresh falhando
com job em voo, duas viradas seguidas) — as funções que decidem cada um desses casos estão testadas
em separado, o laço que as costura não; (c) dois arquivos de **teste** acima de 350 linhas
(`test_bootstrap.py` 434, `test_persistence.py` 475), que o gate exclui por desenho
(`infra/scripts/check_file_size.py`, `SKIP_DIRS`).

---

# T2.5-backfill — o consumidor que faltava (`market-worker`)

Fecha o item 1 do §19: "não existe consumidor de `market.backfill.requested`… este é o bloqueio mais
alto do M2 hoje". Segunda opinião de desenho **antes** de codar:
`.claude/state/astra-review-T2.5-backfill.md` (5 must-fix; os cinco endereçados abaixo).

## 22. O pedido vira lacuna, e só. Quem busca continua sendo o recovery

O consumidor **não chama REST**. Ele traduz um pedido em linhas de `ingestion_gaps` e para. Isso não é
economia de código: é o que mantém uma única porta para a exchange (a decisão conjunta do M2), um
único orçamento de taxa, uma única política de tentativa e um único caminho de anúncio — as velas
preenchidas viram `market.candles.closed` pela outbox porque `upsert_candles` as enfileira na mesma
transação, exatamente como um minuto ao vivo (`durable.py`). **Confirmado na prova**, não assumido.

Duas convenções de intervalo se encontram e a tradução mora num lugar só
(`backfill_plan.normalize_window`): o pedido é **semiaberto** `[gap_start, gap_end)` (o produtor
corrigiu isso na T2.5b, §15) e `ingestion_gaps` é **inclusivo nas duas pontas**
(`expected_times(start, end)` conta `end`, e o fetch pede `gap_end + 1min`). O último minuto aceito é
`min(gap_end, detection_last + 1min) − 1min`, com `detection_last = align_open_time(server_now) −
DETECTION_GRACE` — a fórmula é da Astra e é um minuto mais larga que o meu clamp original, que
descartava um minuto que o próprio recovery aceitaria.

## 23. Um grupo por shard (e por que o grupo único está errado aqui)

`market-worker.backfill.{exchange}.{i}of{N}`. Toda mensagem chega a **todos** os shards; só o dono do
mercado (`crc32(symbol) % N == i`, a mesma fatia de `universe.shard_symbols`) planeja, os outros dão
`XACK` sem efeito. Com um grupo compartilhado, cada pedido é entregue a **um** shard, que na maioria
das vezes não é o dono e só poderia descartá-lo — o pedido se perderia em silêncio. A Astra concorda
com a topologia e acrescentou o `{exchange}` no nome (hoje só existe Binance, mas dois workers de
exchanges diferentes competiriam no mesmo grupo e descartariam trabalho alheio).

Custos declarados, não escondidos: mudar `N` cria grupos novos que releem o histórico retido e deixa
os antigos com pendências (remoção é procedimento manual); cada grupo tem seu próprio
`hunter:processed:{group}`; e o stream tem `MAXLEN 5 000`, então um shard parado por muito tempo perde
pedidos por trimming — a republicação horária do scanner é parte necessária da recuperação, não um
luxo.

## 24. `XACK` nem sempre é marca — o achado mais importante da revisão

Must-fix 1 da Astra, e ela está certa: `ack()` grava o `event_id` em `hunter:processed:{group}` e
`consume()` consulta esse conjunto **antes** de entregar. Uma recusa por "mercado fora do universo"
marcada como processada faria a republicação de uma hora depois ser descartada pela guarda **antes**
de alguém reconsultar o universo — o mercado voltaria e nunca seria backfillado. Regra implementada:

| Situação | `XACK` | Marca `event_id` |
|---|---|---|
| planejado por inteiro | sim | **sim** |
| planejamento parcial (teto de linhas, mês sem partição, minutos de outro gap) | sim | **não** |
| recusa dependente do estado de agora (fora do universo, janela futura, sem partição) | sim | **não** |
| pedido de outro shard/exchange | sim | **não** (a topologia pode mudar) |
| erro transitório (Postgres/Redis) | **não** | não — volta pelo `XAUTOCLAIM`; após 3 tentativas é largado com `outcome=failed` e log de erro |
| envelope ilegível | sim | não (quarentena) |

## 25. Prioridade sem coluna: a idade da janela, não a origem

`ingestion_gaps` não tem `source` nem `priority` e esta tarefa não pode migrar o schema. A separação
é pela **idade da janela**, que é propriedade do dado: `check_gaps` só cria lacunas dentro dos seus
1 499 minutos, então tudo mais antigo é, por construção, histórico pedido por alguém; e um pedido
*dentro* das últimas 24 h descreve exatamente os minutos que a detecção acharia sozinha, então
tratá-lo como vivo não é erro. O que a Astra corrigiu (must-fix 3) e foi implementado:

1. **Desempate dentro do estrato vivo.** `ORDER BY detected_at` deixava 50 lacunas de quase um dia
   passarem à frente de um buraco de um minuto recém-detectado. Agora os dois estratos ordenam por
   `gap_end DESC` — o minuto ausente mais novo primeiro, que é o que toda janela rolante espera.
2. **Teto de linhas não é teto de tempo.** Seis páginas lentas a `FETCH_TIMEOUT_S = 20 s` seriam
   120 s e empurrariam a próxima detecção dois minutos. O estrato histórico roda sob prazo monotônico
   (`HISTORY_BUDGET_S = 30 s`), não inicia outra lacuna sem orçamento e limita o timeout do fetch ao
   que resta.
3. **Descartada** a ideia de gravar `detected_at` no futuro para ordenar por último: quebraria
   `reopen_stale_failed` (que reabre `failed` por `detected_at <= now − 1 h`) e o backfill nunca mais
   seria retentado.

Garantia declarada: **o estrato histórico só gasta o que o vivo não gastou** (`leftover =
min(history_limit, live_limit − len(live))`), com teto próprio de 6 linhas por ciclo.

Efeito colateral que precisou de conserto no mesmo arquivo: `check_gaps` expandia **todo** gap aberto
em minutos para subtrair da janela de detecção. Com lacunas de 7 dias abertas isso construiria
milhões de `datetime` por ciclo; agora os gaps são recortados à janela antes da expansão.

## 26. A corrida que a tabela não impede (must-fix 2)

`ingestion_gaps` não tem unicidade por intervalo, e agora existem **dois** escritores com o mesmo
protocolo (ler cobertura → inserir o que falta). Os dois leem "faltando, sem gap", os dois inserem: duas
linhas, dois fetches REST das mesmas velas. Corrigido com `pg_advisory_xact_lock` por exchange
(`recovery_queries.lock_gap_planning`), tomado **antes** da leitura nos dois caminhos, transacional
(solto no commit ou no rollback, nunca vazado) e sem nenhuma chamada REST na mão. Teste:
`test_two_planners_racing_write_one_set_of_gaps`.

Segundo achado da mesma revisão: a fusão de buracos próximos (≤ 60 min) pode atravessar velas
**persistidas** — refazer minuto presente é inofensivo — mas **nunca** minutos de um gap `open`/`failed`.
Fundir por cima de um `failed` recriaria aqueles minutos como `open` e contornaria o cooldown de uma
hora. Teste: `test_the_merge_never_reaches_across_a_gap_that_already_exists`.

## 27. Mensagem ilegível não pode derrubar o coletor (must-fix 5)

`hunter_core.events.consume` desserializa o envelope **antes** do `yield`; um envelope inválido
levanta dentro do gerador, mata a task, e com o `TaskGroup` do `main.py` mata o worker inteiro — que
reencontra a mesma mensagem depois do restart, porque o `XAUTOCLAIM` a repesca da PEL. Como esta
tarefa só pode tocar `hunter_core/events/**` para nome/maxlen, a tolerância mora em
`backfill_reader.read_batch`, que entrega `(id, None)` para o que não parseia. **Divergência
declarada:** o certo é isso viver no core, para todos os consumidores; fica como pendência escrita no
módulo e aqui.

## 28. Números escolhidos, e de onde cada um vem

| Constante | Valor | Por quê |
|---|---|---|
| `MAX_REQUEST_MINUTES` | 10 080 (7 dias) | a janela de bootstrap da decisão conjunta; acima disso trunca pelo lado **antigo** e é final (teto de política, não de orçamento) |
| `CHUNK_MINUTES` | 240 | limitado por cima pela página de klines (1 500, peso 10, uma chamada dentro de `FETCH_TIMEOUT_S`) e **por baixo pela outbox**: cada minuto preenchido é uma linha, `MAX_PENDING` da prontidão é 500 e a virada de minuto de 200 mercados já contribui ~200. 240 + 200 cabe; 1 440 deixaria `/ready` vermelho ~15 s por ciclo (despachante ~100 linhas/varredura) e ainda atrasaria a vela ao vivo atrás de um dia de histórico |
| `MERGE_MINUTES` | 60 | mesmo número que o produtor usa (notes §15) |
| `MAX_ROWS_PER_REQUEST` | 48 | 7 dias em pedaços de 240 são 42; a folga é para janela fragmentada. O excedente é **adiado** (não marcado), não descartado |
| `MAX_HISTORY_GAPS_PER_CYCLE` | 6 | 6 páginas × peso 10 = 60 de 2 400/min, e ≤ 1 440 linhas de outbox por ciclo |
| `HISTORY_BUDGET_S` / `MIN_FETCH_BUDGET_S` | 30 s / 3 s | metade da cadência de detecção (60 s), e um piso abaixo do qual não vale começar outra página |
| `MAX_MESSAGE_ATTEMPTS` | 3 | uma mensagem que falha sempre é largada com log de erro em vez de girar para sempre |

**Vazão que isso implica, dita por extenso:** 1 440 minutos de histórico por ciclo por shard ≈ 1 dia
de velas por minuto de relógio; 7 dias de um mercado ≈ 7 min; 200 mercados ≈ 23 h. O gargalo **não é
REST** (13 440 de peso para 2 M de velas, ~6 min de cota) — é a outbox, que publica uma mensagem por
minuto preenchido a ~100/s. Registrado como requisito para outra tarefa (§31).

## 29. O buraco que a prova encontrou antes da prova: partições

O primeiro teste de integração com velas de 6 dias atrás falhou com `no partition of relation
"candles_1m" found for row`, e o mesmo aconteceu **no stack local** no primeiro minuto do consumidor
ligado: `create_partitions.py` provisiona o mês corrente e os **seguintes**, então um pedido de 7 dias
no dia 6 do mês nomeia minutos de agosto que nenhuma partição aceita. Inserir aborta a transação
inteira (velas + outbox + transição de status do gap) e o gap gastaria suas cinco tentativas numa
condição que nenhuma retentativa conserta.

`partitions.storable_months` pergunta antes: os meses sem partição não são planejados, o log diz
`unstorable_minutes` e, se a janela inteira for insalvável, o pedido é recusado com `no_partition` —
sem marca, para ser reavaliado quando as partições existirem. Foi por isso que `accepted` deixou de
ser o nome do desfecho quando algo ficou de fora: um pedido real da prova entregou 5 247 minutos e
deixou 3 300 sem partição, e chamar aquilo de `accepted` teria escondido o problema.

## 30. Testes (39 novos, em três arquivos)

`tests/test_backfill_plan.py` (17, sem docker): semiaberto → inclusivo, clamp na detecção, futuro,
vazio, timestamp ingênuo, segundos truncados, teto de 7 dias, subtração de velas, fusão sobre velas
presentes, **não** fusão sobre gap existente, janela completa, teto de linhas com adiamento medido.
`tests/test_backfill_priority.py` (6, Postgres): ordem por minuto mais novo, histórico não toma o
orçamento do vivo, histórico usa a sobra sob teto próprio, fronteira exata do estrato, lacuna de 6
dias **é** drenada (o que não acontecia antes), prazo estourado não gasta tentativa.
`tests/test_backfill_consumer.py` (16, Postgres + Redis): pedido → lacunas → REST falso → 120 velas
`source=rest` → **120 linhas de outbox** `market.candles.closed`; repetição não refaz REST; fora do
shard ignora sem marca; fora do universo recusa **e é atendido quando volta com o mesmo `event_id`**;
janela futura; teto de 7 dias; mensagem malformada em quarentena com a próxima servida; payload
inválido; timeframe não suportado; mercado desconhecido; outra exchange; mês sem partição; reentrega
não duplica; dois planejadores concorrentes escrevem um conjunto só; `XINFO GROUPS` com lag 0; e um
teste de contrato que publica com o **produtor real** (`hunter_scanner_worker.backfill`,
`importorskip`).

## 31. O que fica como requisito para outras tarefas

- **Job de partições (`infra/scripts/create_partitions.py`, infra/ops):** provisionar meses **para
  trás** (pelo menos 1) ou aceitar que todo backfill no começo do mês perde a parte do mês anterior.
  Medido: 3 300 de 8 547 minutos de um pedido real (§29).
- **T2.9 / dono da outbox:** anunciar *cada* minuto backfillado pelo mesmo caminho da vela ao vivo é
  o gargalo de vazão do bootstrap (§28) e ainda coloca anúncios de histórico à frente de velas vivas
  na ordem `created_at`. Ou o backfill ganha um caminho de anúncio próprio (ou nenhum, já que o
  scanner lê candles do Postgres para o bootstrap), ou a vazão do bootstrap fica presa em ~1 dia de
  histórico por minuto de relógio. **Não decidi sozinho:** é contrato da T2.9.
- **`hunter_core.events.consume`:** a tolerância a mensagem ilegível (§27) devia ser do core.
- **Operação:** trocar `MARKET_SHARD=i/N` exige remover os grupos antigos
  (`XGROUP DESTROY market.backfill.requested market-worker.backfill.binance.{i}of{N_antigo}`) depois
  de confirmar que não há pendências.

**A revisão de diff desta tarefa está no §32**, mais abaixo: a seção T2.5c foi intercalada aqui
por outra tarefa em voo enquanto esta ainda escrevia.

---

# T2.5c — o contexto que sobrevive ao tick

Terceira parte. A T2.5b fechou com **p99 > 21 s** contra o alvo de 3 s da decisão conjunta e
entregou a causa medida à T2.2b: 77–89 % do custo por mercado era `decode_candles`. Esta tarefa
ataca esse item e mede o que sobra. Segunda opinião de desenho:
`.claude/state/astra-review-T2.5c-context.md` (6 perguntas), e ela **derrubou o meu desenho** — o
que está na árvore é o dela.

## 22. O desenho que eu levei, os três contraexemplos que o mataram, e o que ficou

Levei uma **janela persistente com fusão**: guardar as velas decodificadas por mercado, ler só as
16 linhas mais novas por tick (`hot_state_candles.CANDLE_FAST_WINDOW`), fundir por `open_time`, e
invalidar por evento (`market.candles.closed` com `open_time` no passado), por regressão de
cobertura e por ressincronização periódica. A Astra recusou com três cenários **concretos**, e cada
um é um jeito diferente de a lista do Redis mudar sem ninguém anunciar:

1. **vela WS mais velha que as 16 mais novas** entra por `_push_candle_full_rewrite` e reescreve o
   miolo da lista; o evento durável só sai depois (`ingest.py:179` escreve no Redis **antes** de
   enfileirar), então há uma janela em que a leitura curta não vê a mudança e a leitura inteira vê;
2. **REST antes, WS depois:** o backfill já inseriu a linha no Postgres e o `INSERT … DO NOTHING`
   não produz um segundo evento (`persist_rows.py:133`), então a vela WS que preenche aquele minuto
   no Redis **não é anunciada** para ninguém;
3. **a chave que o Redis perdeu** (eviction, `FLUSHDB`, um `LTRIM` externo) e que volta com uma
   linha só: uma fusão preserva 1 499 velas que o Redis não tem mais. Uma união nunca *remove*.

A conclusão dela — "'só o WS escreve' não implica 'toda escrita relevante é anunciada'" — está
certa, e a alternativa que ela propôs é melhor que a minha em todos os eixos menos um:

> **continue lendo a lista inteira; reaproveite o objeto decodificado quando a linha for
> byte-idêntica.**

É o que está implementado (`hunter_scanner_worker/hotcache.py`). A sequência é **reconstruída das
linhas recebidas** a cada tick, então remoção, reordenação, reescrita histórica e truncamento saem
corretos por construção: não existe regra de invalidação para errar, e o que a lista perdeu o cache
perde na mesma passada. O eixo que se perde é o tráfego — as 3 500 linhas continuam viajando do
Redis a cada tick, e a §25 mostra que **é isso que sobrou como gargalo**.

A chave é a **linha crua**, não o minuto: é a única coisa que prova que a linha não mudou, e achar
o `open_time` exigiria desempacotar (parte do custo) e reimplementar a precedência do escritor
(`_candle_may_replace`). Linha nova → decodificada **pela função de produção**, uma linha por vez
(`decode_candles((row,), …)`), para que este módulo não possa discordar do loader.

## 23. O que o cache prova, e como

Cadeia de dois elos, os dois testados:

- `tests/test_hotcache.py` — um cache **novo** responde **exatamente** o que `decode_candles` /
  `decode_trades` respondem, para toda forma que os loaders têm opinião sobre (vazio, truncado,
  vela em formação, linha corrompida, linha depois do corte). Igualdade de `SourceEntry`, não de
  amostra;
- `tests/test_context_identity.py` — um cache **mantido** responde o que um novo responde, ao longo
  de 60 minutos sintéticos com buraco, backfill reescrevendo o miolo, vela em formação atualizada
  dentro do minuto e o anel deslizando em 1 500. Compara `FeatureVector.canonical_bytes()` **e**
  `canonical_json(FeatureState.as_wire())` em cada corte, e um segundo teste compara o
  `MarketContext` **inteiro** (janela, `truncated`, fontes), porque uma divergência em dado que
  nenhuma feature lê hoje não apareceria nos bytes do vetor e apareceria no dia em que alguém ler
  (exigência da Astra).

## 24. Memória: medida, não estimada — e por que 1 500 velas ficam

`tracemalloc`, medido, com o teste que o afirma (`test_the_resident_cost_of_one_market_is_measured_not_estimated`):

| | |
|---|---|
| Por vela residente | **2 357 B** (dos quais 311 B são a linha crua guardada como chave) |
| Por mercado (buffer cheio de 1 500) | **3,4 MiB** |
| 200 mercados | **674 MiB** |
| No teto de guarda `max_markets = 400` | ~1,3 GiB |
| Tape (2 000 linhas por mercado) | +~0,6 MiB por mercado, ~128 MiB nos 200 |

A T2.2b estimou 1 625 B/vela e ~487 MB; o número real é 38 % maior.

**Fica em 1 500.** Encurtar a janela era a alternativa óbvia e ela **muda os números**, não só a
memória: `relative_volume_1h` pede 60 × 24 = **1 440 velas finais**, e 1 440 linhas *incluindo* a
vela em formação deixam 1 439 — a feature ficaria indisponível durante a formação de todo minuto
(achado da Astra; a folga das 1 500 é deliberada, `volume.py:14`). E `windows._bars_15m` usa
`run // 15` barras de todo o rabo contíguo: 1 500 minutos são 100 barras de 15 min, 1 440 são 96 —
muda a ancoragem fria do ATR. Economia: **4 %** (~19,5 MiB nos 200 mercados). Não se troca
identidade de resultado por 4 % de memória.

O alvo é a VPS Contabo (12 vCPU, 47 GB — `.claude/state/vps.md`), então 674 MiB residentes são
0,6 % da máquina. Um teto por LRU de mercados foi considerado e recusado: com 200 mercados
continuamente ativos, qualquer capacidade abaixo de 200 transforma cada passada em uma sequência de
reconstruções (concordância com a Astra).

## 25. O que a medição achou depois que o decode saiu do caminho

A ordem dos gargalos mudou três vezes nesta tarefa, e cada mudança veio de uma medição, não de um
palpite. Custo de **um mercado, um tick**, medido **dentro do contêiner** contra o Redis real
(`docker exec … probe2.py`, 5 mercados líquidos, listas cheias):

| | frio (1ª passada) | quente |
|---|---|---|
| `read_hot_state` (Redis → Python) | 20,7 ms | **16–21 ms** |
| decodificar 1 009 velas | 36,7 ms | **0,6–0,9 ms** |
| decodificar 2 000 trades | 25,0 ms | **0,7–1,0 ms** |
| book + derivativos | 0,2 ms | 0,2 ms |

Os dois caches entregam ~40×. **O que sobrou é a leitura**, e ela é grande por um motivo verificado:
`redis.connection.HIREDIS_AVAILABLE` é **False** na imagem — o parser RESP em Python puro percorre
~3 000 linhas por mercado por tick. *(Tentei medir o ganho do `hiredis` no contêiner e não consegui
instalá-lo lá: a imagem tem um venv sem `pip` e sem `uv`. Então isto é hipótese com uma causa
medida, não um número — e a mudança é `packages/core/pyproject.toml`, fora deste brief.)*

No banco de testes (Windows, `tests/test_load.py`, 200 mercados com **hot state cheio**, 1 500 velas
e 2 000 trades cada):

| | T2.5b | T2.5c |
|---|---|---|
| custo por mercado (p50) | 66,6 ms | **13,4 ms** |
| passada completa (p99 de 5) | 15,1 s | **3,23 s** |
| passada fria (200 mercados sem cache) | — | 19,4 s |

**A fixture estava medindo o vazio** e isso foi corrigido primeiro (item 3 do brief): ela semeava as
velas de BTCUSDT sob a chave de todos os símbolos, `build_context` descartava as 1 500 como de outro
mercado e o motor rodava sobre um contexto **vazio** — 31,5 ms/mercado na T2.5, 66,6 ms depois de
semear cada símbolo sob a própria chave. O número piorou porque passou a existir. A fixture também
passou a semear um tape **cheio** (2 000), que é o que 75 % do universo real tem (medido:
`LLEN` de 238 chaves `mkt:binance:*:trades` → p25 = p50 = p75 = max = 2 000).

O `xfail(strict=True)` **fica**, com o número novo: 3,23 s contra 3,0 s, 8 % fora. As duas maiores
parcelas do que sobrou estão **fora deste serviço**: `build_context` varre, ordena e deduplica as
1 500 velas e `MarketContext.__post_init__` revalida as 1 500 velas e os 2 000 trades — a cada tick,
para um corte que andou um segundo (~3,1 ms perfilados por mercado, somados). O remédio é um caminho
de construção para um contexto cujas fontes **já foram conferidas**, e isso é `packages/**`.

## 26. As janelas derivadas atravessam o tick (e o cinto de segurança disso)

O memo por contexto da T2.2b (`minute_index`, `bars_15m`) morria com o contexto, e o contexto morre a
cada tick — então dobrar cem barras de 15 min acontecia 60 vezes por minuto para um histórico de
minutos que muda **uma** vez por minuto. `HotCache.adopt` transporta essas duas entradas para o
contexto seguinte quando `final_candles` é igual (comparação por valor que o `tuple.__eq__` resolve
por identidade, porque as velas vêm do cache). Medido: 16,7 → 10,9 ms por mercado no banco de
testes; 13,4 ms com o tape cheio.

Três coisas fazem disso uma otimização e não uma aposta:

1. **Lista branca, nunca o memo inteiro** (`CARRIED_WINDOWS`). As duas entradas de hoje são funções
   de `final_candles` **só** — verificado em `windows._build_index` e `_bars_15m`. Uma derivação
   futura que dependa de `as_of`, da vela em formação ou do livro simplesmente não viaja: ela é
   recalculada, o que é apenas mais lento;
2. **um teste afirma a pureza contra o próprio `windows`**
   (`test_the_carried_windows_depend_on_the_minutes_and_on_nothing_else`): dois contextos com os
   mesmos minutos e `as_of`/forming diferentes têm de derivar as mesmas barras. No dia em que isso
   deixar de valer, quebra aqui — não num vetor;
3. **o teste de identidade de 60 minutos roda com o transporte ligado.** Ele é o aceite.

Ressalva registrada: `MarketContext.memo` é documentado como "nasce com o contexto, morre com ele", e
este módulo escreve nele de fora. É uma dependência do scanner num detalhe de outro pacote, aceita
com os três guardas acima e **declarada** aqui para quem mexer no memo.

## 27. Bootstrap: prioridade dinâmica em vez de fatia fixa

A T2.5b deu ao bootstrap 40 % do relógio por *duty cycle*. Uma repartição fixa gasta a sua parte
qualquer que seja o atraso, e o orçamento defendido é a **idade de um tick**. Agora
(`hunter_scanner_worker/pressure.py` + `BootstrapJob.run_slice(pressure=…)`):

- **suspende** quando o mercado sujo mais velho passa de **1 s** (uma cadência de features: esse
  mercado já perdeu o próprio ritmo) e **volta** abaixo de **0,5 s**. A histerese existe para não
  oscilar entre duas fatias;
- a pergunta é feita **em toda fronteira cooperativa** que o replay já tinha, não só na entrada:
  uma visita tem orçamento de 120 s, e perceber o atraso só na entrada deixaria o bootstrap segurar
  o loop por dois minutos depois de o scanner ficar para trás (correção da Astra);
- suspender é **pausar**, nunca cancelar: o gerador e o coletor sobrevivem, porque recriá-los
  reancoraria a recursão de Wilder e pagaria os cortes de novo (T2.5b §12);
- o **refresh horário não é regulado** — é limitado e é a única coisa que mantém o arquivo atual;
- `hunter_scanner_bootstrap_suspended` publica o estado. Na prova de 30 min ele ficou **1 o tempo
  todo**, que é a resposta certa para um loop que está permanentemente atrasado — e é também a
  confissão de que, neste stack, o bootstrap não avança enquanto o custo por mercado não cair
  (registrado na prova, não escondido).

Divergência com a Astra: ela sugeria `1 s / 0,5 s` como "hipóteses de tuning"; adotei exatamente
esses valores e amarrei o de suspensão ao `feature_throttle_s`, para que a explicação seja um
número do produto e não um gosto.

## 28. A fronteira da medição mudou de lugar

`scanner_tick_to_opportunity_seconds` era observado **dentro** de `Scanner.advance`, antes de
`features.updated` e da linha do Radar saírem — as duas projeções ficavam fora do número que existe
para limitá-las (achado da Astra). Agora a amostra é tirada no `evaluation_loop`, **depois** do
publish, com o `last_input_ts` capturado antes do `advance` (que limpa a sujeira). `Evaluation.scored`
diz se o throttle do score deixou a observação chegar ao scorer, porque é isso que define se houve
oportunidade para medir. Teste: `test_the_latency_sample_is_taken_after_the_projections_are_published`
prova a ordem espionando o publish e lendo o `_count` do histograma no meio dele.

## 29. Suposições numéricas novas

1. `SUSPEND_S = 1,0` (= `feature_throttle_s`) e `RESUME_S = 0,5` (§27).
2. `_IDLE_S = 0,05` — quanto um replay suspenso dorme entre duas olhadas no backlog quando o duty
   cycle não lhe dá pausa própria (`duty = 1`).
3. `WARMUP_CEILING_S = 20` no teste de carga: teto da passada fria, reportado à parte do orçamento.
4. Janela de velas mantida em **1 500** (§24), tape em `TRADES_MAXLEN = 2 000` — nenhum dos dois é
   escolha nova, os dois passaram a ser escolha **medida**.

## 32. [T2.5-backfill] Revisão de diff da Astra — três must-fix, três corrigidos

> Continuação da seção **T2.5-backfill** (§22–§31, acima). Este arquivo é um log compartilhado e
> outra tarefa em voo (T2.5c) intercalou a sua própria seção entre as duas metades desta.

`.claude/state/astra-review-T2.5-backfill-diff.md`. Veredito: **REQUEST_CHANGES**, e os três achados
são reais. O que mudou depois dela:

1. **HIGH — a cauda não liquidada recebia marca definitiva.** `normalize_window` recortava o fim da
   janela contra `detection_last` e **esquecia** o recorte; `final` era `plan.complete`. Cenário
   dela: pedido `[10:00, 10:30)` com `detection_last = 10:05` planejava seis minutos e marcava o
   evento inteiro como processado — a republicação depois das 10:30 seria descartada pela guarda e
   **ninguém jamais planejaria os 24 minutos restantes**. (A detecção periódica os pegaria por
   estarem recentes, mas isso conserta o dado, não o contrato do consumidor.) Corrigido:
   `Window.clamped_minutes` conta o recorte, ele entra no `left_out` e `final = left_out == 0`. Note
   a assimetria deliberada: o teto de 7 dias corta o **passado** e é definitivo (política); o clamp
   corta o **futuro próximo** e é temporário. Testes:
   `test_the_unsettled_tail_is_counted_and_not_forgotten` e
   `test_a_window_whose_end_has_not_closed_yet_is_not_marked_processed` (o `event_id` não é marcado).
2. **HIGH — 30 s não limitavam a operação inteira nem respeitavam a próxima detecção.** O prazo
   nascia *depois* do estrato vivo e só limitava o fetch. Cenário reproduzido por ela: vivo gasta
   45 s, histórico gasta 8 s de banco + 20 s de REST + 8 s de banco = ciclo de 81 s. Corrigido em
   duas partes: (a) `history_deadline(cycle_start, now)` devolve o **menor** entre "30 s a partir de
   agora" e "o fim do ciclo de 60 s menos 5 s de margem" — no cenário dela, 10 s; (b) o prazo embrulha
   a **unidade inteira** (`asyncio.timeout(remaining)` em volta de `recover_one`), não só o fetch. E
   o `timeout_s` do fetch voltou a ser o do adaptador: se quem cortou foi o **ciclo**, o cancelamento
   vem do prazo de fora, a transação faz rollback e o gap **não gasta tentativa** — cobrar do gap a
   lentidão do nosso ciclo era exatamente o que ela pediu para não fazer. Testes:
   `test_the_history_deadline_is_the_cycle_end_when_live_collection_was_slow` (com os números dela) e
   `test_a_unit_that_outlives_the_budget_does_not_spend_an_attempt`.
3. **MEDIUM — havia um terceiro escritor de lacunas fora do protocolo.** `persist.report_losses`
   também lê cobertura e insere gaps (a vela final que a fila descartou), e não participava da
   serialização: uma vela descartada e um pedido de backfill leem "faltando, sem gap" ao mesmo tempo
   e os dois inserem. Corrigido com o mesmo `lock_gap_planning` antes da leitura — o que exigiu
   ampliar o escopo para `persist.py` (dentro de `services/market-worker/**`). Teste:
   `test_a_dropped_candle_and_a_request_do_not_open_two_gaps_for_one_minute`.

**Nice-to-have aceitos e feitos:**

- O teste de timeout do fetch **não testava nada** desde a extração: ele fazia `monkeypatch` de
  `recovery.FETCH_TIMEOUT_S`, mas `recover_registered` liga o padrão em `recovery_drain`, então o
  `sleep(10)` do adaptador simplesmente retornava antes dos 20 s e as asserções passavam sem
  timeout nenhum. Agora o teste passa `timeout_s=0.05` explicitamente. **Achado meu no mesmo
  arquivo:** o `sed` da extração renomeou `test__recover_one_...` para `testrecover_one_...`;
  corrigido (o nome voltou a começar por `test_`).
- `outcome_name` e a marca não podem discordar: o nome agora sai de `left_out` (adiados + bloqueados
  + sem partição + não liquidados), que é a mesma condição de `final`. Teste:
  `test_the_word_and_the_mark_never_disagree`.
- Prova de progresso entre republicações depois do teto de linhas:
  `test_a_second_pass_plans_the_holes_the_row_budget_deferred` — as linhas da primeira passada viram
  cobertura e a segunda planeja as mais antigas, **sem** o produtor inventar outra identidade.

**Registrado, não implementado:**

- Ela recusa atribuir o `TimeoutError` de 10 s no flush à minha contenção **e tem razão**: o
  `wait_for` cobre `flush_batch` inteiro e o relato não separa fases nem espera de lock. Fica como
  "causa indeterminada" na prova, não como diagnóstico.
- "240 é tamanho de lote, não garantia de prontidão": dois chunks rápidos somam 480 anúncios antes da
  drenagem. O que o número **garante** é o teto por ciclo (6 × 240 = 1 440) e o que a prova mediu é
  `outbox_pending = 0` ao fim com `/ready` verde — evidência, não promessa. O remédio de verdade é o
  item da T2.9 no §31.
- A referência de **30 dias** do regime não cabe em um pedido: o teto de 7 dias é política e alguém
  precisa pedir o resto em outras janelas. Está dito no `PIPELINE.md` §1b e é decisão de produto, não
  de worker.

## 30. O que ficou como requisito para outras tarefas (T2.5c)

Todos com número medido na prova (`t25-proof.md`, T2.5c), e nenhum dentro de
`services/scanner-worker/**`:

1. **`hunter_core.events.consume` — o consumidor de `market.ticks` é hoje o dono do p99.**
   151 mensagens/s produzidas contra **~71/s consumidas**, lag estacionado em ~95 000 (o `MAXLEN`
   de 100 000 apara o resto), ou seja **~10 minutos** de atraso permanente numa fila cujo consumo
   custa um `touch` num dicionário. O suspeito medido é o custo por mensagem do envelope + guarda de
   `event_id`. Duas saídas possíveis, e a escolha é de desenho, não de worker: (a) tornar o consumo
   em lote (uma verificação por lote em vez de uma por mensagem); (b) para um stream de
   **notificação** — e `consumers.py` já declara que ticks não têm efeito durável e que perder um
   não custa nada — pular o acumulado em vez de drená-lo mensagem a mensagem (`XGROUP SETID … $`
   acima de um limiar de lag). Não implementei: muda a semântica de consumo e merece brief próprio.
2. **`packages/core/pyproject.toml` — `redis[hiredis]`.** `HIREDIS_AVAILABLE = False` na imagem, e
   a leitura do hot state custa **16–21 ms por mercado por tick** para ~3 000 linhas com o parser
   RESP em Python puro. Hipótese com causa medida (não consegui instalar `hiredis` no contêiner
   para medir o ganho: o venv da imagem não tem `pip` nem `uv`).
3. **`packages/indicators/hunter_indicators/features/context.py` — um caminho de construção para
   fontes já conferidas.** `build_context` varre/ordena/deduplica 1 500 velas e
   `MarketContext.__post_init__` revalida 1 500 velas + 2 000 trades **a cada tick**, para um corte
   que andou um segundo: ~3,1 ms perfilados por mercado. É o que falta para o teste de carga passar
   (3,23 s contra 3,0 s).
4. **Leitura incremental do tape (desenhada, não entregue).** `hot_state_trades.push_trade` é
   estritamente `LPUSH` + `LTRIM` — append-only —, então ler as K linhas mais novas e checar
   sobreposição pela linha que já era a cabeça **é** decidível, e o descarte da cauda é exatamente
   `n` linhas por `n` chegadas. Isso corta ~2 000 das ~3 000 linhas por tick. Não vale para as
   velas (reescrita no miolo, §22), e por isso não entrou junto: é um segundo desenho, com os
   contraexemplos da Astra para responder de novo.
5. **`market-worker`: `mkt:coverage:binance` congelado** (prova §6) — 41 min sem carimbo com o tape
   fresco, e por isso 100 % das avaliações da janela saíram `uncovered`. Sintoma e hora registrados;
   o arquivo é de outra tarefa em voo.

## 31. Revisão de diff da Astra — três must-fix, três corrigidos

`.claude/state/astra-review-T2.5c-diff.md`. Veredito dela: **REQUEST_CHANGES**, com "aceito o cache
por bytes e o transporte restrito do memo". Os três:

1. **O cache do tape mudava quais linhas o loader aceita** (o único defeito real de equivalência do
   diff, e eu não tinha visto). `decode_trades` lê `side` **depois** de descartar a linha pelo
   corte, então uma linha carimbada no futuro com `side` inválido é silenciosamente pulada por ele —
   e o meu decode adiantado (corte `_NEVER`) levantava `ValueError`, o que derruba o ciclo inteiro
   (`runners.py`, o `except` abandona o resto da passada). Corrigido com um terceiro veredito,
   `DEFERRED`: a linha que não decodifica sem corte não é cacheada como recusa, é entregue ao loader
   **no corte real** a cada tick — pulada enquanto está no futuro, levantando no instante em que o
   corte a alcança, exatamente como o loader. Teste novo, com os dois cortes.
2. **`scored` não provava publicação.** `publish_radar` volta sem escrever quando não há score
   utilizável **e engole exceção do Redis** — então o histograma dizia "oportunidade publicada em
   N s" para uma linha que ninguém viu. `publish_radar` passou a devolver três veredictos
   (`RADAR_WRITTEN` / `RADAR_NOTHING` / `RADAR_FAILED`); a amostra só sai quando não foi
   `RADAR_FAILED`, e o texto da métrica passou a dizer o que ela mede. Teste novo com um Redis que
   recusa o `zadd`. **Divergência parcial registrada:** ela mediria só publicações de verdade, o que
   deixaria o histograma quase vazio nesta fase (4 oportunidades em 200 mercados); mantive a amostra
   para o ciclo que terminou sem ter o que projetar, porque é um ciclo concluído e é o que torna o
   número comparável com as provas T2.5/T2.5b — e escrevi isso no `help` da métrica.
3. **A prova afirmava mais do que mostrava.** Os dois pontos aceitos e corrigidos no
   `t25-proof.md`: (a) "6 400 = nenhum minuto perdido" virou a contagem por **par (mercado,
   minuto)** — 6 200 pares, **199 mercados com os 31 minutos**, e os dois que faltam são a troca de
   universo das 20:38:58 (`VETUSDT` entrou, `ROBOUSDT` saiu), o que também explica os "201 mercados
   distintos"; (b) a atribuição do p99 ao consumidor virou sintoma + correlação, porque
   `last_input_ts` guarda o **maior** carimbo entre os gatilhos e um fechamento recente substitui o
   de um tick atrasado.

Nice-to-have aceitos: o contador de decode passou a ser delta **por mercado** (a soma global perdia
incrementos quando um mercado saía do universo); `LivePressure` recebe os limiares do
`ScannerConfig` em vez de constantes próprias; um teste em que a pressão sobe **dentro** da mesma
chamada de `run_slice` (o anterior mudava a pressão entre chamadas e ficaria verde sem a checagem
interna); e o teste de pureza do memo passou a atravessar fronteiras de 15 minutos, não só dois
instantes do mesmo minuto.

**Divergência registrada (consumo):** ela defende consumo em lote em `hunter_core.events.consume`
(uma ida ao Redis por lote, mantendo uma decisão por `event_id`) e **recusa** `XGROUP SETID $` como
primeira correção, com um cenário que eu aceito: perder dezenove notificações quando a vigésima
marca o mercado não é o mesmo que perder **todas** — um mercado pouco ativo pode ter a única
notificação dele no trecho pulado. Registro a preferência dela no item 1 do §30 e não implementei
nenhuma das duas: é `packages/core/**`.

Ela também recusa atribuir os 16–21 ms de leitura inteiramente ao parser, porque `read_hot_state`
mede o pipeline inteiro (transporte + espera no loop). Concordo, e o §25 já dizia que o ganho do
`hiredis` **não foi medido**; o §30 mantém a hipótese com a causa medida ao lado.

**[T2.5-backfill] Correção do meu próprio remédio (registrada porque a prova a encontrou):** pôr `report_losses` sob
o lock **bloqueante** o fez esperar dentro do `drain_loop`, que roda uma vez por segundo, atrás de um
ciclo de detecção que lê 200 mercados — `market_persist_lag lag_s=14,4` e 4 flushes estourando o
timeout em 7 min. Trocado por `pg_try_advisory_xact_lock`
(`recovery_queries.try_lock_gap_planning`): quem não pega o lock não escreve nada, não drena nada e
tenta na iteração seguinte. O relatório de perdas é best-effort por contrato (H1); o flush não é.

**[T2.5-backfill] Rodada 2 da Astra: APPROVE, com três caminhos de `partial` sem conclusão que ela
pediu para registrar** (`.claude/state/astra-review-T2.5-backfill-diff2.md`). Não são defeitos deste
consumidor; são limites de progresso do sistema, e estão aqui para quem for depurar "por que este
pedido volta toda hora":

1. **Mês antigo sem partição:** os minutos continuam bloqueados mesmo depois de a parte armazenável
   ser recuperada. Some quando o job de partições provisionar meses para trás (§31).
2. **Fonte permanentemente vazia:** o gap alterna tentativa → `failed` → reabertura de hora em hora,
   e enquanto existir ele bloqueia o pedido. O `market_gap_history_starts_later` cobre o caso em que
   a exchange devolve dado começando depois; o caso "nunca devolve nada" não tem cura local.
3. **Orçamento sempre curto:** com o vivo consumindo as vagas ou o relógio, uma unidade histórica que
   precise de mais tempo do que sobra pode ser cancelada repetidamente — sem gastar tentativa (por
   desenho), mas também sem progredir. É visível em `market_backfill_budget_spent` e
   `market_backfill_unit_timeout`; o remédio é reduzir a fila viva, não afrouxar o prazo.

Também aceitei a ressalva dela sobre o `try-lock`: "fica na fila para a próxima iteração" não é
retenção ilimitada — o deque de perdas é limitado (`maxlen`) e uma contenção longa pode evictar uma
perda antes de ela ser reportada. Isso degrada o *relato*, não reintroduz a duplicidade do MF3.
