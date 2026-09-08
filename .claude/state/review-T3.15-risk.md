# Revisão `risk-engine-guardian` — T3.15 (`6b837ac`) e T3.15b (`56d2dea`)

Revisor: `risk-engine-guardian`. Data: 2026-09-08. Somente leitura; nada foi editado fora deste
arquivo, nada commitado, nenhuma suíte com testcontainers executada.
Diff lido: `git diff 0db5fbb~3..56d2dea` nos caminhos do pedido (inclui, por construção do intervalo,
`7839731` T3.14b/T3.5d — comentado só onde toca o caminho do dinheiro).
Contrato de referência: `docs/RISK_ENGINE.md` §1–§3, §6, §8, §11; `docs/DATABASE.md` §22;
`.claude/state/decisions-delegated-2026-09-07.md` §D10.

## Resposta à pergunta central

**Existe algum caminho pelo qual um sinal chega a uma ordem paper sem uma versão `purpose = paper`
ativada por ato humano auditado?**

Sim — dois, e nenhum deles é exercido por código que existe hoje. O que os torna reportáveis é que
ambos estão **dentro dos privilégios já concedidos** ao papel `hunter_worker`, e a §7 do contrato
("falhar fechado") e a §5 ("o estado durável é a autoridade; o Redis e o evento são projeções") pedem
que a garantia venha do dado durável, não da ausência de uma linha de código:

1. **A ponte nunca lê `strategy_versions.purpose`.** O rótulo que decide se um sinal pode virar ordem
   é lido de `agent_signals.supporting_features->>'purpose'` — um JSONB que o próprio papel
   `hunter_worker` pode `UPDATE` e que não tem CHECK nem trigger de congelamento — enquanto a coluna
   autoritativa, dona do rótulo, congelada depois da ativação e só escrevível pelo owner, é
   **ignorada na mesma query que já a junta**. (B1)
2. **A ativação em si não é protegida pelo banco.** `hunter_worker` manteve `UPDATE (status,
   activated_at)` em `strategy_versions`, e a trigger de congelamento só dispara
   `WHEN OLD.activated_at IS NOT NULL`. Uma linha `paper` em `draft` pode ser ativada por qualquer
   sessão com o DSN do worker, sem `system_events`, sem changelog e sem ato humano registrado. (B2)

Os três portões pedidos (`catalogue.py`, `admission/sources.py::origin()`, `bridge_screen.py`) estão,
individualmente, **corretos e fail-closed** — ordem certa, rótulo desconhecido recusado, `live`
recusado por nome com a mensagem da D10. O problema não é nenhum dos três: é que **dois deles nunca
veem um rótulo que não seja `paper`** (§"Antes de ligar a ponte", item 3) e o terceiro julga o dado
errado.

---

## Bloqueantes

### B1 — a ponte decide o propósito por um JSONB que o worker pode escrever, e ignora a coluna que a D10 criou

`services/execution-worker/hunter_execution_worker/bridge_repo.py:92-107` (`_SIGNAL_SELECT`) e
`bridge_repo.py:152` (`purpose=str(envelope.get("purpose") or meta.get("purpose") or "")`).

A query já faz `JOIN strategy_versions v ON v.id = s.strategy_version_id` e lê `v.status` e
`v.activated_at` — mas **não** lê `v.purpose`. O `purpose` que `bridge_screen.screen_signal`
(`bridge_screen.py:235-246`) julga vem exclusivamente de `agent_signals.supporting_features`
(fallback `signal_outcomes.meta`). `agent_signals` está em `infra/migrations/ddl/tables.py:157`
(`WORKER_WRITE_TABLES`): `hunter_worker` tem `INSERT, UPDATE` de tabela e a tabela não tem trigger de
imutabilidade. `strategy_versions.purpose`, ao contrário, é congelado depois da ativação
(`infra/migrations/ddl/strategy_purpose.py:82`) e revogado de todo papel de aplicação
(`ddl/strategy_purpose.py:203`). A revisão inverteu a autoridade: o campo mole decide, o campo duro é
ignorado.

**Prova, sem banco** (sonda de leitura, saída real em §"Comandos"): `_signal()` devolve
`purpose='paper'` a partir de um `supporting_features` que diz `paper`, e `screen_signal` passa o
portão de propósito e só para no check de geometria seguinte — a versão nunca é consultada.

**Prova, dentro da própria suíte verde:** `services/execution-worker/tests/shadow_builders.py:229`
insere `strategy_versions` **sem nomear `purpose`** (logo, `research_only`, o default da coluna) e
`shadow_builders.py:287` grava `"purpose": purpose` só no envelope JSON. O teste
`test_a_paper_signal_of_an_active_version_is_a_candidate`
(`services/execution-worker/tests/test_bridge_eligibility.py:92-101`) passa — ou seja, os 14 verdes
da T3.15b **demonstram** que um sinal de uma versão `research_only` é admitido pela ponte quando o
envelope diz `paper`. O teste que deveria provar o portão prova o buraco.

**Cenário concreto.** A linha `momentum v2` (paper) é derivada e ativada pelo Everton; a ponte é
ligada. Uma sessão com o DSN do worker (o próprio `strategy-worker`, o `execution-worker`, ou uma
correção de incidente feita à mão — a rota normal de reparo neste projeto) roda
`UPDATE agent_signals SET supporting_features = jsonb_set(supporting_features, '{purpose}', '"paper"')
WHERE strategy_version_id = <momentum v1>`. Os sinais da coorte `research_only`, que a decisão
conjunta item 9 diz que **nunca** viram ordem, passam o portão da ponte, chegam a `origin()` (que
recebe `paper` constante — ver item 3 de "Antes de ligar"), viram `trade_proposal` e, aprovados,
viram ordem de entrada. Nada no caminho relê a versão. A `agent_signals` não precisa nem ser
alterada: basta um `INSERT` com o JSONB escolhido, que o mesmo papel também pode fazer.

**Correção (pequena e testável).**
1. `bridge_repo.py:92-107`: acrescentar `v.purpose AS version_purpose` ao `SELECT`.
2. `bridge_repo.py:86`: `ShadowSignal` ganha `version_purpose: str`.
3. `bridge_screen.py:235`: o portão passa a exigir **as duas** verdades — recusa `unknown_purpose` se
   qualquer uma não for `paper`, e um motivo novo `purpose_mismatch` quando envelope e linha
   divergem (é o sinal de que alguém escreveu no lugar errado; ele merece contador e log próprios,
   não pode se esconder atrás de `research_only`).
4. Teste: versão `research_only` + envelope `paper` ⇒ `purpose_mismatch`; versão `paper` + envelope
   `paper` ⇒ passa; versão `paper` + envelope `research_only` ⇒ recusa. E
   `shadow_builders.activate_version` passa a nomear `purpose`, para que o teste que diz "paper"
   crie de fato uma coorte paper.

### B2 — a ativação de uma linha `paper` não exige o owner nem deixa `system_events`

`infra/migrations/ddl/strategy_purpose.py:176-189` (`WORKER_COLUMNS_EXCEPT_PURPOSE` inclui `status`
e `activated_at`) e `ddl/strategy_purpose.py:146-155` (as duas triggers de congelamento nascem com
`WHEN (OLD.activated_at IS NOT NULL)`).

A `0010` estreitou corretamente o que **cria** uma coorte paper (`purpose` é do owner). Não estreitou
o que a **ativa**. Como a trigger de congelamento não dispara em linha `draft`
(`activated_at IS NULL`), o `UPDATE` que promove a linha é ordinário, e `hunter_worker` tem o
privilégio de coluna para os dois campos que o compõem.

`git grep` confirma que **nenhum** código de aplicação escreve `strategy_versions`: o único `INSERT`
do repositório está em `services/strategy-worker/hunter_strategy_worker/paper_line.py:109`, executado
na conexão de migração. O privilégio é, hoje, inteiramente não usado — e é exatamente o privilégio
que a D10 diz que não deve existir ("a ativação é ato deliberado, manual, auditado").

**Cenário concreto.** A linha `momentum v2` (paper, `draft`) já foi derivada — ato legítimo,
auditado, que a D10 prevê. Antes das sete condições estarem cumpridas, uma sessão qualquer com o DSN
do worker (um script de manutenção, um `psql` de plantão, uma migração de dados fora do Alembic) roda
`UPDATE strategy_versions SET status='active', activated_at=now() WHERE purpose='paper'`. A partir do
ciclo seguinte o `strategy-worker` carrega a versão no roster (`catalogue.py:250-258` só recusa
`live`), emite sinais com `envelope["purpose"]='paper'` (`record.py:170`) e a coorte que move capital
está de pé. `system_events` não tem nenhuma linha; `docs/DATABASE.md` §22.4 e a D10 afirmam que a
ativação é auditada, e não haveria como datá-la. Com `ENABLE_PAPER_AUTONOMY=false` nada vira ordem —
mas o interruptor passa a ser a **única** coisa entre uma coorte que ninguém autorizou e a carteira.

**Correção.** Migração nova (`0011`), no padrão da `0010`: revogar `UPDATE (status, activated_at)` de
`hunter_worker` (re-conceder as demais colunas), e teste em
`packages/core/tests/integration/test_schema_privileges.py` provando que o worker não promove uma
linha `draft`. Alternativa complementar, mais forte e mais cara: trigger `BEFORE UPDATE ... WHEN
(OLD.activated_at IS NULL AND NEW.activated_at IS NOT NULL)` que recuse quando `current_user` não é
o owner. A revogação basta para o M3.

---

## Antes de ligar a ponte

### 1 — `activate` de uma linha `paper` reescreve o conteúdo copiado com o que o código diz hoje

`infra/scripts/activate_strategy_version.py:134-137` e `:156-175`.

`--paper-line` copia `parameters_schema`/`default_parameters`/`params_format` da linha congelada
(`paper_line.py:78-121`) e recusa se o `code_ref` do build divergir do congelado
(`paper_line.py:73-77`). O `activate` que vem depois **não** copia da linha: lê
`strategy.parameters_schema` e `strategy.default_parameters` do **código do build atual**
(`:136-137`) e os grava junto com um `code_ref` recalculado (`:156-170`). Como a linha derivada tem
`activated_at IS NULL`, a guarda de `:143` ("uma versão congelada nunca é reapontada") não roda, e
não há nenhuma comparação entre `row.code_ref` e o digest atual.

**Cenário concreto.** 2026-09-10: `--paper-line momentum v1` deriva `v2` com `atr_mult=2.0` e
`code_ref=momentum_v1@sha256:AAA` (o build da VPS naquele dia — a derivação exige que batam).
2026-09-11: um deploy toca `momentum_v1.py` (um default ajustado, ou só uma constante) → digest BBB,
`atr_mult=2.5`. 2026-09-12, cumpridas as sete condições, o Everton roda
`activate_strategy_version.py momentum v2 --changelog "..."`. O script aceita: `resolve_strategy`
liga a linha pelo **nome do módulo** que o `code_ref` nomeia (`catalogue.py:193-212` — o digest não
entra nessa resolução), recalcula BBB e grava BBB **e** `atr_mult=2.5`. A coorte paper passa a rodar
parâmetros e código que a coorte `research_only` nunca rodou; a comparação que a D10 existe para
fazer ("o mesmo gatilho medido pelas barras e medido pela carteira") deixa de ser possível, e a
carteira gasta dinheiro sob parâmetros que ninguém comparou. O `system_events` registra o `code_ref`
novo, não que o conteúdo derivado foi descartado.

Não há teste que pegue isso: `services/strategy-worker/tests/test_activate_paper_line.py:164-182`, o
único que ativa uma linha paper, roda com `dry_run=True` — o `UPDATE` nunca é exercido sobre uma
linha derivada.

**Correção.** Em `activate()`, quando `row.code_ref` já é um digest congelado (toda linha derivada
tem um): recusar se o digest recalculado divergir — a mesma frase que `paper_line.py:73-77` já usa —
e copiar `schema`/`params`/`params_format` **da linha**, não do código, como `supersede` (`:232-233`)
e `paper_line` já fazem. Teste com `dry_run=False`: ativar a linha derivada preserva byte a byte o
que foi copiado; e um build divergente é recusado em vez de reescrever.

### 2 — a ponte não filtra `cohort`: uma coorte de replay pode gastar a carteira

`services/execution-worker/hunter_execution_worker/bridge_repo.py:92-107` — `grep -rn cohort
services/execution-worker/hunter_execution_worker` não devolve nada. O `_SIGNAL_SELECT` não filtra
`supporting_features->>'cohort'`.

`hunter_core.domain.enums.ShadowCohort` (`packages/core/hunter_core/domain/enums.py:358-366`) é
explícito: *"Replay and prospective are different populations by construction: the data used to
develop a version is never that version's reserved forward evaluation"*. A coorte é configuração do
worker (`SHADOW_COHORT`, `services/strategy-worker/hunter_strategy_worker/config.py:117`), não
propriedade da versão — as duas coortes emitem sob o **mesmo** `strategy_version_id`, e portanto sob
o mesmo `agents` e o mesmo `purpose`.

**Cenário concreto.** Com a linha paper ativa e a ponte ligada, alguém sobe um segundo
`strategy-worker` com `SHADOW_COHORT=replay:paramtest` — que é precisamente o mecanismo documentado
para manter as duas populações separadas — contra o stream ao vivo. Seus sinais carregam
`purpose=paper` (vem da versão), `source_bar_close` do minuto corrente e `emitted_at = now`
(`services/strategy-worker/hunter_strategy_worker/persist.py:65`), logo caem dentro do `_LOOKBACK`
de 240 s e da `ENTRY_WINDOW` de 120 s. A ponte os seleciona, screena e submete: a população de replay
ocupa vaga, consome orçamento de participação (§4 do contrato: a chave é
`(market_id, escopo_de_capital)`, compartilhada por todos os agentes) e move capital, além de
contaminar a avaliação prospectiva reservada.

**Correção.** `AND s.supporting_features->>'cohort' = 'prospective'` no `_SIGNAL_SELECT`, e um ramo
`cohort_not_prospective` em `screen_signal` para defesa em profundidade e contador próprio (um sinal
de replay chegando à porta é um erro de operação que merece ser visto, não filtrado em silêncio).
Teste: sinal `cohort='replay:x'`, versão `paper`, envelope `paper`, janela aberta ⇒ recusado.

### 3 — `origin()` só recebe `paper` constante: o segundo portão é decorativo

`packages/core/hunter_core/admission/sources.py:215` (`purpose: str = PURPOSE_PAPER`),
`services/execution-worker/hunter_execution_worker/bridge.py:210-229` (`_request` não passa
`purpose`), `services/execution-worker/hunter_execution_worker/admission_cycle.py:175-188`
(`rebuild_request` não passa `purpose`), `apps/api/hunter_api/services/admission.py:183`
(`purpose=PURPOSE_PAPER` literal).

`admit()` chama `request.origin(...)` (`packages/core/hunter_core/admission/service.py:191`) em
**todos** os caminhos — correto. Mas nenhum chamador em produção passa um `purpose` que não seja
`paper`: os três construtores de `ProposalRequest` ou omitem o campo (herdando o default) ou o
cravam. O ramo `research_only` / desconhecido de `origin()` (`sources.py:263-276`) é, na prática,
código morto no runtime; sua cobertura vem só dos testes unitários.

Não é um defeito por si — é a razão de B1 ser bloqueante em vez de "defesa em profundidade
redundante". Antes da T3.15 o default era `live` e a situação era idêntica (o portão também sempre
via o rótulo admissível), então **isto não é regressão**; é uma promessa da D10 ("a admissão aceita
`paper` e recusa quem não é") que o código não cumpre porque a admissão nunca vê outro rótulo.

**Cenário concreto.** Fecha-se B1 no `bridge_screen` mas um refactor futuro reordena os checks e o
portão de propósito passa a rodar depois de um `return` antecipado. `origin()` não pega: ele recebe
`paper` porque `_request` o cravou, e a ordem volta a existir com um rótulo que ninguém conferiu.

**Correção.** `bridge._request`: `purpose=chosen.screened.signal.purpose` (o rótulo do sinal, não uma
constante). `admission_cycle.rebuild_request`: enquanto `trade_proposals` não tiver coluna/`payload`
de `purpose`, cravar `PURPOSE_PAPER` **explicitamente e com comentário** dizendo que a origem já foi
verificada no arquivamento — hoje é um default herdado, que é a forma de um valor virar outro sem
ninguém perceber.

### 4 — a ordem manual nasce `paper` (correto), mas não existe rota, e a RBAC ainda não foi escrita

`apps/api/hunter_api/services/admission.py:150-190`.

**A troca `live` → `paper` está certa** e não abre porta: a §8 do contrato manda que a ordem manual
gere `trade_proposal` (`agent_id` nulo, `actor=user`) e passe pelos mesmos checks, e é o que
acontece — `admit()` roda `origin()`, o Risk Engine decide, o kill switch vale igual. A ressalva da
D10 §6 ("se o guardian mostrar que a troca quebra a trilha de auditoria da ordem manual, plano B")
**não se aplica**: a trilha de auditoria da ordem manual não passa por `purpose` em lugar nenhum;
`actor_id`/`actor_type` continuam intactos, `request_digest` não inclui `purpose`
(`sources.py:42-59`, `REQUEST_PAYLOAD_KEYS` tem oito chaves e nenhuma é essa) e portanto a
idempotência não mudou de identidade com a troca. **Não execute o plano B.**

**Quem pode chamar `file_manual_order`: ninguém.** `grep -rln "services.admission"
apps/api/hunter_api` não devolve nenhum importador; não há rota, não há dependência de RBAC, a função
existe e só é chamada por `apps/api/tests/unit/test_admission_adapter.py:124`. A pergunta de RBAC não
tem resposta em código — o que é fail-closed hoje e uma obrigação amanhã.

**Cenário concreto.** A T3.8 (ou quem escrever a rota) copia o padrão das rotas vizinhas de
`apps/api/hunter_api/routers/portfolio.py:210` (`context: ViewerOrg`) para o `POST` de ordem manual.
Qualquer VIEWER da organização passa a abrir entradas na carteira paper principal — a mesma carteira
única por organização da §11 —, e a §8 do contrato ("ordem manual paper... `actor=user`") vira uma
frase sobre quem *aparece* no log, não sobre quem pode decidir.

**Correção.** Quando a rota for escrita: `OwnerOrg` (é o que
`apps/api/hunter_api/routers/risk.py:176` já usa para o `resume`, o outro ato que move capital),
`_owned(session, context, portfolio_id)` antes de qualquer coisa, e um teste de RBAC por papel.
Registrar isso no brief da rota agora, enquanto a decisão é barata.

### 5 — `VersionSummaryOut` não publica `purpose`: a página do Lab não distingue a coorte que gasta

`apps/api/hunter_api/schemas/lab_summary.py:109-126` e
`apps/api/hunter_api/repositories/lab_summary.py:31-39` (`VersionMeta` não carrega `purpose`).

O resumo por versão do Lab é agrupado por `strategy_version_id`, então as duas coortes aparecem em
linhas separadas — bom. Mas nenhuma das duas diz qual é qual.

**Cenário concreto.** Com `momentum v2` (paper) ativa, a página lista `momentum v1` e `momentum v2`
lado a lado, mesmo `code_ref`, mesmos parâmetros, mesmas métricas hipotéticas, e **nada** indica que
a segunda é a que compra. Quem lê para responder à pergunta da D10 ("o mesmo gatilho medido
hipoteticamente contra medido pela carteira") não sabe qual coluna é qual, e o operador que quiser
parar a coorte que gasta não sabe qual versão depreciar. `GET /lab/shadow/signals` já mostra
`purpose` por sinal (`apps/api/hunter_api/services/lab_signals.py:58`) — a inconsistência é só no
resumo.

**Correção.** `purpose` em `VersionMeta` e em `VersionSummaryOut`, lido de `strategy_versions`; um
marcador visível na página (`docs/DESIGN.md`). Barato, e é o painel pelo qual a coorte paper será
lida todo dia.

### 6 — condição da D10 ainda não medida: folga do ciclo do worker com duas coortes ativas

`services/strategy-worker/hunter_strategy_worker/catalogue.py:250-258` aceita a versão `paper` no
roster ao lado da `research_only`; as duas avaliam os mesmos mercados nas mesmas barras. A D10 pede,
com todas as letras, "medir a folga do ciclo do worker" antes do ato (208 sinais em 9 h viram
~416/dia). Não encontrei essa medição em `.claude/state`. Não é defeito de código; é uma das
condições escritas, e ela é verificável. Registrada aqui para não se perder.

---

## Depois

### 7 — `hunter_bridge_candidates_total` não publica zero por motivo conhecido

`services/execution-worker/hunter_execution_worker/metrics.py:64-77`. O item 2 do brief T3.15b pedia
"add `live_forbidden` and `unknown_purpose` **so the counters exist at zero**". O que mudou foi a
docstring; não há inicialização. O contador só é criado no primeiro `.inc()`
(`bridge.py:137`). Compare com o padrão correto que o próprio repositório já tem:
`services/strategy-worker/hunter_strategy_worker/catalogue.py:292` itera `REJECTIONS` e faz `.set(0)`.

**Cenário concreto.** Um painel "sinais `live` recusados na porta" com
`hunter_bridge_candidates_total{outcome="live_forbidden"}` devolve *no data*, não `0`. "Nenhum sinal
live jamais chegou" e "a ponte não está rodando" ficam com a mesma aparência — que é exatamente o
argumento que a própria docstring do contador usa para justificar sua existência. Vale para todos os
motivos, então é dívida da T3.14, não da T3.15b.

**Correção.** Uma tupla `REFUSAL_REASONS` ao lado do contador e um laço
`bridge_candidates_total.labels(outcome=r).inc(0)` na subida do worker.

### 8 — `origin()` sem caso de falha para rótulo desconhecido

`packages/core/tests/unit/admission/test_sources.py:57-92`. Há caso falho para `research_only` e para
`live`, e caso feliz para `paper` — falta um rótulo desconhecido (`"Paper"`, `"paper "`, `""`). O
ramo é o mesmo que `research_only` exercita, então a cobertura de linha não muda; o que falta é a
declaração de que a comparação é exata e sensível a caixa e a espaço. O portão da ponte tem esse
teste (`test_an_unknown_purpose_is_refused_unknown_purpose`); os dois deveriam espelhar-se, que é a
razão declarada de a constante ser importada e não redigitada.

### 9 — `_run` não deixa `system_events` quando a falha não é `Refused`

`infra/scripts/activate_strategy_version.py:296-306`. O `except` cobre `Refused`; qualquer outra
exceção (violação de unicidade numa corrida de dois `--paper-line`, queda de conexão) faz o
`conn.begin()` rolar tudo atrás, inclusive o evento. A docstring do módulo (`:47`) afirma "Every run
writes a `system_events` row, activation or refusal alike". É frase mais forte que o código. Baixa
severidade (a falha é barulhenta e nada foi escrito), mas a afirmação deve ser corrigida ou o código
deve passar a honrá-la numa transação própria.

### 10 — "uma linha `paper` por estratégia" é garantia de script, não de banco

`services/strategy-worker/hunter_strategy_worker/paper_line.py:88-100`. É um `SELECT` seguido de um
`INSERT` na mesma transação — TOCTOU clássico sob READ COMMITTED. Na prática a corrida é contida por
`UniqueConstraint("strategy_id", "version")`
(`packages/core/hunter_core/db/models/agents.py:72`), porque duas execuções concorrentes calculam o
mesmo `v<n+1>` e uma aborta. Ou seja: **não há cenário de falha hoje**, e por isso isto é observação,
não achado. Registro porque `docs/DATABASE.md` §22.4 enuncia a invariante como se o banco a
mantivesse; a doutrina da §11 do contrato (o índice parcial `uq_portfolios_principal_paper`) sugere o
mesmo remédio aqui: índice parcial único em `(strategy_id) WHERE purpose='paper' AND status <>
'deprecated'`.

---

## Respostas às seis perguntas

1. **Os três portões.** Ordem correta e fail-closed nos três.
   `catalogue.py:253` recusa `live` **antes** de resolver código ou parâmetros (a versão nem é
   avaliada) e publica zero em `purpose_live_forbidden` (`:292`).
   `sources.py:265-276`: `live` primeiro, por nome, com "live é Fase 4; ENABLE_LIVE_TRADING=false";
   depois `!= paper` ⇒ recusa (pega `research_only` e qualquer desconhecido).
   `bridge_screen.py:235-246`: `live` → `live_forbidden` com a mesma mensagem; `research_only` →
   `research_only`; `!= paper` → `unknown_purpose`; só `paper` passa — e antes de qualquer leitura de
   dado de mercado, como o item 5 da T3.14 pede. `PURPOSE_PAPER`/`PURPOSE_RESEARCH_ONLY` importados
   de `hunter_core.strategies.envelope` (uma grafia); `PURPOSE_LIVE` local, recusado por nome.
   **A ressalva é B1**: o portão da ponte é correto, mas julga o dado errado.
2. **Ordem manual `purpose=paper`.** Correto, não abre porta, e o plano B da D10 §6 **não** deve ser
   executado (a trilha de auditoria não passa por `purpose`; `request_digest` também não). Quem pode
   chamar `file_manual_order`: ninguém — não há rota nem RBAC. Ver "Antes de ligar" item 4.
3. **`record.py:170` e o stream.** Não há consumidor do `shadow.signals.emitted` que leia `purpose`
   do payload: o único (`bridge_consumer.py:76-107`) trata o evento como despertador e relê tudo do
   Postgres. Um consumidor antigo que exigisse `research_only` passaria a **recusar** um `paper` —
   falha fechada. O inverso é impossível: nada preenche `paper` por default. Sinais anteriores à
   T3.15 já carregavam `purpose` no envelope (o default do `SignalEnvelope`,
   `packages/core/hunter_core/strategies/envelope.py:143`), então a coorte antiga é lida como
   `research_only`, não como `""`. O `bridge_repo.py:152` termina em `or ""` ⇒ `unknown_purpose`:
   fail-closed também no caso ausente.
4. **`--paper-line`.** Copia da linha congelada, não do código (`paper_line.py:78-121`); confere o
   `code_ref` contra o build e recusa divergência (`:73-77`); exige fonte `research_only` já ativada
   (`:59-72`); uma linha paper não depreciada por estratégia (`:88-100`, ver item 10); nasce `draft`
   com `activated_at NULL` (`:106-124`); grava `system_events` (`:125-131`); `--dry-run` em todos os
   modos. **O `activate` seguinte exige**: `0002` e `0010` aplicadas, a linha não ser `live`,
   resolver código, parâmetros válidos contra o schema — e **não** exige que o `code_ref` bata com o
   congelado nem preserva o conteúdo copiado (item 1 de "Antes de ligar"). **Sim, há como ativar uma
   linha `paper` sem `system_events`**: por fora do script, com o papel `hunter_worker` (B2).
5. **`ENABLE_PAPER_AUTONOMY`.** Fonte única confirmada: `config.py:122` lê
   `Settings().enable_paper_autonomy` (`packages/core/hunter_core/settings.py:125`), nenhum parser
   local sobrou. Os **dois** motores da ponte estão atrás do mesmo booleano —
   `main.py:90-91` (o laço de 1 s) e `bridge_consumer.py:163-166` (o consumidor de stream, que com o
   flag falso nem cria o grupo, então `XINFO` não mostra uma autonomia que não existe). `/ready`
   publica `autonomy: off|on` (`bridge_consumer.py:73`, `heartbeat.py:55`). Sem ressalvas.
6. **β.** Fail-closed, confirmado. `bridge_universe.py:219-223` exige as três condições da §6 juntas
   (`available_at <= :now`, `window_end <= :now`, `valid_until > :now`, mais `valid` e
   `superseded_at IS NULL`); ausência ⇒ `current_beta` devolve `None` ⇒
   `bridge_screen.py:269-271` recusa `beta_unavailable`. Idem no caminho manual
   (`manual_inputs.py:63-64`). **Não há β = 1 implícito**: o único `BetaEstimate(value=Decimal(1))`
   do repositório está em `services/execution-worker/proof/run_proof.py:157` (harness de prova, fora
   do runtime); para as posições abertas e as reservas,
   `packages/core/hunter_core/portfolio/positions.py:67,95` usam `betas.get(...)` ⇒ `beta_btc=None`
   ⇒ o motor trata como não validado e o check `beta_validity` sai `unavailable` (rejeita), como a §6
   manda. O único frouxo é benigno: a ponte não aplica `max_beta_age_s` (só `valid_until`), então um
   β dentro do prazo mas com mais de 7200 s passa a ponte e é **recusado** pelo motor — desperdício
   de ciclo, nunca aprovação indevida.

---

## Comandos e saída real

Somente leitura; nenhuma suíte com testcontainers foi executada (regra do pedido). O que rodou:

```
$ uv run pytest packages/core/tests/unit/admission/test_sources.py -q -p no:randomly
................                                                         [100%]
16 passed in 2.75s
```

Sonda de leitura para B1 (não escreve nada, não toca o banco — `screen_signal` retorna no portão de
propósito antes de usar a sessão, por isso `None` basta):

```
$ uv run python -    # linha com supporting_features={"purpose": "paper"}, versão não consultada
v.purpose in the bridge query? False
v.status  in the bridge query? True
ShadowSignal.purpose = 'paper'
[info] bridge_candidate_refused reason=assumed_costs_unavailable signal_id=e83fbb0c-...
refused by the purpose gate? assumed_costs_unavailable
```

Leitura: a query da ponte **não** contém `v.purpose` (contém `v.status`); o `purpose` veio do JSONB;
e o portão de propósito **não** recusou — a recusa que aparece é do check de geometria seguinte.

```
$ git grep -n "UPDATE strategy_versions\|INSERT INTO strategy_versions" -- services packages apps
services/strategy-worker/hunter_strategy_worker/paper_line.py:109:  "INSERT INTO strategy_versions ("
```

Único escritor da tabela em todo o código de runtime, e roda na conexão de migração — o
`INSERT`/`UPDATE` que `hunter_worker` ainda detém (B2) não tem consumidor legítimo.

---

## Status

`DONE_WITH_CONCERNS` — o desenho dos três portões está certo e é fail-closed; o que está errado é
**qual dado o portão da ponte julga** (B1) e **o que protege a ativação** (B2). Os dois se fecham com
uma coluna no `SELECT`, um ramo de recusa novo e uma revogação de grant.

Nada foi editado fora deste arquivo. Nada commitado.

**Bloqueia ligar ENABLE_PAPER_AUTONOMY: sim.**

Com a precisão que o número merece: ligar o interruptor **hoje** não produz ordem nenhuma — não
existe linha `purpose = paper` em banco algum, não existe `agents` apontando para uma, e todo sinal
existente carrega `research_only` no envelope, logo é recusado na porta. O bloqueio não é sobre
amanhã de manhã; é sobre a **sequência**: o flag só é ligado como parte da ativação da coorte paper
(D10, condição 3), e no instante em que essa linha existir, a única coisa entre um sinal
`research_only` e uma ordem paper é um campo JSONB que o papel do worker pode escrever — com a
coluna correta a um `SELECT` de distância, já dentro do mesmo `JOIN`. Fechados B1 e B2, e com os
itens 1 e 2 de "Antes de ligar a ponte" resolvidos, retiro o bloqueio.
