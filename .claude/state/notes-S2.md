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

## 22. `code_ref` hasheava bytes crus — CRLF (Windows) vs LF (VPS) davam versões diferentes
Bug HIGH achado pela Sexta-feira na VPS (2026-09-06): `version_code_ref`
(`services/strategy-worker/hunter_strategy_worker/code_ref.py`) hasheava os bytes exatos de cada
módulo do fecho. `packages/core/hunter_core/strategies/**` está com CRLF numa checkout Windows e
com LF na VPS (Linux); mesmo commit, dois digests diferentes. Uma versão ativada de um lado batia
`code_ref_mismatch` do outro — `load_active_versions` a pulava e `/ready` (via `shadow_versions`)
ficava vermelho sem nenhuma mudança de código real.

**Correção:** o digest agora é calculado sobre o conteúdo *normalizado* de cada módulo —
decodificado como UTF-8 (BOM inicial, se houver, descartado via `utf-8-sig`), com `\r\n` e `\r`
reescritos para `\n` antes de entrar no `sha256` (`_normalized_source`, mesmo arquivo). A leitura
usada para descobrir o fecho de imports (`ast.parse`) também passou a decodificar com `utf-8-sig`,
pelo mesmo motivo — um módulo com BOM antes só quebrava o parse antes de chegar ao hash. Nada além
disso muda: espaços finais, indentação e o resto do texto continuam byte-a-byte significativos
(`TestLineEndingNormalization::test_a_real_code_change_still_changes_the_digest_under_crlf` e
`test_trailing_whitespace_still_changes_the_digest` provam isso — trocar um byte real ainda muda o
digest, com CRLF ou sem). Testes em `services/strategy-worker/tests/test_code_ref.py`.

**O digest de toda versão já ativada muda com esta correção** — inclusive as da tabela do §20
(`momentum`/v2 `code_ref=hunter_core.strategies.momentum_v1@sha256:c012f75c…`,
`volume_anomaly`/v2 `code_ref=…@sha256:d8275427…`). Reproduzido e confirmado nesta tarefa:

| variante | digest de `momentum_v1` (fecho: aggregate, base, canonical, envelope, indicators, numeric, schema) |
|---|---|
| **antes** da correção, árvore LF (a que está no repo) | `hunter_core.strategies.momentum_v1@sha256:c012f75cdd8492d3eb46aa9abd536320220c3bf71788e47e6b6b73218b0ba823` |
| **antes** da correção, mesma árvore forçada para CRLF | `hunter_core.strategies.momentum_v1@sha256:4942036753bf73091374d86ae74c4e8e885d776a2ec8fb5afd5f5e34afd3f52b` (**diferente** — o bug, reproduzido) |
| **depois** da correção, árvore LF | `hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95` |
| **depois** da correção, mesma árvore forçada para CRLF | `hunter_core.strategies.momentum_v1@sha256:6ccbe8b6c8ac18f32e93a6d44e71e0045155646479907b2b1944f39c3cdf4c95` (**igual** — corrigido) |

Ou seja: qualquer linha de `strategy_versions` já congelada com o digest antigo (tree-wide *ou*
por módulo, calculado antes desta correção, em qualquer SO) vai divergir do digest que esta
imagem calcula agora. A regularização é via `infra/scripts/activate_strategy_version.py
--supersede` (o mesmo mecanismo do §20/§21-b) — decidir **onde** rodar (dev, VPS, ambos) e para
quais linhas fica com o orquestrador; esta tarefa só corrigiu o cálculo, não tocou no catálogo.

**Arquivos tocados:** `services/strategy-worker/hunter_strategy_worker/code_ref.py`,
`services/strategy-worker/tests/test_code_ref.py`, `.gitattributes` (raiz — `*.py text eol=lf`,
`*.sh text eol=lf`, `*.ps1 text eol=crlf`, para que clones futuros já venham em LF; a árvore
existente **não** foi renormalizada agora, isso é commit separado do orquestrador), esta nota.

## 23. Funding: identidade por proximidade temporal, não por igualdade exata de timestamp (S2-funding)

Achado da Sexta-feira/Astra (H2, `EXP-0001-momentum-v1.md`): dos 73 outcomes com `R_net = null`
por funding "não apurável", **69** tinham uma linha real em `funding_rates` a menos de 2 s do
instante que o código pedia — a maioria a 5 ms —, porque `resolve_funding` casava por **igualdade
exata de timestamp** contra uma grade nominal calculada, e a grade real da Binance não é redonda
(851 de 1883 linhas de `funding_rates` têm segundos ≠ 0). A correção ingênua de dar tolerância
`±2s` ao casamento é **proibida**: o código antigo fazia a **união** da grade calculada com o
observado, então uma tolerância aplicada a essa união cobraria a mesma liquidação duas vezes.

**Desenho, com três rodadas de revisão da Astra matando dois desenhos antes deste** (a razão de
cada rejeição está no docstring de `funding.py`, não repetida aqui):

1. *Rejeitado:* grade de slots ancorada no epoch Unix (`floor(epoch_s / interval_s)`). Morreu com
   dois contraexemplos concretos: `_cadence()` truncava o gap pro segundo (`int()` em vez de
   `round()`), então um par jitterizado lia 28799 s em vez de 28800 e a âncora do epoch caía longe
   da grade real; e um mercado que passa a liquidar de hora em hora por um tempo depois do seu 8h
   normal (mecanismo real da Binance) põe **dois pagamentos reais e devidos** no mesmo bucket de
   8h, e "o mais antigo vence" descartava o segundo silenciosamente.
2. *Rejeitado:* casamento por proximidade só contra a grade nominal, com sobras tratadas como
   eventos soltos. Morreu com três achados: a guarda de ambiguidade comparava o instante **nominal**
   contra a abertura da barra, não o instante **real** da linha (uma liquidação 5 ms depois da
   abertura passava como não-ambígua); duas linhas próximas do mesmo nominal com taxas
   **conflitantes** eram resolvidas escolhendo a mais próxima, quando discordância é evidência de
   que não é o mesmo evento; e duas linhas duplicadas fora da grade (sem nominal por perto) nunca
   eram deduplicadas, porque o casamento só olhava pro nominal.
3. *Rejeitado:* clusterização restrita às linhas já dentro de `(entry_ts, exit_ts]`, usando o
   primeiro membro do cluster como instante de referência para toda fronteira. Morreu com dois
   cenários de "cluster a cavalo de uma fronteira": duas representações do mesmo evento, uma no
   instante exato de `ambiguous_from` (não-ambígua sozinha) e outra 5 ms depois (ambígua sozinha) —
   escolher a primeira escondia a incerteza da segunda; e duas representações, uma exatamente na
   entrada (corretamente nunca cobrada) e outra 5 ms depois (dentro da janela) — filtrar pra janela
   *antes* de clusterizar escondia a irmã que provava serem o mesmo evento nunca-cobrado.

**O desenho final** (`services/strategy-worker/hunter_strategy_worker/funding.py`):
clusteriza **todo** o histórico lido (não só o que já está na janela) por proximidade temporal pura
(`MATCH_TOLERANCE = 2s`, exportada — bem menor que a metade do menor espaçamento real entre
liquidações distintas, que é medido em horas). Por cluster: se os membros **discordam** sobre estar
dentro de `(entry_ts, exit_ts]`, ou sobre estar antes/depois de `ambiguous_from`, o resultado é
`funding_boundary_uncertain`/`funding_ambiguous_exit` — incidência incerta, nunca resolvida
escolhendo o lado conveniente. Só um cluster **unânime** dentro da janela segue adiante: precisa
concordar em `rate` e `mark_price` (senão `funding_conflicting_rows`); um cluster de mais de uma
linha que concorda é **uma** cobrança (`duplicate_settlement_row` em `meta.funding.notes`), nunca
duas. Só depois disso o cluster é casado (contabilidade, nunca reutilizável) com o nominal mais
próximo, unicamente para dizer quais nominais ficam genuinamente `funding_missing` — a grade
identifica lacunas, nunca fabrica ou funde uma cobrança. **Achado colateral:** o código antigo
também *dobrava* a cobrança quando duas linhas reais e muito próximas existiam para o mesmo
settlement (reproduzido: `per_unit` saía 0.04 em vez de 0.02) — um bug latente distinto do H2, que
este desenho também fecha por construção.

**A janela de leitura em si precisou alargar.** `settle.py`/`recompute_funding.py` liam
`funding_rates` até `exit_ts` inclusive; uma linha real 5 ms **depois** de `exit_ts` (a outra
metade de um cluster cuja irmã está dentro da janela) nunca chegava a `resolve_funding`, que
então via só a metade "dentro" do cluster e a cobrava como se fosse um evento resolvido e solto —
exatamente o bug que o item 3 do desenho corrige, mas só se o dado chegar. As duas leituras agora
pedem até `exit_ts + MATCH_TOLERANCE`; `resolve_funding` continua sendo o único lugar que decide o
que está de fato "dentro" — o alargamento é só para não cegar o clusterizador.

**Métrica/log:** `hunter_shadow_funding_unresolved_total{reason}` (Counter, família do motivo sem
o sufixo do timestamp — `funding_missing:<instante>` vira `funding_missing`, senão a cardinalidade
explode) e log estruturado `shadow_funding_unresolved` (`signal_id`, `market_id`, `reason`
completo), em `outcomes.py::_finish`.

**Recompute (`infra/scripts/recompute_funding.py`, novo).** Lista outcomes **terminais** com
`r_multiple IS NULL` e `meta.funding.reason` não nulo, recomputa com o código atual contra os
valores **armazenados** (nunca re-anda as barras), e só com `--apply` grava — preservando
`meta.r_ex_funding` intocado e `meta.funding.reason = null` (nunca sobrescrito pela auditoria,
para não poluir uma futura contagem de "funding indisponível" com um outcome já corrigido);
`meta.funding.previous` guarda o objeto `funding` anterior por inteiro, `recomputed_at` e
`recompute_reason` registram quando e por quê. Idempotente por construção (a mesma `WHERE
r_multiple IS NULL` do `SELECT` está no `UPDATE`); `--apply` só conta uma linha como escrita se
`rowcount > 0` (uma segunda execução concorrente não infla a contagem).

**Prova.** 25 testes novos (`test_funding.py` un­it, `test_settle.py` e `test_recompute_funding.py`
de integração contra Postgres real via testcontainers — este último carrega o script por caminho,
como `infra/scripts/tests/test_create_partitions.py` já faz, porque o script não é pacote
instalado). Cada um dos cenários de bug foi confirmado falhando contra o código anterior antes da
correção (evidência no relatório da tarefa, não repetida aqui). `uv run pytest
services/strategy-worker` (unit + integração, por arquivo), `ruff check .`, `ruff format --check
services`, `pyright services/strategy-worker` e `check_file_size.py` verdes. Dry-run real contra o
Postgres do stack local (`docker compose ... exec strategy-worker`, com o código copiado pro
container e restaurado ao original depois — a imagem publicada não mudou): **0 de 237** outcomes
terminais locais estão afetados hoje, porque nenhum atravessa uma liquidação neste snapshot
(`meta.funding.reason` já é `null` nos 237); o censo de 73 casos do H2 é da coorte da **VPS**,
população diferente. A sintaxe do `UPDATE` foi validada contra o schema real numa transação
`BEGIN; ...; ROLLBACK;` antes disso.

**Arquivos tocados:** `services/strategy-worker/hunter_strategy_worker/{funding,settle,outcomes,metrics}.py`,
`services/strategy-worker/tests/{test_funding,test_settle,test_recompute_funding,test_shadow_outcomes}.py`
(novo: `test_settle.py`, `test_recompute_funding.py`), `infra/scripts/recompute_funding.py` (novo), esta nota.

## 24. `build_market_context` nunca recebia funding/OI; `regime_id` nunca era carimbado (S2-context)

Dois buracos medidos pela Sexta-feira (notas-S2, KB-0030, KB-0059): (1)
`context.py::build_market_context` chamava `build_context(...)` sem `funding` nem
`open_interest`, embora `base.py` (S1) já aceitasse e filtrasse os dois por `ts <= cut` —
`StrategyContext.funding`/`.open_interest` eram `None` em **toda** avaliação, bloqueando a
candidata M-E do backlog (teto de funding extremo); (2) `agent_signals.regime_id` nunca era
gravado, apesar de `market_regimes` existir desde a T2.1/T2.4 e o scanner escrever regimes.

**(a) Módulo novo `derivatives.py`.** Durável primeiro (`funding_rates`, `open_interest_history`,
lidos por `market_id` + PK, mais recente com `ts <= cut`), hot state (`mkt:{ex}:{sym}:deriv`) só
quando o durável não tem linha ou a linha é incompleta para o tipo de domínio
(`NormalizedFunding.mark_price` é obrigatório). Fonte (`"durable"`/`"hot_state"`) e motivo de
ausência (`no_data`, `no_mark_price`, `no_open_interest_value`, `timestamp_unprovable`) voltam
junto do valor e são gravados em `supporting_features.provenance` (JSONB já existente — sem
migração). `context.py` passa `funding=`/`open_interest=` para `build_context`, que já fazia o
corte; nada em `packages/**` mudou.

**Três rodadas de revisão da Astra, a segunda derrubando a correção da primeira:**

- **MUST-FIX 1 (rodada 1) — o `ts` durável do OI é o início do bucket da rodada de poll, não o
  instante da leitura.** `hunter_market_worker/persist_rows.py` calcula **um** bucket (`oi_bucket`,
  5 min) para a rodada inteira e depois faz REST sequencial por símbolo
  (`sampling.py::_run_oi_cycle`); um mercado tarde na rodada pode ter sido lido estritamente depois
  do bucket em que foi gravado. `row.ts <= cut` sozinho **não prova** "lido antes do corte".
  *Correção tentada:* aceitar a linha durável só quando `cut >= row.ts + 5 min` (uma folga do
  tamanho de `OI_BUCKET_MINUTES`).
- **MUST-FIX 1 (rodada 2) — a folga fixa não fecha o buraco, e a Astra construiu o contraexemplo:**
  rodada começa `12:04:59` (bucket `12:00`, porque `oi_bucket` arredonda o **início** da rodada para
  baixo), lê o mercado às `12:05:02` e grava `ts=12:00`; uma avaliação no corte `12:05:00` — três
  segundos **antes** da leitura real — passaria pela folga de 5 min (`12:05:00 >= 12:00 + 5min`).
  Qualquer folga finita tem essa falha: ela reduz a exposição, nunca estabelece garantia, porque
  nada no código limita quanto tempo uma rodada pode levar. **Correção final: o `ts` durável do OI
  nunca é tratado como prova de `<= cut`, ponto.** `_resolve_open_interest` só aceita o hot state
  (cujo `oi_ts` é o instante real da leitura, `hunter_market_worker.hot_state.write_open_interest`);
  uma linha durável sozinha vira sempre `timestamp_unprovable`, **não importa a idade** — nada no
  esquema atual distingue "seguramente antiga" de "a rodada que a escreveu ainda pode estar
  rodando" sem uma suposição que este módulo se recusa a fazer. **Risco residual declarado, fora do
  escopo desta tarefa** (não pode tocar `services/market-worker/**`): o OI durável nunca vira
  utilizável enquanto o market-worker descartar o timestamp real de cada leitura em favor do bucket
  da rodada — o conserto de verdade é lá, não aqui. `OI_BUCKET_SLACK` e o teste que fixava aceitação
  exatamente na fronteira de 5 min foram removidos (cristalizavam a premissa errada).
- **MUST-FIX 2 — um settlement realizado no hot state nunca atualiza o preço de mark.**
  `hunter_market_worker/hot_state.py::write_funding(realized=True)` só toca o grupo de campos do
  funding, deixando o `mark_price`/`mark_ts` do último snapshot **estimado** (possivelmente muito
  mais antigo ou mais novo, e não relacionado) parado no hash. Combiná-los fabricaria uma
  observação que nunca existiu como tal. `DerivRaw` passou a expor `mark_ts` separado de
  `funding_ts`, e `_resolve_funding` só aceita a combinação do hot state quando
  `funding_ts == mark_ts` (prova de que vieram da mesma escrita); senão, `no_mark_price`.
- **MUST-FIX 3 — aceito, já estava certo por construção, só o nome do motivo mudou.**
  `load_regime_asof` não filtra por valor de `regime`, então um regime `UNKNOWN` gravado durante o
  warm-up do classificador (T2.4) já era retornado como um regime de verdade (é uma classificação,
  não um valor ausente — docstring de `MarketRegime`). Só a **ausência de qualquer linha** retorna
  `None`; o motivo passou de `"no_regime_before_cut"` para `"no_regime_asof"` para não presumir "é
  warm-up" de um `SELECT` vazio — a função não sabe distinguir os dois casos e não tenta.
- **Nice-to-have aceito:** a query de regime ganhou `end_time IS NULL OR cut < end_time`
  (`[start_time, end_time)` explícito), em vez de confiar apenas em "o mais recente com
  `start_time <= cut`" — mais barato do que continuar assumindo contiguidade perfeita entre linhas.

**Não aceito, com motivo:** a sugestão de privilegiar sempre a observação "inteira" mais adequada
semanticamente por cima de "durável primeiro" (ex.: nunca usar o durável de funding quando ele é
`realized` e uma leitura mais nova `estimated` existiria) foi descartada — o brief pede
durável-primeiro explicitamente, e o `funding_kind="realized"` já é gravado corretamente para
diferenciar as duas leituras a jusante (o Lab decide o que fazer com cada tipo).

**(b) `regime_id`.** `decide.py::evaluate_slot` chama `repo.load_regime_asof(session, cut=bar_close)`
dentro da mesma transação que já segura o lock do slot, antes de `build_record`; `RegimeScope.GLOBAL`
sempre (é o único escopo que o scanner popula hoje — `scanner.py:229` — não existe regime por
mercado). `regime_id`/`regime_reason` **não** entraram em `Provenance` (que é montado em
`context.py`, antes da procura de regime): são parâmetros próprios de `build_record`, escritos no
mesmo bloco `supporting_features.provenance` do item (a). Nunca bloqueia o sinal
(`ShadowConfig`/`Evaluation` inalterados).

**(c) `code_ref` não muda.** Only `services/strategy-worker/**` foi tocado; o digest
(`code_ref.py`) é sobre `packages/core/hunter_core/strategies/**`, intocado. `test_code_ref.py`
(23 testes) continua verde sem qualquer alteração — confirmado rodando a suíte isolada.

**(d) Nada de novo é emitido.** `momentum_v1`/`volume_anomaly_v1` não leem `ctx.funding`/
`ctx.open_interest` (grep confirma). `test_no_new_signals.py` prova isso construindo o mesmo
contexto com e sem funding/OI preenchidos (incluindo um funding deliberadamente extremo,
`0.0009`) e comparando a `Decision` (modelo Pydantic congelado, `==`) — idêntica com e sem. Achado
da Astra, não fechado: para `volume_anomaly_v1` o lote realmente dispara (`decision is not None`
verificado); para `momentum_v1` nenhum dos dois lotes dispara (a receita de `series()` é a de
`volume_anomaly_v1`, 1m/5m; a de `momentum_v1` é 15m e não foi reproduzida aqui por custo/tempo) —
a prova de invariância para `momentum_v1` cobre hoje só a população "sem sinal", não "com sinal
suprimido por engano". **Pendência declarada para quem pegar isso depois:** um lote que dispare
`momentum_v1` de verdade (recibo em `packages/core/tests/unit/strategies/test_momentum_v1.py`) e a
mesma comparação `==`.

**Testes novos:** `test_derivatives.py` (unit, resolução pura — inclui os cenários das três
must-fixes da Astra, reproduzidos falhando contra o código anterior a cada correção),
`test_context_derivatives.py` (integração: durável, hot state, fonte na proveniência, o cenário
pedido explicitamente pelo brief — uma observação 1 s depois do corte nunca entra, para funding
**e** para OI —, e o caso "taxa elegível com mark só no futuro" que a Astra pediu),
`test_regime_stamp.py` (integração: regime vigente carimbado, `UNKNOWN` carimbado como qualquer
outro, ausência com motivo, nunca bloqueia, fronteiras exatas `start_time == cut` aceita e
`end_time == cut` recusada), `test_no_new_signals.py` (unit, item d, com a pendência acima).

**Comandos e saída real (após as três rodadas de revisão da Astra):**
`uv run pytest services/strategy-worker --ignore=.../test_replay_arms.py
--ignore=.../test_replay_reproduce.py -q` → **205 passed** (os dois arquivos de `replay/**`
excluídos são de outra tarefa em voo — ver "Achado não meu" abaixo); `uv run ruff check
services/strategy-worker` e `uv run ruff format --check services/strategy-worker` verdes (o único
achado é em `replay/**`, de outra tarefa em voo, fora do escopo desta); `uv run pyright
services/strategy-worker` → 0 erros; `uv run python infra/scripts/check_file_size.py` → só
`replay/engine.py` (351 linhas, outra tarefa, oscilando enquanto ela edita) acima do orçamento —
nenhum arquivo tocado aqui passa de 291 linhas.

**Achado não meu, registrado para quem estiver de plantão em `replay/`:**
`test_replay_arms.py::test_no_arm_enters_where_the_base_refused_the_entry` falha com
`AttributeError: 'NoneType' object has no attribute 'execute'` (o teste passa `session=None` de
propósito e o caminho de código chega a `repo.py::load_funding`, função que esta tarefa não tocou).
Reproduzido isolado, confirmado não relacionado a nada aqui — `repo.load_funding` está byte a byte
igual ao que era antes desta tarefa (só funções novas foram acrescentadas ao módulo).

**Fechamento da Astra (3ª rodada, pós-correção):** "sim, fecha o must-fix 1" — hot state consultado
incondicionalmente, corte aplicado antes do resolver, durável sozinho sempre `timestamp_unprovable`
independente da idade. Nice-to-have aceito e aplicado: a abertura do docstring do módulo dizia
"durável primeiro, hot state como fallback" para os dois igualmente, quando o OI tem uma exceção
obrigatória — reescrita para nomear a assimetria explicitamente.

**Arquivos tocados:** `services/strategy-worker/hunter_strategy_worker/derivatives.py` (novo),
`services/strategy-worker/hunter_strategy_worker/{hot_state,repo,context,record,persist,decide}.py`,
`services/strategy-worker/tests/{test_derivatives,test_context_derivatives,test_regime_stamp,test_no_new_signals}.py`
(novos), `services/strategy-worker/tests/builders.py` (helpers `insert_funding_rate`,
`insert_open_interest`, `insert_regime`), esta nota.
