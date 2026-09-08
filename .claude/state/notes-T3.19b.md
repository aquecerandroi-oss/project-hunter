# Notas T3.19b — o motor de replay histórico (500 mil validações/dia)

Base: `main` em `5c97b18`. **Nada commitado.** Caminhos tocados (só os meus):
`services/strategy-worker/hunter_strategy_worker/replay/{environment,simulate,candles,ledger,budget,plan,run}.py`,
`services/strategy-worker/hunter_strategy_worker/{persist,tracking_repo,context,decide}.py`,
`services/strategy-worker/tests/{test_replay_contract,test_replay_engine,test_replay_lookahead}.py`,
`docs/PIPELINE.md` (§6c novo), `docs/DEPLOYMENT.md` (§5.2 novo), `docs/plans/REPLICATION.md`
(§3.5 novo, §9 reescrito), `.claude/state/brief-T3.19b-db-replay-runs.md` (brief para a
database-architect). Nada em `infra/migrations/**`, `services/execution-worker/**` (só leitura de
`bridge_screen.py`), `apps/**`, `obsidian/**`, `.env*`.

---

## 1. A decisão central: reusar `evaluate_slot`, não reimplementar nada

O brief pedia "reuse the live evaluation function, never a second implementation". A leitura
literal seria copiar o laço de decisão; a leitura correta é **chamar a função viva**. Uma barra
replayada é uma chamada a `hunter_strategy_worker.decide.evaluate_slot` — a mesma que
`consumer.handle_candle` faz quando uma vela fecha. O replay fornece só os dois pontos que essa
função já lê do mundo:

| Costura | Como o replay a preenche | Por quê |
|---|---|---|
| `clock` | `ReplayClock(bar_close, lag_s=2)` — já era parâmetro de `evaluate_slot` (a docstring dele cita "a replay cohort") | põe a decisão a 2 s da barra: a entrada cai na abertura de `bar_close + 1min` e `delay_s = 60 ≤ max_entry_delay_s = 120`. Congelado por barra: duas leituras do relógio na mesma barra dão o mesmo instante |
| `redis` | `ReplayHotState` — três métodos (`xrevrange`, `lrange`, `hgetall`) que respondem vazio | para uma barra de dias atrás o tail já seria vazio (o corte descarta ≥ `source_bar_close`); a sonda de universo é o único ponto onde isso é **suposição** e não fato — está declarada abaixo |

Sai de graça, por reuso: corte em `source_bar_close`, só `is_final`, máquina de slot e barreira de
re-arme, `plan_entry`, `assumed_costs`, `build_record`, identidade `uuid5` com a coorte dentro,
`walker.walk` e `settle.settle` (funding com o mesmo motivo quando não dá para estabelecer).

**Colisão de nome declarada:** o brief pediu `replay/engine.py`, mas esse arquivo **já existe** e é
da R1 (dobra de políticas de saída sobre entradas congeladas, EXP-0004). Não editei o arquivo de
outro escopo: o motor novo é `replay/simulate.py`.

## 2. Quatro mudanças em arquivos vivos (todas minhas, todas mínimas)

1. **`persist.py` — um replay não escreve `shadow_outbox`.** `is_published_cohort(cohort)` é
   `False` para `replay:`; `prospective` e `replication:` continuam publicando. A regra fica no
   único ponto por onde toda decisão passa, e não num argumento que o chamador pode esquecer. A
   ponte já recusaria (`cohort_not_live`), mas publicar meio milhão de linhas/dia para serem
   recusadas uma a uma atravessaria um despachante cujo atraso é check de prontidão.
2. **`tracking_repo.load_open_trackings(cohort=...)`** — filtro opcional por `meta.cohort`. Sem ele,
   drenar os desfechos de um replay avançaria também os *prospectivos* com um relógio do passado.
   O varrimento vivo passa `None` e não muda.
3. **`context.build_market_context(candles_reader=...)`** e **`decide.evaluate_slot(candles_reader=...)`**
   — ponto de injeção **de custo, nunca de conteúdo**. O caminho vivo passa `None` e lê
   `repo.load_candles` como sempre.
4. Nada mais. `walker`, `settle`, `episodes`, `slots`, `record`, `identity` e as estratégias
   congeladas não foram tocados.

## 3. Onde estava o custo (medido, não estimado)

O primeiro número real foi **3,93 barras/s** com 3 processos. A instrumentação disse por quê:

```
round trip até o Postgres (SELECT 1, 50x, sessão aberta) = 44,88 ms
statements SQL por barra replayada                       = 11,25  (≈14,5 round trips com BEGIN/COMMIT)
load_candles (query + 1560 modelos pydantic), sessão quente = 95,18 ms
build_context a partir da memória                        =  4,04 ms
explain (volume_anomaly_v1, 1560 velas)                  =  2,62 ms
parede por barra, 1 processo                             = 654 ms   →  14,5 x 44,88 = 651 ms
```

Isto é **latência de rede do Docker Desktop no Windows**, não algoritmo: praticamente 100 % da
parede são round trips. A otimização que fiz mesmo assim é a que sobrevive à mudança de máquina:
`replay/candles.py` lê a fatia inteira do mercado **uma vez** e fatia em memória, o que remove os
~95 ms de releitura/revalidação por barra (barras consecutivas de 5 m compartilham 1555 dos 1560
minutos). Medido: 3,93 → 4,62 barras/s (+17,6 %) — pequeno aqui porque o resto é round trip, grande
onde o round trip é barato.

**A legitimidade da cache é um teste, não uma afirmação:** para cada corte da janela, o que ela
devolve é comparado com o que `repo.load_candles` devolve (`test_replay_engine.py::TestTheCandleCache`),
e um pedido fora do que ela carregou vai ao banco em vez de responder curto.

## 4. Prova real (2026-09-08)

O stack local **não pôde** ser usado como banco da prova, e isso contradiz o brief: o banco local
está em **`0011_strategy_activation_owner`**, não em `0012` (verificado: `select version_num from
alembic_version`), e `strategy_versions` não tem `promising_at`/`replication_parent_id`. O
`load_active_versions` do head seleciona essas colunas e falharia. Não apliquei migração num banco
compartilhado por outro agente. Usei o caminho que o brief autoriza como alternativa: **um Postgres
descartável meu** (`hunter-t319b-proof`, porta 15433, fora do stack, removido ao fim), migrado a
`head`, carregado com **velas reais exportadas por leitura do banco local** — 3 mercados perpétuos
(BTCUSDT, ETHUSDT, SOLUSDT), 64 179 velas de 1 m, `funding_rates` das mesmas. O stack local não foi
parado, recriado nem escrito.

**Uma premissa que precisei tomar:** o `code_ref` congelado das versões ativas de produção não bate
com o digest **deste** build (a árvore tem mudanças não commitadas de vários agentes), e o catálogo
recusa — corretamente — rodar código que a versão não nomeou. Registrei no banco de prova duas
versões `v9` com os `default_parameters` de `momentum v2` e `volume_anomaly v2` **byte a byte** e o
`code_ref` recongelado para este build. Mesmo código, mesmos parâmetros, velas reais; só o digest é
de hoje.

### 4.1 A corrida de 31 dias × 3 mercados (momentum, 15 m)

Janela `2026-08-08 → 2026-09-08`, coorte `replay:55555555-5555-4555-8555-555555555555`, 11 fatias
(passos curtos, `--from/--to`), `--workers 3`:

```
barras avaliadas   8 928  ( = 31 x 96 x 3, exatamente o planejado; 0 erros)
estados            unavailable 5 030 | not_triggered 3 757 | triggered 141
sinais                71   desfechos resolvidos 71   abertos 0   censurados 0   no_entry 0
resultados         invalidated 29 | target 24 | stop 16 | expired 2
funding            9 resolvidos (expectancy_r -0,8326) | 62 funding_schedule_unknown
                   (média r_ex_funding -0,2811)
mercados 3 | dias distintos de decisão 13
tempo              1 820,3 s (30,3 min)  →  4,90 barras/s com 3 processos
linhas de shadow_outbox das 5 coortes de replay:  0
```

`unavailable` é 56 % porque o backfill de 31 dias (T3.7b) **ainda não rodou**: as velas destes
mercados começam em `2026-08-24`. O motor conta a barra que não pôde avaliar em vez de fingir que
ela não existiu — que é o comportamento pedido.

### 4.2 As corridas de 5 min (volume_anomaly), 1 dia × 3 mercados

| Janela | Barras | s | barras/s | Sinais |
|---|---:|---:|---:|---:|
| 2026-09-01 → 09-02 (**sem** cache de janela) | 864 | 220,0 | 3,93 | 13 |
| 2026-09-02 → 09-03 (**com** cache) | 864 | 187,0 | 4,62 | 8 |

Densidade de sinais medida: **1,2 %** das barras avaliadas em 5 m, **1,8 %** em 15 m (141
`triggered` → 71 sinais: a diferença é o slot, que só admite um acompanhamento por mercado por vez).

## 5. A projeção para 500 mil/dia — e a resposta honesta

Na VPS o Postgres é contêiner na mesma máquina (`DEPLOYMENT.md` §9), round trip da ordem de 0,3 ms.
A barra passa a ser limitada por CPU:

```
barra_vps ≈ 15 ms de CPU (6,7 ms medidos aqui, com margem de 2x para a vCPU da Contabo)
          + 14,5 round trips x 0,3 ms
          ≈ 20 ms  →  50 barras/s por processo  →  150 barras/s com REPLAY_CPU_SHARE=0,33 (3 de 12 vCPU)
```

**Com 20 h/dia de replay: 10,8 milhões de barras avaliadas por dia.**

| "Validação" = ... | Produção/dia com o orçamento | Contra a meta de 500 000 |
|---|---:|---|
| **uma decisão simulada** (barra avaliada) | **10 800 000** | **21 × a meta** |
| **uma operação simulada com entrada e desfecho** (sinal + outcome) | **~160 000** (1,5 % de densidade) | **~1/3 da meta** |

Em versões × mercados × dias, que é como o brief pediu: uma versão de 5 min sobre 200 mercados e 31
dias = 1 785 600 barras ≈ 9,9 CPU-h ≈ 21 400 operações; uma rodada de replicação inteira (pai + 10
irmãs) sobre a mesma janela = 19,6 milhões de barras, **~109 CPU-h**, **~236 000 operações** — cerca
de **um dia e meio** dentro do orçamento de 3 processos. Custo em linhas: ~236 mil `agent_signals` +
236 mil `signal_outcomes` + 2 200 slots de episódio por rodada; com o tamanho médio de envelope de
hoje, da ordem de **1,5–2 GB** por rodada de 5 min (`agent_signals.supporting_features` é o grosso).
Zero linhas de outbox.

**A conclusão que o Everton precisa decidir:** meio milhão *de validações* por dia está entregue e
sobra, se validação for a decisão simulada. Meio milhão *de operações fechadas* por dia não cabe em
3 vCPU — exigiria ~10 vCPU dedicadas, o que faminta a coleta, que é a única coisa que **não** se
recompõe depois. Alavancas medidas, na ordem em que valem: (a) mais mercados (a massa é linear e
hoje são 200); (b) preferir 15 m a 5 m quando a hipótese permite (3 × mais barato por mercado-mês
para ~2/3 dos sinais); (c) uma cache de derivativos removeria 2 dos 11,25 statements por barra — só
importa onde o round trip é caro; (d) `context_minutes = 1560` é 60 % do CPU por barra, e reduzi-lo
**muda o experimento congelado** — não é decisão de engenharia.

## 6. Não-antecipação: como está provado

`test_replay_lookahead.py` é um **teste de mutação**, não uma inspeção. Uma barra é replayada duas
vezes sobre o mesmo banco; entre as duas, **toda** vela posterior a ela é reescrita (volume × 50,
preço × 1,5) e, num segundo caso, marcada `is_final = false`. A decisão — estado, stop, alvos,
confiança, motivo, horizonte e o bloco de features do envelope — tem de ser idêntica.

E há **contraprova**: o mesmo par de corridas é aplicado a um motor deliberadamente trapaceiro
(`build_market_context` monkeypatched para cortar em `bar_close + 30 min` enquanto continua
reportando a barra honesta). O teste **exige** que a trapaça seja detectada; e um segundo teste
mostra que a trapaça é invisível **sem** a mutação — que é exatamente como um backtest vazando se
parece quando ninguém perturba o futuro.

Custos: `test_the_costs_are_the_versions_own_and_not_the_replays` compara `meta.assumed_costs` do
sinal replayado com os `default_parameters` congelados da versão, campo a campo.

"Mesmo código, mesma resposta": `test_replay_engine.py::TestSameCodeSameAnswer` roda a **mesma
janela** sob `prospective` e sob `replay:` e compara barra, stop, alvos, confiança, motivo,
horizonte, estado, resultado, entrada, saída, instante da saída e `r_multiple`.

## 7. Decisões numéricas que tive de tomar (não vinham do brief)

| Decisão | Valor | Por quê |
|---|---|---|
| `REPLAY_DECISION_LAG_S` | **2 s** | qualquer lag < 60 s põe a entrada na abertura de `bar_close + 1min` (a mesma do dia saudável ao vivo) com `delay_s = 60`; ≥ 60 s moveria a entrada um minuto e mudaria a população. Zero seria `decision_at == bar_close`, que nenhuma corrida real alcança. Vai gravado em todo recibo |
| `REPLAY_CPU_SHARE` | **0,33** (→ 3 de 12 vCPU, `floor`) | deixa nove vCPU para coleta/scanner/estratégia/execução; `floor` e não arredondamento, para o replay nunca ganhar uma vCPU no desempate |
| `REPLAY_MAX_WORKERS` | 4 | teto absoluto: uma máquina maior não vira um experimento maior sem alguém decidir |
| `REPLAY_MAX_CONCURRENT_RUNS` | 1 | duas corridas entrelaçadas tornam o throughput de ambas ininterpretável |
| `heartbeat_max_age_s` / `outbox_lag_max_s` | 60 / 60 | espelham `heartbeat.TTL_S` e `SHADOW_OUTBOX_LAG_ALERT_S` — não inventei um segundo modelo de saúde |
| Unidade de paralelismo | **mercado**, em processos | o estado mutado é `(versão, mercado, coorte)`; dois processos no mesmo mercado disputariam o mesmo slot, e fatiar o mesmo mercado no tempo quebraria a barreira sequencial de re-arme |
| `DRAIN_MARGIN` | 2 min | `advance_tracking` dobra até `min(horizon_open, last_closed_minute(now))`; um relógio exatamente no horizonte pararia um minuto antes dele |
| Janela `[from, to)` | semiaberta | duas fatias adjacentes nunca visitam a mesma barra — repetir não corromperia (uuid5 + ON CONFLICT), mas dobraria o `bars` do recibo e o número de throughput seria mentira |
| Livro-razão | `system_events` + JSONL | `replay_runs` precisa de migração, que o brief proíbe aqui. Brief escrito: `.claude/state/brief-T3.19b-db-replay-runs.md` |
| Densidade de sinal para a projeção | **1,5 %** (faixa medida 1,2–1,8 %) | média das duas famílias medidas; a projeção de operações/dia é a única linha sensível a ela e está declarada |
| Round trip da VPS | **0,3 ms** (suposição) | é o único número da projeção que **não** medi: não tenho a VPS aqui. Postgres é contêiner na mesma máquina (§9 do DEPLOYMENT), então a ordem é essa; se for 3 ms, a barra vai a 58 ms e a produção cai ~3 × |
| Fator de CPU da VPS | **2 ×** mais lenta que o PC | margem conservadora sobre os 6,7 ms medidos; também não medido |

## 8. Concerns

1. **O banco local está em `0011`, não em `0012`** — o briefing afirmava `0012` aplicada. A `0012`
   está commitada em `5c97b18` mas o contêiner `migrate` do stack local rodou antes dela. Efeito
   real e imediato: **qualquer código do head que leia `strategy_versions` quebra contra o banco
   local** (`load_active_versions` seleciona `replication_parent_id`/`replication_index`), incluindo
   a API que o designer está rodando do código-fonte na 8010, se ela tocar essa tabela. Não apliquei
   a migração: é um banco compartilhado e não é o meu caminho. **Alguém precisa rodar
   `alembic upgrade head` contra o stack local** (ou recriar o `migrate`) — não é destrutivo
   (colunas nuláveis + um CHECK alargado), mas é decisão de quem opera o stack.
2. **O número de throughput desta máquina não é o número da VPS**, e a diferença é de uma ordem de
   grandeza. As 4,90 barras/s medidas são latência do Docker Desktop no Windows (44,88 ms por round
   trip, medidos). A projeção de 50 barras/s por processo depende de duas suposições declaradas no
   §7 (round trip 0,3 ms, CPU 2 × mais lenta). **A primeira coisa a fazer na VPS é rodar
   `--dry-run` e uma fatia de um dia e comparar** — o recibo já traz `bars_per_second`.
3. **A elegibilidade replayada é a de hoje.** `markets.is_monitored` é sobrescrito no lugar e não há
   histórico por barra no schema; a sonda `universe_changed_after` responde "sem mudança" no replay
   porque responder a verdade (toda barra histórica está atrás de alguma mudança de universo) faria
   **toda** barra virar `unavailable`. Isso está escrito na docstring do `environment.py`, no §6c da
   PIPELINE e aqui: um replay cobre o universo atual, não o da janela. É a limitação metodológica
   principal do motor.
4. **`funding_schedule_unknown` em 62 dos 71 desfechos da prova.** Não é bug do replay: copiei só 30
   linhas de `funding_rates` para o banco de prova, e o resolvedor recusa inventar cadência
   (`settle.py`). Numa corrida de verdade, sobre o banco real, a cobertura de funding é a mesma da
   faixa viva — mas vale medir: um replay de 31 dias precisa de histórico de funding de 31 dias + 3
   dias de folga por mercado, e ninguém verificou se o backfill traz funding junto com as velas.
5. **O `code_ref` das versões ativas não bate com este build.** O catálogo recusa rodá-las, o que é
   o comportamento certo, mas significa que **um replay das versões de produção não roda a partir
   desta árvore** — só a partir do build que as congelou. Quem for rodar na VPS tem de rodar com a
   imagem do commit que ativou a versão, ou reativar com o digest novo pelo script auditado. Isto
   não é da T3.19b, mas morde exatamente aqui.
6. **A `0012` amplia o CHECK de coorte, mas o motor de replay não depende dela**: `replay:<uuid>` é
   gramática da `0002`. Um replay roda contra `0011` **desde que** o `load_active_versions` do build
   corresponda ao schema — hoje não corresponde (concern 1).
7. **Não implementei a cache de derivativos** (2 dos 11,25 statements por barra). Medi, e onde o
   round trip é barato ela vale ~pouco; onde é caro vale 18 %. Fica declarada como alavanca, não
   como esquecimento — implementá-la é mais um ponto de injeção no caminho vivo, e o custo/benefício
   não justificou hoje.
8. **A fila (`replay:queue`) e o `--drain-queue` têm teste de contrato, não de integração com Redis
   de verdade.** A gramática do pedido, a recusa de coorte não-replay e o portão de prontidão estão
   testados puros; o `LPUSH`/`RPOP` contra um Redis real não está. É o pedaço menos exercitado da
   entrega.

## 9. O que revisar depois de mim

- **risk-engine-guardian:** que nenhuma linha escrita por um replay possa virar entrada. As três
  barreiras continuam (purpose, ausência de `agents`, coorte) e agora há uma quarta que é ausência
  de evento: um replay não escreve `shadow_outbox`. Vale checar se algum consumidor lê
  `agent_signals` **sem** filtrar coorte — a ponte filtra; o resto não foi auditado por mim.
- **code-reviewer:** as quatro mudanças em arquivos vivos do §2 (especialmente o `candles_reader`,
  que é um ponto de injeção no caminho de decisão) e a equivalência da cache.
- **database-architect:** `.claude/state/brief-T3.19b-db-replay-runs.md`.
- **Sexta-feira:** o §3.5 da REPLICATION.md é **proposta**. A pergunta para o Everton é dupla: (i)
  replay pode maturar o bloco 2 (irmãs)? (ii) "500 mil validações/dia" conta decisões simuladas ou
  operações fechadas? O §9 da REPLICATION.md tem a aritmética das duas leituras.
