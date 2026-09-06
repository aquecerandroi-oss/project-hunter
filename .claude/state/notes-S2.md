# Notas de desenho — S2 (`strategy-worker` em modo sombra)

Decisões tomadas ao implementar `.claude/state/brief-S2-strategy-worker.md`, com a segunda
opinião da Astra (`.claude/state/astra-review-S2-worker.md`). Onde o plano era omisso, a escolha
está aqui com o motivo; onde diverge do brief, está marcado como **desvio**.

## 1. A barreira de rearme mora em `last_bar_close`
`shadow_episodes` não tem coluna para "quando o acompanhamento terminou", e o item 4 da decisão
conjunta exige que o rearme use uma barra com a condição falsa **posterior ao término**. Sem
migração nova (S0 está congelada), `last_bar_close` passa a ser uma **barreira**: a guarda de
avaliação é `bar_close > last_bar_close`, e no encerramento gravamos
`last_bar_close = GREATEST(last_bar_close, instante_do_término)`.

Consequência: uma barra que fechou **antes** do término mas foi entregue depois dele é recusada
(cenário "eventos fora de ordem" do brief). Custo aceito e declarado: `last_bar_close` deixa de
ser sempre um fechamento de barra e passa a ser "avançado até este instante" — o docstring do
modelo em `agents_shadow.py` descreve a coluna como "o fechamento avaliado", e essa semântica é
ligeiramente mais larga. A Astra aceitou com a ressalva de documentar (revisão S2, "o que eu
faria diferente", B). O instante do término é: a abertura, quando a saída é comprovada na
abertura; o **fechamento** da barra, quando o toque é intrabar (não inventamos o instante do
toque).

## 2. Ordem entre o motor de outcomes e a transição do slot
Achado da Astra (revisão S2, B): se a avaliação da barra rodasse antes de o motor de outcomes
processar uma saída já ocorrida, o resultado dependeria de qual laço rodou primeiro. `decide.py`
avança o acompanhamento aberto **até** a barra que está sendo avaliada e só então relê o slot e
aplica a transição, tudo sob o mesmo `SELECT … FOR UPDATE`.

## 3. Prova de que o commit precedeu a abertura (duas transações)
O instante do commit não é observável de dentro da transação e o Postgres não o guarda
(`track_commit_timestamp` desligado; `now()` é o início da transação). A prova é montada de
fora: `commit₁ concluído → lê o relógio t → t < entry_bar_open`. A segunda transação grava o
atestado (`meta.entry_plan.confirmed_at`); ela **não** precisa vencer a abertura, porque registra
um fato já estabelecido.

**Perda conservadora declarada:** um crash entre o commit e a confirmação faz o motor de outcomes
encerrar o acompanhamento como `no_entry: late:unconfirmed`. Perde-se uma entrada que teria sido
válida; nunca se cria uma entrada retroativa. É contável (`no_entry_reason` distingue
`late:delay`, `late:missed_open` e `late:unconfirmed`) e precisa aparecer nas contagens de
cobertura da S3.

## 4. Elegibilidade não é comprovável para uma barra antiga (`eligibility_max_lag_s`)
Must-fix 4 da Astra: `markets.is_monitored` é sobrescrito a cada refresh, então o valor de agora
não prova a elegibilidade de uma barra de uma hora atrás. Uma barra com
`now − bar_close > eligibility_max_lag_s` vira `unavailable` — não decide e **não rearma** —
em vez de fingir que o presente é o passado. O envelope registra
`provenance.eligibility_observed_at`.

**Interação com `max_entry_delay_s`: o gate é 300 s, o limite de atraso é 120 s.**
`max_entry_delay_s` vale **120 s** e é congelado nos `default_parameters` da versão; **300 s** é
o `eligibility_max_lag_s` deste módulo, que é operacional. (O título anterior desta passagem
dizia "`max_entry_delay_s` (300 s, não 120 s)" e trocava os dois — corrigido em 2026-09-06,
nice-to-have do risk-engine-guardian.) Com **os dois** em 120 s o ramo `no_entry: late:delay`
viraria praticamente inalcançável: a barra teria sido descartada como indisponível antes de a
regra de atraso falar, e essa população sumiria das contagens. Com o gate em 300 s e o refresh de
universo em 900 s, a leitura ainda está dentro de um mesmo ciclo.

## 5. Outcomes por polling do Postgres, não pelo stream
O `market-worker` publica `market.candles.closed` **antes** do flush durável
(`ingest.py`), então o stream prova que a vela existe, não que ela é durável, e não pode reentregar
o minuto que o processo perdeu enquanto estava fora. O motor lê a série durável e avança
estritamente contígua a partir de `meta.progress.last_bar_open`. O stream continua sendo o
gatilho das **decisões**.

## 6. Censura tem prazo, e o prazo é durável
Must-fix 2 da Astra: "existem velas posteriores" prova descontinuidade, não irrecuperabilidade, e
uma série que simplesmente para nunca satisfaria essa condição — o acompanhamento e o
`tracking_hold` ficariam abertos para sempre. O minuto que falta é registrado em
`meta.gap_wait = {minute, since, gap_status}` (sobrevive a restart) e o acompanhamento vira
`censored` com `gap:<minuto>:<motivo>`. Nunca vira `expired`.

**Revisado em 2026-09-06 (MUST-FIX 2 do risk-engine-guardian): o relógio deixou de decidir
sozinho.** Ver §16.

## 7. Blocklist vence o hold
Recomendação da Astra (E), aceita: o hold mantém a coleta de um mercado que saiu do **ranking**,
mas uma exclusão explícita do operador interrompe a coleta e os acompanhamentos ainda abertos
recebem censura administrativa identificada (`blocked:<símbolo>`). O contrário redefiniria a
blocklist como "bloqueia apenas novas decisões", e isso teria de ser uma decisão do dono, não uma
consequência silenciosa desta tarefa.

## 8. `tracking_hold` amplia coleta, nunca elegibilidade
`markets.is_monitored` continua sendo só o conjunto elegível (top N + allowlist − blocklist) e é
o que o `strategy-worker` lê como elegibilidade; `market.universe.changed` continua reportando
esse conjunto. O hold entra apenas em `MonitoredUniverse.symbols`, no caminho **comum** de
`run_universe` — depois do refresh do líder e depois do fallback do follower (must-fix 3 da
Astra), antes de `shard_symbols`. Custo declarado: sem tocar em `ingest.py`, o mercado segurado
volta com **todos** os canais (trades, book, mark, liquidações), não só velas.

## 9. Convenções de saída versionadas (v0)
- gap adverso na abertura (`open <= stop`) sai na abertura, com o preço adverso real;
- gap favorável (`open >= target1`) sai em `target1`, **sem crédito** pelo excedente — o plano diz
  "alvo ultrapassado usa `target1` como base sem crédito" e a convenção pessimista vale dos dois
  lados;
- prioridade de rótulo quando dois eventos caem na mesma abertura: `stop` > `target` > `expired`
  > `invalidated` (o preço é o mesmo; muda só o nome do que aconteceu);
- invalidação é observada no fechamento de uma barra alinhada ao timeframe da invalidação e paga
  na próxima abertura elegível.

## 10. Escala do banco aplicada antes da escrita
Pendência da S1 (§12, "escala do banco"): os níveis vão para `NUMERIC(28,10)` **antes** do
insert (`levels.to_db_scale`), e o motor de outcomes reconstrói o plano a partir dos valores
**armazenados** (`virtual_stop`, `virtual_targets`, `meta`), nunca da memória nem do código. É o
que faz "o nível usado depois do restart = o nível gravado" ser verdade por construção.

## 11. `meta` é canônico
Tudo em `signal_outcomes.meta` passa por `canonical_json` (`params_format = 1`): números viram
string decimal normalizada e timestamps ISO-8601 `Z`. Consequência visível nos testes: `delay_s`
é `"60"`, não `60`. Motivo: JSONB não aceita `Decimal`, e aceitar `float` seria exatamente o que
a regra dura proíbe.

## 12. `registry_key = f"{strategies.key}_{version}"`
O catálogo separa o que o código junta (`strategies.key = "momentum"` + `version = "v1"` vs
`momentum_v1`/`v1` no registry). A derivação evita um mapa escrito à mão que pode divergir. Uma
versão ativa cujo `(key, version)` não está no registry é **ignorada com log**, nunca aproximada.

## 13. Correções da revisão de diff da Astra (`astra-review-S2-worker-diff.md`)
Oito achados, seis com cenário reproduzido por ela. O que mudou:

- **Elegibilidade histórica (HIGH 1).** O gate de 300 s sozinho não *prova* nada. Agora existe
  prova: `eligibility.universe_changed_after` lê `market.universe.changed` (publicado **só**
  quando o conjunto monitorado muda) e, se houve mudança depois do fechamento da barra, a
  avaliação vira `unavailable:universe_changed`. Se não houve, o `is_monitored` de agora **é** o
  daquele instante. Limites declarados no módulo: a publicação é best-effort e o stream é
  aparado em 1000 — os dois erram para o lado otimista, e o gate de atraso continua valendo.
- **Instante do extremo (HIGH 2).** `mfe_ts`/`mae_ts` agora são **sempre nulos**: OHLC dá o valor
  da máxima, não o segundo em que ela ocorreu. A janela conhecida vai para `mfe_bar`/`mae_bar`.
- **Censura e cauda desconhecida (HIGH 3).** Um acompanhamento censurado ou ainda aberto tem
  limite superior `null` (ilimitado) e `coverage.bars_total = null`; os valores conhecidos ficam
  em `*_complete_bars`. Antes, uma censura apresentava a excursão parcial como total exata.
- **Gap favorável (HIGH 4).** `Progress.exit_observed` guarda o preço que o mercado imprimiu; o
  crédito continua limitado a `target1`. A excursão passa a ser medida pelo observado.
- **Funding (HIGH 5).** Liquidações **presentes** na janela entram mesmo fora da cadência
  estimada (união grade ∪ observadas), e uma liquidação dentro da barra de uma saída intrabar
  torna o funding não apurável (`funding_ambiguous_exit`) em vez de cobrada como se o fechamento
  fosse o instante financeiro.
- **Código congelado (HIGH 6).** `repo.code_ref_matches`: o worker só roda uma versão cujo
  `code_ref` congelado é o digest do código deste processo. Antes, um restart sobre uma imagem
  nova avaliava B gravando proveniência A.
- **Stream ocioso (MEDIUM 7).** `/ready` deixou de ficar vermelho num mercado quieto: passado o
  `consumer_stall_s`, a checagem pergunta ao próprio stream se algo foi publicado depois da
  última iteração.
- **Blocklist (MEDIUM 8).** Aplicada ao conjunto final, não só ao que o hold acrescenta — um
  follower com snapshot velho ficava coletando um símbolo bloqueado.

**Não aceito, com motivo:** nada. Os oito foram implementados. O item "fontes preservadas após a
retenção ordinária" que ela quer antes do DONE fica **em aberto** (ver §14): o `tracking_hold`
mantém a coleta, mas a retenção de 90 dias de `candles_1m` não conhece o hold — é trabalho de
schema/retention (S0/M2), não do worker.

## 14. Pendências deixadas para depois
- **S3:** as contagens de cobertura precisam separar `late:delay`, `late:missed_open`,
  `late:unconfirmed`, `geometry`, `gap:*` e `blocked:*` — cada um é uma população diferente.
- **`docker compose build strategy-worker` não constrói nada** e imprime "No services to build":
  o serviço reusa `hunter-api:${GIT_SHA:-dev}`, construída pelo serviço `api`, exatamente como o
  `market-worker` (comentário do serviço `migrate` no compose explica o motivo). A imagem que o
  `strategy-worker` roda é a mesma que `docker compose build api` produz.
- **Transferência ao analytics-worker** (item 10 da decisão): registrada em `docs/PIPELINE.md`
  §6b; quando acontecer, `advance_tracking`/`settle`/liberação do slot **mudam** de processo, não
  são duplicados.
- **Retenção não conhece o hold.** `tracking_hold` mantém a *coleta* de um mercado segurado, mas
  a retenção de 90 dias de `candles_1m` (`docs/DATABASE.md` §1.3, `prune_partitions.py`) apaga por
  partição sem olhar `shadow_episodes`. Com horizontes de 2–4 h isso não morde hoje; um replay
  antigo ou uma versão de horizonte longo morderia. É trabalho de schema/retention, não do worker.
- **Um minuto perdido custa até 24 h de avaliações naquele mercado.** A agregação da S1 exige a
  janela contígua inteira (289 barras de 5 min = 1445 min), então um buraco de um minuto deixa a
  estratégia `unavailable:gap` até o buraco sair da janela **ou** o `market-worker` recuperá-lo.
  Medido na prova operacional: o restart do coletor às 00:09 perdeu o minuto 00:08 e as 800
  avaliações seguintes foram todas `unavailable`, até a recuperação de gaps preencher. Não é
  bug — é a recusa correta de agregar sobre um buraco — mas é uma propriedade operacional que a
  S3 precisa mostrar como cobertura, e que torna a pontualidade do `recovery` do market-worker um
  requisito do Lab.
- **`funding_rates` vazio no stack local:** sem histórico de funding a cadência do mercado é
  desconhecida e `r_multiple` fica `NULL` com `meta.r_net_reason = "funding_schedule_unknown"`,
  mantendo `meta.r_ex_funding`. É o comportamento correto (nunca zero inventado), mas significa
  que enquanto o `market-worker` não persistir funding, **todo** outcome encerrado terá `R_net`
  nulo. A S3 precisa mostrar isso como cobertura, não como ausência de resultado.

---

# Correções da revisão do risk-engine-guardian (2026-09-06)

## 15. `code_ref` é por versão, não pela árvore (MUST-FIX 1, HIGH)
**O que estava errado.** `activation.py::strategies_code_ref()` fazia o digest de *todos* os `.py`
de `hunter_core/strategies/` e `repo.py::code_ref_matches()` exigia igualdade exata. Consequência
reproduzida pelo revisor: acrescentar `momentum_v2.py` — ou um comentário em `indicators.py` —
mudava o digest, `load_active_versions` passava a pular **todas** as versões congeladas com
`shadow_version_code_ref_mismatch`, e o Lab morria em silêncio com `/ready` verde.

**(a) O digest.** `hunter_strategy_worker/code_ref.py`: o `code_ref` de uma versão é o digest do
**módulo da própria estratégia mais o fecho transitivo dos módulos irmãos que ela realmente
importa**, derivado por análise `ast` dos imports (não por lista fixa, que envelhece na primeira
vez que uma calculadora muda de módulo). `momentum_v1` cobre `aggregate`, `base`, `canonical`,
`envelope`, `indicators`, `numeric`, `schema` — e **não** `volume_anomaly_v1` nem `registry`.
Formato `hunter_core.strategies.<módulo>@sha256:<64 hex>`. Uma função só, e **uma** resolução de
caminho (`Path(hunter_core.strategies.__file__).parent`), usada pelo worker e pelo script de
ativação; há teste que falha se o script recriar um `STRATEGIES_DIR` próprio (nice-to-have 3).

Dois limites declarados, ambos errando para o lado de "o digest muda quando o código muda":

- **o fecho para em `hunter_core.strategies`.** A Astra recomendou incluir **todo** módulo
  `hunter_core` alcançável, porque `domain/market.py` (`align_open_time`) e `domain/types.py`
  (`to_money`) são numericamente decisivos. **Divergência registrada e não aceita:**
  `hunter_core/domain/enums.py` é editado por trabalho não relacionado toda semana (T2.1/T2.2
  estão editando-o agora), e um digest que o cobrisse recongelaria todas as versões para fora da
  existência no próximo enum — exatamente a falha que se está corrigindo. Preço declarado: uma
  mudança em `to_money`/`align_open_time` **não** é capturada pelo digest. Se um dia importar, o
  caminho é mover os utilitários numéricos para um módulo estável dentro de `strategies/`, não
  alargar o fecho;
- **`__init__.py` fica de fora.** É uma fachada de reexports que importa as duas estratégias e o
  registry; segui-lo restauraria o acoplamento com a árvore inteira. Nenhum caminho de avaliação o
  lê (o worker resolve pelo `registry`). A Astra pediu incluí-lo "depois de torná-lo mínimo" —
  torná-lo mínimo é `packages/**`, fora do escopo desta tarefa.

**Ligação versão ↔ código.** `catalogue.py::resolve_strategy` usa duas evidências independentes:
`(strategies.key, version)` no registry (como na primeira ativação) e o **módulo nomeado pelo
`code_ref`** (a única evidência que uma versão sucedida tem, porque o `version` dela virou `v2`
enquanto o código continua `momentum_v1`). Quando as duas respondem, têm de responder a mesma
coisa (`shadow_version_code_module_conflict`). Quando só o módulo responde, ele ainda precisa
pertencer à **família** que este build conhece para aquele `strategies.key`: se o registry carrega
algum `<key>_*`, o módulo nomeado tem de ser de um deles — `momentum`/`v7` apontado para
`volume_anomaly_v1` é recusado (`shadow_version_code_module_foreign`), que é o cenário que a Astra
levantou. Uma `key` que este build não conhece não tem família para contradizer, e aí o módulo vale
sozinho (é o caso das chaves sintéticas dos testes).

**(b) `/ready` vermelho quando ninguém roda.** `catalogue.py::VersionRoster` separa linhas `active`
de versões executáveis e conta as recusas por motivo (`code_ref_mismatch`, `code_ref_not_frozen`,
`no_code`, `no_parameters`). A checagem `shadow_versions` (`health.py`) fica falsa quando
`active > 0` e `runnable == 0` — a mesma regra que `main.py:53` já aplica à migração ausente,
chegando depois do start. Métricas: `hunter_shadow_versions_active`,
`hunter_shadow_versions_runnable`, `hunter_shadow_versions_unrunnable{reason}`.

**Divergência da Astra registrada:** ela queria vermelho para **qualquer** ativa não executável
("uma estratégia saudável não deve esconder uma morta"). Mantida a regra do brief (só o silêncio
total derruba o `/ready`), porque um vermelho permanente por uma linha velha que ninguém usa treina
o time a ignorar a luz; o caso parcial aparece na gauge por motivo, que é onde ele é acionável.

**(c) `--supersede`.** As linhas já ativadas (`momentum` v1, `volume_anomaly` v1) têm o `code_ref`
da árvore inteira e são imutáveis pela trigger da 0002. O script ganhou um modo que, **numa só
transação**, marca a antiga como `deprecated` (com `changelog` dizendo por quê e para quem) e cria
`version + 1` `active` com o `code_ref` novo e com o `parameters_schema`/`default_parameters`/
`params_format` **lidos da linha congelada**, não recomputados do código (exigência da Astra: o
sucessor continua o experimento que foi congelado, não o que o código diz hoje). Recusa se a versão
nunca foi ativada, se o digest já bate, se `version + 1` já existe, ou se os parâmetros congelados
não validam contra o próprio schema. Teste de atomicidade com falha injetada antes do commit.

**Consequência aceita:** `strategy_version_id` muda, logo o `uuid5` dos sinais muda e a **população
recomeça** — v1 e v2 são coortes de contagem distintas para a S3. É o preço de não poder corrigir
uma linha congelada, e é preferível a mentir sobre a proveniência.

## 16. Censura consulta `ingestion_gaps` (MUST-FIX 2, MEDIUM)
**O que estava errado.** `_handle_gap` censurava por relógio (`censor_after_s`, 1800 s) sem olhar
o que o coletor estava fazendo. Na prova da S2 o recovery levou ~10 min para 786 gaps; uma janela
pior censuraria acompanhamentos que o dado ainda ia cobrir — e a perda seria **correlacionada com
a instabilidade do coletor**, que é o pior viés possível para um log de pesquisa (some justamente
o que foi decidido nas condições que mais interessam).

`gaps.py` pergunta ao registro do próprio market-worker, e o veredito vira o sufixo do motivo
(a S3 precisa contar as três populações separadamente):

| estado em `ingestion_gaps` | decisão | motivo |
|---|---|---|
| `open` cobrindo o minuto, recente | **espera**, quanto for preciso | — |
| `failed` cobrindo o minuto | censura **na hora** | `gap:<minuto>:failed` |
| nenhum gap cobrindo o minuto | censura ao esgotar o orçamento | `gap:<minuto>:unregistered` |
| `open` cobrindo o minuto, parado há mais que `gap_recovery_max_s` | censura | `gap:<minuto>:stalled` |

`recovered` com a vela ainda ausente conta como "não coberto": o backfill rodou e a corretora não
tinha aquele minuto (a Binance omite minutos vazios), então vale o orçamento.

**Orçamentos novos, com motivo.**
- `censor_after_s`: **1800 s → 7200 s**, e agora só vale para o minuto que *ninguém registrou*.
  1800 s era um chute curto na direção errada. A detecção roda a cada 60 s sobre uma janela de
  1439 minutos (`recovery.py`), então um market-worker **de pé** registra qualquer minuto faltante
  em ~3 min do fechamento; um buraco não registrado com duas horas significa que o coletor esteve
  fora essas duas horas, e um coletor fora há duas horas não vai preencher aquele minuto em
  silêncio.
- `gap_recovery_max_s` (novo): **86 400 s**. É o limite do veto. Só o laço de recovery move uma
  linha para `failed`; um market-worker que simplesmente não está rodando deixaria o
  acompanhamento — e o `tracking_hold` atrás dele — abertos para sempre, que é o que o §6 recusou.
  Um dia é generoso por construção: o laço tenta a cada 60 s, desiste em 5 tentativas e reabre um
  `failed` uma hora depois, então um gap em que ele está mesmo trabalhando resolve ou vira `failed`
  em horas.

## 17. Nice-to-have desta passada
- **§4 desta nota** trocava os dois números (`max_entry_delay_s` é 120 s, dos `default_parameters`;
  300 s é o `eligibility_max_lag_s`). Corrigido no lugar, com a troca declarada.
- **Prioridade de saída na mesma abertura.** O §9 declara `stop > target > expired > invalidated`;
  `walker.py::_exit_at_open` pagava a invalidação antes da expiração. O **código** foi ajustado à
  convenção declarada (o preço é o mesmo — é aquela abertura de qualquer jeito; muda só o rótulo,
  e a S3 conta por rótulo). Teste: barra que é ao mesmo tempo a abertura do horizonte e a que paga
  uma invalidação pendente ⇒ `expired`.
- **Rollback com falha injetada antes do commit** (checklist S2): `slots.advance` explode depois de
  `persist_decision`; nada fica no banco (sinal, outcome, episódio e outbox em zero) e a nova
  tentativa produz exatamente uma de cada.
- **Limite da varredura documentado e visível.** `tracking_repo.SWEEP_LIMIT = 500` ganhou docstring
  com o motivo do teto, e `count_open_trackings` + `hunter_shadow_trackings_unswept` publicam o que
  ficou de fora da passada (antes, um backlog acima do limite era indistinguível de mercado quieto).

## 18. `repo.py` virou dois módulos
O orçamento de 350 linhas estourou (414). A costura é de responsabilidade, não de contagem:
`catalogue.py` = *quais versões rodar* (roster, resolução versão ↔ código, `code_ref_matches`,
`registry_key`), `repo.py` = *sobre o que rodá-las* (mercados, velas, funding). Quem importava
`ActiveVersion`/`load_active_versions`/`registry_key` de `repo` passou a importar de `catalogue`;
não há reexport, porque um reexport esconderia a costura.

## 19. Isolamento do catálogo nos testes
Efeito colateral honesto da resolução por módulo: chaves sintéticas dos testes (`real_volume`,
`idempotent_volume`) passaram a ser **executáveis**, porque o `code_ref` que o script grava para
elas nomeia um módulo real. Como a trigger recusa apagar uma versão ativada, o catálogo é
compartilhado por toda a sessão de teste e `versions[0]` deixou de ser determinístico. Duas
ferramentas em `tests/builders.py`: `only_version(versions, key)` (o cenário diz qual versão
espera) e `isolate_catalogue(session, keep=...)` (deprecia as demais; `status` é o único campo de
ciclo de vida que a trigger deixa mutável, §16.1).

## 20. Estado do catálogo local depois do `--supersede` (2026-09-06 02:08 UTC)
| key | version | status | code_ref |
|---|---|---|---|
| momentum | v1 | deprecated | `hunter_core.strategies@sha256:13dfa322…` |
| momentum | **v2** | **active** | `hunter_core.strategies.momentum_v1@sha256:c012f75c…` |
| volume_anomaly | v1 | deprecated | `hunter_core.strategies@sha256:13dfa322…` |
| volume_anomaly | **v2** | **active** | `hunter_core.strategies.volume_anomaly_v1@sha256:d8275427…` |

Duas linhas `strategy_version_superseded` em `system_events`. Antes do `--supersede`, com a imagem
nova e as linhas velhas, o worker registrou `shadow_no_runnable_version active=2
code_ref_mismatch=2` e `/ready` respondeu **503** — a prova operacional do item (b) no stack real.
Depois, `/ready` 200, container `healthy` e as duas v2 sendo avaliadas.

**Pendência para o orquestrador (fora do escopo desta tarefa):** o comentário do serviço
`strategy-worker` em `infra/docker/docker-compose.yml` ainda diz "as três checagens de readiness";
agora são quatro (`shadow_migration`, `shadow_versions`, `shadow_consumer`, `shadow_outbox`).

## 21. Achados da revisão de diff da Astra (`astra-review-S2-fixes-diff.md`, 2026-09-06)
Três HIGH, todos aceitos e corrigidos; e uma perda que ela nomeou e que fica declarada.

**(a) O fecho por AST aceitava dependências que não capturava.**
`from hunter_core.strategies.calc.impl import X` procurava `calc.py`, não achava e **descartava
em silêncio**; `importlib.import_module("hunter_core.strategies.helper")` era invisível;
`from hunter_core.strategies import CONTEXT` (reexport pelo `__init__`, que o digest não cobre)
também sumia. Depois de congelar uma versão assim, mexer no módulo escondido mudaria a execução
**sem** mudar o digest — a única direção em que o congelamento não pode falhar. Agora
`code_ref.py` levanta `UnsupportedImport` para subpacote, reexport pelo pacote,
`import hunter_core.strategies` e qualquer `import_module`/`__import__` dentro do fecho. Não
existe nada disso em `hunter_core.strategies` hoje; no dia em que existir, o script de ativação
**recusa** em vez de congelar uma afirmação que não sustenta. (A frase "os dois erram para o lado
seguro" no §15 vale para os limites *declarados* — o fecho parar em `hunter_core.strategies` e o
`__init__.py` de fora —, não para imports que o parser não entende: esses agora são recusa.)

**(b) O segundo `--supersede` não funcionava.** Feita v1→v2 apontando para `momentum_v1`, uma nova
mudança de código exigiria v2→v3, e o script procurava `momentum_v2`/`v2` no registry e recusava.
Pior: se alguém um dia escrevesse uma `momentum_v2` de verdade, a resolução "registry primeiro"
passaria a achar **duas** respostas para a linha `momentum`/`v2` em produção e a recusaria por
conflito, matando um experimento vivo. `catalogue.py::resolve_strategy` foi invertido: **o
`code_ref` congelado decide quando nomeia um módulo** (é a afirmação irrevogável da linha), e o
registry por `(key, version)` é o *fallback* para uma linha que ainda não tem essa afirmação
(draft na primeira ativação, ou a grafia antiga da árvore). O script de supersede passou a usar a
mesma função, com o mesmo `registry` injetável dos testes. Teste: sucessora sendo sucedida
(v2 → v3).

**(c) `failed` não significa irrecuperável.** `recovery.py::_reopen_stale_failed` devolve um gap
`failed` a `open` depois de `FAILED_RETRY_AFTER_S` (3600 s) com `attempts` zerado — então censurar
na hora custaria um outcome por cinco erros transitórios. `failed` virou **cooldown**: censura só
quando o orçamento ordinário (7200 s, mais que um ciclo inteiro de reabertura + 5 tentativas)
tiver esgotado; o rótulo `:failed` continua separando a população. Sobre a outra metade do achado
(reabrir não atualiza `detected_at`, então um gap recém-reaberto carrega uma data velha):
`gap_recovery_max_s` é 86 400 s e `detected_at` é o instante do **registro**, nunca atualizado —
`stalled` significa "registrado há um dia e ainda não preenchido", retentativas incluídas, o que
continua verdadeiro. Está no docstring de `censor_reason`.

**(d) Perda declarada, não corrigida aqui.** Enquanto o catálogo está incompatível, a barra é
consumida, a versão é pulada e a mensagem recebe **ACK**: consertar o `code_ref` depois não
recupera aquelas avaliações. As gauges dão visibilidade, não preservação. É o motivo de o
`/ready` vermelho importar (o operador é avisado no primeiro poll, não no relatório da S3), e a
recuperação de verdade seria uma coorte de replay (`replay:<run_id>`), que é escopo da S3/S4 e não
desta tarefa. A S3 precisa contar as barras perdidas nessa janela como cobertura ausente com
motivo, não como mercado quieto.
