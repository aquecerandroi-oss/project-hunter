# Notes — T2.6 (API do Radar, Oportunidades, Anomalias e Regime)

Owner: backend-specialist. Companion to `docs/reports/M2.md` (a escrever pelo
test-engineer/documentation-writer em T2.8). Registra decisões tomadas durante
a implementação, divergências entre documentos e pontos que T2.4/T2.5 (ainda
em voo) precisam reconciliar.

## Segunda opinião da Astra (antes de implementar)

Pergunta completa e resposta integral em `.claude/state/astra-review-T2.6-api.md`
(`bash infra/scripts/astra.sh ask T2.6-api "..."`). Pontos e reconciliação:

1. **`org_id` como query param opcional** (não `{org_id}` no path): Astra
   concordou. Implementado em `services/radar_org_derivation.py::resolve_optional_org`
   — reaproveita `principal.membership(org_id)` (mesma semântica de 404 do
   `auth/rbac.py::get_org_context`) e abre uma segunda transação
   (`tenant_session`) só para a leitura de `positions`/`portfolios`/`organizations`.
2. **Nome do campo derivado: `RISK_BLOCKED`.** Astra apontou a divergência
   entre `docs/plans/M2.md:55` (decisão conjunta, que prevalece) + o brief
   (`RISK_BLOCKED`) e `docs/DATABASE.md:220`, `docs/PIPELINE.md:118`,
   `hunter_core/domain/enums.py:268` (docstring), `docs/ROADMAP.md:86`,
   `docs/DESIGN.md:83` (`BLOCKED_BY_RISK`). Ficou com **`RISK_BLOCKED`** no
   contrato da API (`schemas/radar.py::RadarStatusFilter`,
   `schemas/opportunities.py`), por ser o que a decisão conjunta mais recente
   e o brief vigente usam. **Pendência para documentation-writer:** reconciliar
   o nome nos quatro documentos acima (ou registrar formalmente por que a API
   diverge) — não fiz essa edição porque nenhum desses arquivos está na lista
   de arquivos permitidos deste brief.
3. **Fonte de leitura do Radar: Postgres, não `radar:scores` (Redis).**
   Confirmado — `repositories/radar.py` lê `opportunities` diretamente (score
   mínimo, status, estágio, exchange, anomalia, regime, busca por símbolo,
   ordenação, cursor). `radar:scores`/`rt:radar` continuam servindo só a ponte
   de tempo real, que **já existia** antes deste brief
   (`realtime/channels.py:28,36,88` já tinha `RADAR_CHANNEL = "rt:radar"` em
   `_PUBLIC_EXACT` com throttle próprio — nada precisou ser adicionado lá).
4. **`/system/workers` + scanner:** confirmado que nenhuma mudança de produção
   era necessária — `services/system_status.py::parse_heartbeat_key`/
   `scan_heartbeats` já são genéricos por `role` (o unit test
   `test_system_workers_status.py:70` já cobria `hb:scanner:`). Adicionei dois
   testes de integração de contrato em `test_system_workers_api.py`
   (`test_workers_reports_the_scanner_role_through_the_generic_hb_scan`,
   `test_workers_absent_scanner_is_simply_missing_not_reported_unavailable`).

## Segunda opinião da Astra sobre o diff (antes de reportar DONE)

Íntegra em `.claude/state/astra-review-T2.6-api-diff.md`
(`bash infra/scripts/astra.sh ask T2.6-api-diff "..."`). Veredito inicial:
REQUEST_CHANGES — 4 must-fix, todos corrigidos nesta rodada:

1. **HIGH — `WARNING` não bloqueia entradas.** `radar_org_derivation.py`
   tratava qualquer estado ≠ `ACTIVE` (inclusive `WARNING`) como bloqueio, mas
   `RISK_ENGINE.md` §5 diz que `WARNING` **permite** entradas (tamanho × 0,5;
   `ks_multiplier` 0.5) — só `TRADING_DISABLED`/`EMERGENCY` bloqueiam de fato
   (RiskCheck #1, "`kill_switch`", é `efetivo ∈ {TRADING_DISABLED,
   EMERGENCY}`). Corrigido: `_BLOCKING_KILL_SWITCH_STATES = (TRADING_DISABLED,
   EMERGENCY)`. Teste de regressão:
   `test_list_radar_warning_kill_switch_does_not_block_entries`.
2. **MEDIUM — contrato de `risk_blocked` inconsistente.** O docstring dizia
   "never false" mas o código retornava `False` legitimamente; também não
   deixava claro que um portfolio bloqueado marca **todas** as oportunidades
   da org, mesmo as que nunca tocariam aquele portfolio. Reescrevi o
   docstring de `services/radar_org_derivation.py` para declarar exatamente
   isso: `false` = "nenhum kill switch `TRADING_DISABLED`/`EMERGENCY`
   encontrado" (não "passaria em toda checagem de risco"), e a agregação é
   por organização inteira, não por portfolio.
3. **HIGH — regime aberto podia ficar "fresco" para sempre.** Um scanner que
   morre logo após abrir uma linha de regime (`end_time IS NULL`) deixava
   `is_stale=false` indefinidamente, porque o cálculo só olhava `end_time`.
   Corrigido: `is_stale = end_time IS NOT NULL OR NOT scanner_alive`, onde
   `scanner_alive` lê o heartbeat `hb:scanner:*` (o mesmo que
   `/system/workers` já lê, via `services/system_status.scan_heartbeats`) —
   `routers/regime.py::_scanner_alive`. Falha do Redis aqui não vira 503 (o
   dado do regime em si veio do Postgres): fica conservador, `scanner_alive =
   False`. Teste de regressão:
   `test_get_current_regime_open_row_reads_stale_when_the_scanner_is_not_confirmed_alive`.
4. **MEDIUM — faltava o 503 de Postgres que o brief pede (linha 13).**
   Implementado **parcialmente**, com o limite documentado no próprio código
   (`repositories/radar_common.py::postgres_failures_as_503`): um
   `contextlib.asynccontextmanager` que traduz
   `sqlalchemy.exc.OperationalError`/`InterfaceError` (falha de conexão) em
   503 `application/problem+json`, usado nos quatro routers ao redor das
   consultas que rodam **depois** que a dependência `PrincipalSession` já
   abriu a transação. **Gap conhecido e não fechável dentro deste brief:** a
   própria `PrincipalSession` já executa `SET LOCAL ROLE`/`SET LOCAL
   app.current_user` (primeiro round-trip real) *antes* do corpo da rota
   rodar — uma queda do Postgres bem nesse instante ainda escapa como o 500
   genérico do `ProblemDetailsMiddleware`, exatamente como em **todo** outro
   endpoint do M1 que lê Postgres (`routers/markets.py` incluído). Fechar
   isso de verdade exige tocar `hunter_api/errors.py`/
   `ProblemDetailsMiddleware`, que não está na lista de arquivos deste brief.
   Testes unitários (`postgres_failures_as_503` traduz `OperationalError`/
   `InterfaceError`, não traduz `IntegrityError`) em
   `tests/unit/test_analysis_read_models.py`.

**Nice-to-have da Astra não implementados** (registrados, não bloqueantes):
sentinela de `sort=volume` pode, em tese, colidir com um `relative_volume_1h`
extremo (ratio ~1e9) quando o volume mediano histórico é ~0 — preferiria uma
chave explícita de "indisponível" a uma sentinela numérica, mas isso só
importa quando T2.4/T2.5 realmente escreverem esse valor; `repositories
/opportunities.py::list_all` busca tudo antes de paginar (mesmo padrão de
`repositories/markets.py`, aceitável na escala do M2, mas cresce com episódios
`EXPIRED` acumulados — outra decisão para T2.8/retenção); cobertura de teste
de cursor do Radar não inclui empate exato de `sort_value` nem `ASC`.

## Assunção registrada: caminho JSON do envelope de features

`opportunities.feature_snapshot`/`opportunity_history.envelope` são o "envelope"
descrito em DATABASE.md §17.3, mas T2.4 (opportunity engine) e T2.5
(scanner-worker) — os produtores reais — ainda não existem. O que já está
congelado é `hunter_indicators.features.vector.FeatureVector.as_wire()` (T2.2,
já mesclado): `{"values": {"<key>": {"value": "<decimal string>", "quality":
..., "reason": ..., "inputs": [...]}, ...}, "provenance": {...}, ...}`.

`repositories/radar_common.py::feature_value_expr` assume que o envelope
aninha esse vetor sob uma chave `"features"` (para não colidir com as chaves
do próprio envelope — `as_of`, `baseline_ids`, `regime_id`, `versions`,
`state_in`/`state_out`):

```
feature_snapshot["features"]["values"]["<key>"]["value"]
```

Duas chaves concretas usadas:
- **`atr_14_pct`** (filtro `volatility_min`/`volatility_max` do Radar) —
  `hunter_indicators.features.trend.py:78`, `FeatureDefinition(key=f"atr_{self.period}_pct", ...)`,
  período default 14. É o ATR de Wilder(14) em fração, a mesma métrica que
  alimenta o classificador de estágio EARLY/DEVELOPING/EXTENDED — confirmado
  com a Astra em vez do meu palpite inicial (um componente "Volatility" que
  **não existe** na tabela de componentes do Opportunity Engine, PIPELINE.md
  §5).
- **`relative_volume_1h`** (chave de ordenação `sort=volume`) —
  `hunter_indicators.features.volume.py:54`,
  `key=f"relative_volume_{label_for(self.window_minutes)}"`.

Ausência do valor nunca vira zero: a extração retorna `NULL` (o filtro exclui
a linha honestamente; o `sort=volume` usa uma sentinela que só afeta a
ordenação, nunca o valor exposto em `feature_snapshot`).

**Pendência explícita para quando T2.4/T2.5 aterrissarem:** se o envelope real
não aninhar o vetor sob `"features"`, ajustar só `feature_value_expr`
(um único ponto) e os testes de integração de `test_radar_api.py` que fixam
esse formato via fixture (`analysis_fixtures.py` não usa esse caminho hoje —
nenhum teste dos filtros de volatilidade/volume foi escrito por falta de
tempo; ver "Mocks/gaps restantes" abaixo).

## `change` (ordenação "mudança" do Radar)

Definido como `opportunities.score` menos o `score` da linha mais recente de
`opportunity_history` para o mesmo `opportunity_id` (`0` quando não há
histórico ainda — episódio novo, nada para comparar). Documentado em
`schemas/radar.py::RadarItemOut.change` e implementado em
`repositories/radar.py::_change_expr`.

## `risk_blocked` — escopo M2 (kill switch apenas)

M2 não tem Risk Engine (M3/M4). `services/radar_org_derivation.py` só verifica
o kill switch (`organizations.kill_switch_state` e
`portfolios.kill_switch_state` != `ACTIVE`, com o motivo de qualquer um dos
dois). `true` é definitivo; `false` significa apenas "nenhum kill switch ativo
hoje", não "esta proposta passaria em toda checagem de risco" — documentado no
docstring do módulo e nos schemas. Quando M3/M4 trouxer o Risk Engine de
verdade, este é o único ponto a estender.

## `in_position` — definitivo (não apenas kill switch)

Ao contrário de `risk_blocked`, `in_position` é computável por completo hoje:
uma posição `open`/`closing` do `portfolio` da organização no mercado da
oportunidade. `true`/`false` são ambos definitivos quando `org_id` é dado;
`null` só na ausência de `org_id`.

## Correções em arquivos fora da lista original, mas dentro de `apps/api/tests/**`

1. **`apps/api/tests/integration/conftest.py::load_script`** — bug pré-existente
   (não causado por este brief): `infra/scripts/seed.py` importa
   `from seed_reference import ...` (T2.1, database-architect) mas
   `load_script` nunca colocava `infra/scripts` no `sys.path`, então **toda**
   a suíte de integração de `apps/api` (não só T2.6) já estava quebrada antes
   desta tarefa (confirmado rodando `test_markets_api.py` sem essa correção).
   Corrigido com o mesmo padrão que `_alembic_config` já usa para
   `MIGRATIONS_DIR`.
2. **`apps/api/tests/integration/test_system_workers_api.py`** — dois bugs de
   higiene de teste pré-existentes que vazam estado no Redis
   session-scoped compartilhado por todo o arquivo/suíte:
   - `test_market_status_isolates_a_single_exchange_wrongtype_heartbeat`
     escrevia uma chave `hb:market:*` do tipo errado e nunca limpava — todo
     teste **depois** dela que faz `SCAN hb:*` completo (`/system/workers`)
     500/503ava por causa da chave corrompida alheia. Corrigido com o mesmo
     padrão `try/finally: delete` que o teste de wrongtype de `/system/workers`
     já usava.
   - Meu próprio `test_workers_reports_the_scanner_role_through_the_generic_hb_scan`
     escrevia um hash `hb:scanner:*` sem TTL (a diferença do TTL real de 30s
     que `WorkerRuntime` grava) — corrigido com o mesmo padrão.

## Correção de brief: `main.py` vs `app.py`

O brief lista `apps/api/hunter_api/main.py` como o arquivo de "registro dos
routers", mas nesta base de código o registro (`app.include_router(...)`)
sempre foi feito em `hunter_api/app.py` (`create_app`) — `main.py` só constrói
`app = create_app(...)` para o uvicorn. Registrei os quatro routers em
`app.py`, mantendo o padrão de todo router existente (`markets`, `system`
etc.), e não toquei `main.py` (nada a fazer lá).

## Escopo aceito, não implementado

- **503 explícito para Postgres fora do ar**: implementado parcialmente após
  a segunda opinião da Astra — ver "Segunda opinião da Astra sobre o diff",
  item 4, para o mecanismo e o gap conhecido (falha na abertura da própria
  `PrincipalSession`, antes do corpo da rota, ainda cai no 500 genérico, igual
  a todo outro endpoint do M1 que lê Postgres).
- **Filtros de volatilidade/volume não têm teste de integração** cobrindo o
  caminho JSON real (`feature_value_expr`) — só a query é exercitada
  indiretamente pelos testes que NÃO usam esses filtros. Não escrevi fixture
  com `feature_snapshot` no formato assumido para T2.6 propriamente dito por
  ter ficado sem tempo depois de fechar RLS/paginação/anomalias/regime, que
  são os itens obrigatórios do brief. Recomendo ao code-reviewer/test-engineer
  fechar isso quando T2.4/T2.5 confirmarem o formato real do envelope (o teste
  ficaria testando a própria suposição, não o formato real, então não é puro
  ganho fazer agora).
- **`GET /api/v1/opportunities` (lista)** não replica todos os filtros ricos do
  Radar (regime, anomaly_type, volatilidade, status derivado por org) — só
  `score_min`, `status` (nativo), `stage`, `exchange`, `q`. O brief pede a
  riqueza de filtros para `/radar`; `/opportunities` existe principalmente
  para sustentar `/opportunities/{id}` (decomposição completa).
- **`GET /api/v1/regime`**: o brief diz "atual por mercado + histórico", mas
  `market_regimes.scope` só tem `global`/`btc` (`RegimeScope`) — não há regime
  por mercado individual no schema real da T2.1. Implementado como "atual por
  escopo" (os dois valores possíveis de `RegimeScope`), que é o que o schema
  sustenta; interpretação registrada aqui em vez de inventar uma dimensão
  "por mercado" que a T2.1 não modelou.

## Arquivos renomeados em relação ao padrão `{radar,opportunities,anomalies,regime}*`

O brief lista os arquivos permitidos como `{radar,opportunities,anomalies,regime}*.py`
em `schemas/services/repositories`. Duas peças de código são compartilhadas
entre radar e opportunities (cursor keyset genérico + extração JSONB;
derivação de `in_position`/`risk_blocked`) e foram nomeadas com o prefixo
`radar_` para caber literalmente no glob, em vez de um nome genérico como
`analysis_common.py`/`org_derivation.py` que ficaria fora dele:
`repositories/radar_common.py`, `services/radar_org_derivation.py`.

## Rodada de correções do security-reviewer (2026-09-06)

Três MUST-FIX de disponibilidade, mais os nice-to-have baratos. Astra opinou
antes (`.claude/state/astra-review-T2.6-fixes.md`) e sobre o diff depois
(`.claude/state/astra-review-T2.6-fixes-diff.md`).

### Invariante novo: **nunca duas conexões simultâneas por requisição**

Declarado e implementado num único lugar,
`apps/api/hunter_api/routers/radar_common.py::analysis_scope` (módulo novo),
usado pelos quatro routers de análise (radar, opportunities, anomalies,
regime).

**O bug (MF-1, HIGH).** `routers/radar.py` e `routers/opportunities.py`
recebiam a sessão como `Depends(PrincipalSession)` — que **abre a transação
enquanto resolve a dependência**, antes do corpo da rota, e a segura até a
resposta ser montada — e só então, no corpo, chamavam
`services/radar_org_derivation.py::load_org_derivation`, que abre uma segunda
transação (`tenant_session`, com RLS). Duas conexões por requisição, para todo
chamador autenticado que passasse `org_id`. Com `db_pool_size=5` +
`db_max_overflow=5` (`packages/core/hunter_core/settings.py`, sem
`pool_timeout` explícito, logo os 30 s do `QueuePool`), dez requisições
concorrentes travam o processo inteiro: cada uma segura uma conexão e espera
30 s por uma segunda que só outra esperando poderia liberar.

**A correção.** Derivar a organização **primeiro**, numa `tenant_session`
aberta *e fechada* (a conexão volta ao pool), e só depois abrir a
`user_session` do chamador. Um `Depends` não consegue expressar "feche antes
do próximo abrir" (o FastAPI desmonta dependências de generator **depois** do
handler, não entre dependências), então a sequência é um `async with`
explícito no corpo. Foi a alternativa que a Astra preferiu à de duas
dependências encadeadas, porque preserva a precedência das validações
declarativas de query param: uma dependência resolvida antes do corpo faria,
por exemplo, `?limit=0` com organização inacessível responder 404 em vez de
422. Efeito colateral bom: a rota abre a sessão **dentro** de
`postgres_failures_as_503()`, o que fecha o "gap conhecido" registrado na
rodada anterior (queda do Postgres no primeiro round-trip da transação,
`SET LOCAL ROLE`, virava o 500 genérico).

**503 para pool esgotado.** `sqlalchemy.exc.TimeoutError` é `SQLAlchemyError`,
não `DBAPIError` — passava direto pelo tradutor e virava 500. Agora é
traduzido em `repositories/radar_common.py::postgres_failures_as_503`: é falta
de capacidade (infraestrutura), não bug de statement; o `logger.warning` com
`error_type` continua nomeando a causa para investigação. `IntegrityError`
segue 500.

**Testes.** Unit:
`test_analysis_read_models.py::test_postgres_failures_as_503_translates_pool_timeout`.
Integração, com `build_custom_app(db_pool_size=1, db_max_overflow=0)`:
`test_radar_api.py::test_list_radar_serves_an_org_scoped_request_on_a_one_connection_pool`
e `test_opportunities_api.py::test_opportunities_serve_list_and_detail_on_a_one_connection_pool`
(lista **e** detalhe — a Astra apontou que corrigir só a lista deixaria o
detalhe aninhando as duas conexões). Confirmei que falham pelo motivo certo:
invertendo a ordem dentro de `analysis_scope`, o teste do radar responde 503
com `error_type=TimeoutError` no log, depois de esperar o `pool_timeout`.

### MF-2 — `repositories/opportunities.py`: keyset em SQL, sem `decomposition`

`list_all` foi substituída por `list_page`, sobre `build_list_statement(...)`
(função de módulo, não método privado, para poder ser compilada num teste sem
banco). Três mudanças:

1. **`LIMIT limit + 1`** e seek keyset `tuple_(score, id) < (cursor)`, em vez
   de trazer a tabela inteira e varrer a lista em Python procurando o `id` do
   cursor (era o que `services/opportunities.py::build_list_page` fazia).
2. **`decomposition` deixou de ser selecionada na lista.** É a maior coluna da
   tabela e nenhum list view a renderiza. Isso muda o contrato:
   `OpportunitySummaryOut` não tem mais o campo e `OpportunityDetailOut` (que
   herda dela) passou a declará-lo. **Pendência:** `pnpm gen:types` +
   `packages/shared-types` precisam ser regerados por quem fechar a T2.6 —
   `packages/shared-types/**` não está na lista de arquivos desta rodada.
3. **Cursor passou a carregar `(score, id)`** em vez de só `id`
   (`encode_opportunity_cursor(score, row_id)`), porque um keyset precisa da
   chave de ordenação. `MAX_CURSOR_LENGTH` foi de 64 para 96.

Testes: `test_opportunity_list_statement_does_not_select_decomposition` e
`..._is_bounded_by_a_limit` (compilam o statement no dialeto postgresql, sem
banco); `test_list_opportunities_pagination_round_trip_never_skips_or_duplicates`
(5 linhas, duas empatadas em `score` para exercitar o desempate por `id`,
paginadas de 2 em 2 até o fim, sem duplicar nem pular);
`test_list_opportunities_omits_decomposition_and_detail_carries_it`.

### MF-3 — `include_envelope=true` × `history_limit`

Teto de 50 (`schemas/opportunities.py::MAX_ENVELOPE_HISTORY_LIMIT`) quando
`include_envelope=true`; 500 (`MAX_HISTORY_LIMIT`) sem ele. A regra está numa
função pura, `routers/opportunities.py::resolve_history_limit`, com uma
distinção que o brief não especificava e que decidi assim:

- `history_limit` **explícito** acima de 50 com envelope: **422**
  (`envelope-history-limit`, mensagem nomeando os dois tetos). O chamador
  escolheu um número e precisa saber que não será honrado; truncar em silêncio
  devolveria uma trajetória incompleta que ele plotaria como completa.
- `history_limit` **omitido**: o default se adapta (100 sem envelope, 50 com).
  Um `?include_envelope=true` puro tem de continuar funcionando; 422 num valor
  que o chamador nunca escolheu seria regressão — foi exatamente o que o teste
  pré-existente `test_get_opportunity_detail_history_hides_envelope_unless_requested`
  pegou quando a primeira versão aplicava o teto também ao default de 100.

Documentado no `description=` dos dois query params (aparece no OpenAPI) e no
docstring de `MAX_ENVELOPE_HISTORY_LIMIT`. Testes:
`test_resolve_history_limit` (paramétrico) e
`test_resolve_history_limit_explicit_over_the_envelope_cap_is_422` (unit),
`test_get_opportunity_envelope_caps_history_limit` (integração).

### Nice-to-have entregues nesta rodada

- **Docstring de `schemas/regime.py::RegimeOut.is_stale`** reescrito: agora
  descreve os **dois** casos (`end_time` preenchido **ou** linha aberta sem
  heartbeat `hb:scanner:*` vivo), que é o que `routers/regime.py::_scanner_alive`
  implementa desde a rodada anterior. O texto antigo dizia explicitamente
  "never asserted on a genuinely open regime", o contrário do comportamento.
- **`Decimal` de query com `ge`/`le` finitos:** `score_min` (radar e
  opportunities) e `min_severity` (anomalies) em `0..MAX_SCORE` (100 — a
  coluna é `NUMERIC(5,2)` com escala 0–100, PIPELINE.md §3 e §5);
  `volatility_min`/`volatility_max` em `0..MAX_VOLATILITY` (1000, teto
  generoso: `atr_14_pct` é fração). Sem limite finito, `?score_min=NaN` e
  `?score_min=Infinity` chegavam ao Postgres. As constantes são `int` porque
  `Query(ge=, le=)` tipa `float | None`; a comparação contra `Decimal` é exata.
- **Cursor com `Decimal` não finito: 422 `invalid-cursor`** (não 500), em
  `decode_sort_cursor` (radar) e `decode_opportunity_cursor`.
- **Cursores de `anomalies`/`regime` recusam timestamp naive** (422): as
  colunas são `timestamptz` e um valor sem offset seria comparado "no fuso que
  a sessão tiver", deslocando a fronteira da página em silêncio. O encoder
  nunca emite um, então só vem de cursor construído à mão.
- **`q` escapa `%`/`_`** (`repositories/radar_common.py::like_contains` mais
  `escape=LIKE_ESCAPE`), no radar e em opportunities. Antes, `?q=%` casava
  todo o universo.
- **`Organization.deleted_at IS NULL`** no `_kill_switch_block` de
  `services/radar_org_derivation.py` (o filtro equivalente de `Portfolio` já
  existia).

### Continua fora de escopo (registrado, não corrigido)

- **`anomalies` só tem índice em `detected_at`** — a paginação keyset é
  `(detected_at, id)` e os filtros (`type`, `status`, `market_id`,
  `min_severity`) são resolvidos por filtro pós-índice. Índice composto é
  decisão do `database-architect` e exige migração, fora desta lista de
  arquivos.
- **`?status=HOT&status=RISK_BLOCKED` devolve a lista inteira** quando a
  organização está bloqueada: `RISK_BLOCKED` é um predicado por organização,
  não por linha, então em `OR` com qualquer outro status ele satura o
  resultado (`repositories/radar.py::_status_condition` devolve
  `Opportunity.id IS NOT NULL`). É semanticamente correto (toda oportunidade
  *está* bloqueada para aquela org), mas provavelmente não é o que a UI quer;
  precisa de uma decisão de produto antes de virar código.
- **`request.state.org_id` nos logs** — o `org_id` derivado não é anexado ao
  contexto de log da requisição, então um 503 de derivação não diz de qual
  organização veio. Exige tocar o middleware de logging, fora desta lista de
  arquivos.
- **`pnpm gen:types` / `packages/shared-types`** — ver MF-2, item 2.
- **`infra/scripts/check_file_size.py` reprova 4 arquivos**, todos em
  `packages/indicators/hunter_indicators/` (`opportunity/components.py` 466,
  `regime/model.py` 465, `opportunity/status.py` 421, `opportunity/model.py`
  383). São da T2.4/T2.5 do `quant-engineer`, que aterrissaram enquanto esta
  rodada acontecia — nenhum arquivo de `apps/api` está acima do orçamento.
  Registrado aqui porque o comando do brief falha por causa deles.

### Segunda opinião da Astra sobre estas correções

Íntegra em `.claude/state/astra-review-T2.6-fixes-diff.md`. Veredito:
REQUEST_CHANGES. Reconciliação:

**Corrigido nesta rodada:**

1. **`postgres_failures_as_503` não capturava `OSError`.** Uma conexão nova
   recusada (`ConnectionRefusedError`, falha de DNS) é levantada pelo asyncpg
   *antes* de o SQLAlchemy ter um erro DBAPI para embrulhar, então continuava
   virando 500. `auth/principal.py:203` já captura `OSError` junto de
   `OperationalError` exatamente por isso — agora o tradutor faz o mesmo.
   Teste: `test_postgres_failures_as_503_translates_a_refused_socket`.
2. **Nomes de teste corrompidos por um `sed` meu.** Ao renomear
   `_resolve_history_limit` para `resolve_history_limit` (pyright reclamava de
   uso de nome privado fora do módulo), o `sed` renomeou também
   `test_resolve_history_limit` para `testresolve_history_limit`. Os testes
   ainda eram coletados (o padrão default do pytest é `test*`, não `test_*`) e
   passavam, mas o nome estava errado. Corrigido.
3. **O empate de `score` ficava dentro de uma página.** Os scores do teste de
   paginação eram `90/80/70/70/60` com `limit=2`: as duas linhas empatadas
   caíam juntas na página 2, então o desempate por `id` na **fronteira** do
   cursor nunca era exercitado. Agora são `90/80/80/70/60`, com o empate
   atravessando a fronteira página 1 → página 2.
4. **`like_contains` só tinha controle negativo na integração.** Os dois testes
   (`radar` e, novo, `opportunities`) agora fazem `?q=%` (vazio) **e** uma
   busca por substring real do símbolo (encontra) sobre os mesmos dados, para
   que o resultado vazio não possa vir de o filtro estar simplesmente quebrado.

**Aceito como correto, mas fora desta lista de arquivos:**

5. **Timeout de pool durante a autenticação ainda vira 500.** `CurrentPrincipal`
   (`auth/rbac.py:116` → `auth/principal.py:203`) resolve antes de
   `analysis_scope` e captura só `OperationalError`/`OSError`; um
   `sqlalchemy.exc.TimeoutError` em `PrincipalResolver._load` escapa como 500.
   `auth/**` está explicitamente fora do escopo deste brief. **Pendência para
   o security-reviewer/orquestrador:** vale um MUST-FIX próprio em `auth/`,
   porque atinge **todos** os endpoints autenticados, não só os quatro da T2.6.
6. **`packages/shared-types` desatualizado** (`api.d.ts:1465` ainda exige
   `decomposition` na lista) — já registrado em MF-2, item 2. Regerar com
   `pnpm gen:types` antes de fechar a T2.6.

**Registrado, não implementado:**

7. **Paginação sobre um ranking vivo.** O keyset `(score, id)` é estável para
   dados estáveis, mas o scanner reescreve `score` continuamente: uma linha
   ainda não vista que suba de 70 para 90 depois de o cliente já ter passado
   do 80 desaparece da continuação, e uma já vista que caia pode reaparecer.
   É a propriedade normal de qualquer cursor sobre um ranking mutável (um
   snapshot exigiria `REPEATABLE READ` ou uma coluna imutável de ordenação), e
   é aceitável para a UI do radar — **não** para uma exportação que se diga
   completa. Se alguém construir exportação sobre este endpoint, ordenar por
   `first_seen_at`/`id` é o caminho.
8. **`history_has_more`/limite efetivo no detalhe** (sugestão da Astra): hoje
   o cliente não sabe se existe histórico além da janela devolvida. Recusei
   por ser mudança de contrato de schema no fim de uma rodada de correção de
   disponibilidade; entra melhor junto com a regeração de `shared-types`.
