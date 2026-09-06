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
