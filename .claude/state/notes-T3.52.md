# notes-T3.52 — o regime horário vira porteiro de elegibilidade, por versão

**Quando:** 2026-09-08 23:20 → 2026-09-09 03:10 BRT (UTC−3) · em UTC, 2026-09-09 02:20Z → 06:10Z.
**Quem:** quant-engineer. **Base:** `main` @ `7e64df1`. **Nada commitado, nada ativado, nada escrito na VPS.**

## 1. As restrições, ditas de volta antes de escrever código

1. **O portão fica fora do fecho.** `packages/core/hunter_core/strategies/{aggregate,base,canonical,envelope,indicators,numeric,schema}.py` não são tocados: são o fecho de toda versão viva e o `code_ref` congelado de cada linha ativada é o sha256 do módulo da estratégia — mexer neles descasa o catálogo do build e o worker recusa a versão inteira (`code_ref_mismatch`).
2. **O gancho já existe.** `StrategyContext` carrega `eligible`/`eligibility_reason` desde a S1 e **toda** estratégia começa o `explain` com `if not ctx.eligible: return Evaluation(None, INELIGIBLE, "ineligible", {"eligibility_reason": ...})`. `INELIGIBLE` não decide, não re-arma o slot e não gasta a barreira (`episodes.py`). Então o portão é uma decisão do **worker** ao montar o contexto — nenhuma linha de estratégia muda, nenhum digest muda.
3. **A política é por versão e vive na linha da versão**, não em `parameters` (ver §2).
4. **Não-antecipação:** a linha de regime usada é a **hora fechada anterior** ao corte — a última linha horária com `end_time <= source_bar_close`. Uma decisão às 15:30 enxerga a linha `[14:00, 15:00)`, nunca a `[15:00, 16:00)`.
5. **`UNKNOWN` e ausência recusam**, com motivo (`regime_gate:unknown`), nunca com um rótulo inventado.
6. **O replay aplica a mesma regra** porque é a mesma função: `replay` chama `decide.evaluate_slot` → `build_market_context`, e a leitura de `market_regimes` é cortada em `source_bar_close` como as velas.

## 2. Onde a política mora — a decisão que o database-architect tomaria (não há um vivo para perguntar; a opinião é esta, e o critério é o `docs/DATABASE.md` §1, §16.1, §17.1, §22, §28)

**Escolhido: coluna nova `strategy_versions.eligibility_policy JSONB NULL` (migração `0017_eligibility_policy`), congelada pela primeira ativação junto com as outras oito colunas.**

As alternativas e por que caem:

- **chave reservada em `default_parameters`** — recusada por três razões, cada uma sozinha bastaria. (i) O `parameters_schema` congelado do pai é quem valida o conjunto (`activation.validate_parameters`) e ele **não declara** a chave; `derive_variant.py` recusa explicitamente `--set` de parâmetro que o schema não declara. (ii) O conjunto é o que a estratégia lê: pôr ali uma chave que o código do fecho ignora faria `params_hash` distinguir experimentos que o código não distingue. (iii) Mudar `parameters_schema` para aceitá-la seria editar o fecho (`schema.py`) e mexer nos digests `ab2e0398…` (momentum_v1) / `a970c9d9…` (mean_reversion_v1), exatamente o que o brief proíbe.
- **tabela própria (`strategy_version_policies`)** — uma linha por versão, 1:1, sem histórico próprio (a política é congelada com a versão): seria uma junção a mais em todo carregamento de roster para representar um campo que nasce e morre com a linha. A §1 do DATABASE.md reserva JSONB para "dados de forma variável" e proíbe JSONB "para campos que serão filtrados com frequência" — este nunca é filtrado em SQL: é lido junto com a versão e interpretado em Python.
- **um enum/coluna escalar (`regime_allow text[]`)** — resolveria hoje e não resolveria o próximo portão (sessão, β, breadth). A forma `{"regime": {...}}` é um envelope de políticas com uma política dentro, e o parser **recusa chave desconhecida** — fail-closed, nunca "ignora o que não entende".

Consequências que a escolha traz de graça, e que são o motivo dela:

- **congelamento**: `0017` substitui o corpo do gatilho `shadow_freeze_strategy_version` (a mesma técnica que a `0010` usou sobre a `0002`, DATABASE.md §22) acrescentando `eligibility_policy` à lista congelada. Uma política que pudesse mudar depois da ativação mudaria em silêncio o significado de toda coorte já medida com aquela versão;
- **grants**: a `0010` revogou `INSERT/UPDATE` de tabela do `hunter_worker` e re-concedeu **coluna a coluna**, nomeando as colunas de então. Uma coluna nova, por construção, **não** entra nessa lista — logo só a conexão dona (`DATABASE_URL_MIGRATIONS`, que é como `derive_variant.py` escreve) consegue escrevê-la. Isso não é sorte: é a propriedade que a `0010` desenhou, e a `0017` a herda sem uma linha de DDL;
- **downgrade recusa** enquanto existir linha com política não nula: derrubar a coluna faria uma versão que só decide em `SIDEWAYS` voltar a decidir em qualquer regime — silenciosamente, e sem nada de que reconstruir a intenção (§17.7, §22, §28.3).

**Forma do JSON** (validada na leitura, recusada na dúvida):

```json
{"regime": {"scope": "btc", "classifier_version": "regime_hourly_v1",
            "rule": "previous_closed_hour", "allow": ["SIDEWAYS"]}}
```

`scope` e `rule` têm default e lista fechada de valores aceitos; `allow` é não-vazia e só aceita rótulos de `MarketRegime`. `UNKNOWN` em `allow` é recusado na origem (deixar uma versão decidir em aquecimento do classificador seria decidir sem contexto e chamar isso de contexto). **Correção (T3.52b, ressalva R4 do arquiteto): `classifier_version` tem default mas *não* tem lista fechada** — este parágrafo dizia que tinha, e estava errado. O nome nasce no produtor (T3.43) e fechá-lo em gramática tornaria cada classificador novo uma migração; quem fecha a lista é o banco, na escrita, em `derive_variant.py` (`_refuse_a_gate_with_no_series`, DATABASE.md §29.7).

## 3. A regra do corte, o argumento inteiro (e a correção que o brief pediu para eu escrever)

A série horária da T3.43 (`scope = btc`, `classifier_version = regime_hourly_v1`) grava **uma linha por hora, fechada**: `start_time = ts`, `end_time = ts + 1h`. E — isto é o que o brief supôs ao contrário, e vale registrar — a linha da hora `ts` é decidida **com velas que já eram finais em `ts`** (`hunter_indicators.regime.hourly.contiguous_closes` para em `ts`; PIPELINE §4b item 1: "rotular a hora *seguinte* ao dado é o que faz a junção honesta"). Ou seja: usar a linha que **contém** o corte (`[15:00,16:00)` para uma decisão às 15:30) já **não** seria antecipação.

**Mesmo assim a regra implementada é a do brief — a hora fechada anterior (`end_time <= source_bar_close`)** — e as razões são três, nenhuma delas "por precaução":

1. **É verdadeira sob as duas leituras.** Se algum dia a convenção de rotulagem da série mudar (ou uma segunda série entrar no mesmo escopo), a regra continua sem antecipar. A outra depende de uma propriedade de *quem escreve*, e o portão fica do lado de quem lê.
2. **Não depende da latência do produtor.** A linha `[15:00,16:00)` é escrita pela passada horária logo depois das 15:00; uma decisão às 15:02 com o job atrasado não encontraria linha nenhuma e seria recusada por `regime_gate:unknown` — um portão que oscila com o atraso de um job não é um portão, é um sorteio. A linha `[14:00,15:00)` já está escrita há mais de uma hora.
3. **O replay e a faixa viva usam a mesma linha.** No replay a série está inteira; na faixa viva, não necessariamente. A regra que iguala os dois é a que só olha para trás.

**Custo declarado:** a decisão passa a ser cortada por um contexto de **61 a 119 minutos** de idade (a linha `[14:00,15:00)` foi decidida com dados até 14:00 e vale para decisões entre 15:00 e 16:00), contra 1 a 60 minutos se a linha contendo o corte fosse usada. É uma escolha de política, não de aritmética: mudá-la é `"rule"` nova no JSON (o parser recusa rótulo de regra que não conhece), nunca uma edição silenciosa deste código.

## 4. O que foi escrito (e o que **não** foi tocado)

**Migração `0017_eligibility_policy`** (`infra/migrations/ddl/eligibility_policy.py`,
`infra/migrations/versions/0017_eligibility_policy.py`, documentada em `docs/DATABASE.md` §29):
coluna `jsonb NULL`, gatilho de congelamento substituído, guarda de downgrade, nenhum `GRANT` (a
`0010` já deixou a forma pronta: coluna nova = fora de toda concessão = só o dono escreve).

**Achado que quase virou regressão silenciosa.** A primeira versão do módulo copiou a lista
congelada da `0010` — o precedente óbvio — e teria **estreitado** o gatilho de volta, desprotegendo
`replication_parent_id`/`replication_index` que a `0012` havia congelado: um irmão de replicação
poderia ser reapontado para outro pai depois de ativado. Quem pegou foi
`test_0012_freezes_the_lineage_but_leaves_the_marker_writable`, que existe exatamente para isso. A
lista correta é a da `0012` **mais** `eligibility_policy`, e o downgrade chama o criador da `0012`.

**Worker** (`services/strategy-worker/hunter_strategy_worker/`):

| arquivo | o que muda |
|---|---|
| `regime_gate.py` (**novo**) | política (parse/recusa), veredito puro (`evaluate_gate`) e a leitura da linha horária (`load_gate`). A regra de corte **é** a query, por isso as duas moram juntas |
| `variant.py` (**novo**) | a metade pura do `derive_variant.py` (overrides, forma canônica, linhagem) + `resolve_policy`/`policy_note` — extraída porque o script bateu no teto de 350 linhas e porque só pacote instalado é importável dentro da imagem |
| `context.py` | o portão entra **depois** das checagens de mercado e antes do `build_context`; `Provenance` ganha o veredito |
| `record.py` | o bloco `provenance.regime_gate` no envelope (id, hora, rótulo, política) |
| `catalogue.py` / `roster.py` | lê e **parseia uma vez** a coluna; versão com política ilegível não entra no roster (`policy_unreadable`) |
| `decide.py` | passa a política da versão; docstring separando o *carimbo* (`regime_v0`, escopo global) do *portão* (horário, escopo btc) |
| `health.py` / `main.py` | `migration_present` passa a exigir `strategy_versions.eligibility_policy`: sem a `0017` o worker **recusa subir** em vez de estourar `UndefinedColumn` a cada roster |
| `activation_db.py` | `policy_column_present()`; `load_row` **não** passa a selecionar a coluna (as outras quatro rotas não a usam e falhariam num banco uma migração atrás) |
| `activate_derived.py` | `LINEAGE_RE` ganha o segmento **opcional** de política depois do `params_hash` (formato estendido, não reescrito: toda variante já gravada casa exatamente como casava) |

**Script** (`infra/scripts/derive_variant.py`): `--policy regime=<escopo>:<RÓTULO>[,...]` ou
`--policy none`; sem a opção a variante **herda** o portão do pai; a checagem de duplicata passa a
comparar `code_ref` + `params_hash` + **portão**; a linhagem carrega o portão.

**Não tocado, de propósito:** os sete módulos do fecho, `services/scanner-worker/**` e
`hunter_indicators/features/**` (T3.46f), `.env*`, qualquer container do stack local, a VPS.

## 5. Provas (saída real colada)

```
$ uv run pytest services/strategy-worker/tests/test_regime_gate_policy.py -q
...................................                                      [100%]
35 passed in 1.66s

$ uv run pytest services/strategy-worker/tests/test_regime_gate.py -q
.........                                                                [100%]
9 passed in 79.95s (0:01:19)

$ uv run pytest services/strategy-worker/tests/test_derive_variant.py -q
..............                                                           [100%]
14 passed in 54.57s

$ uv run pytest packages/core/tests/integration/test_migrations.py -q \
      -k "adds_the_purpose_column or 0012 or 0013 or 0014 or 0015 or 0016 or 0017"
..............................................................           [100%]
62 passed, 49 deselected in 142.61s (0:02:22)

$ uv run pytest packages/core/tests/integration/test_migrations.py -q \
      -k "not 0012 and not 0013 and not 0014 and not 0015 and not 0016 and not 0017"
..................................................                       [100%]
50 passed, 61 deselected in 222.98s (0:03:42)

$ uv run pytest services/strategy-worker/tests -q -m "not integration"
........................................................................ [ 25%]
........................................................................ [ 51%]
........................................................................ [ 77%]
.............................................................            [100%]
277 passed, 199 deselected in 9.39s

$ uv run pytest services/strategy-worker/tests/test_shadow_decisions.py -q
...............                                                          [100%]
15 passed in 110.09s (0:01:50)

$ uv run pytest services/strategy-worker/tests/test_version_roster.py -q
.........                                                                [100%]
9 passed in 33.49s

$ uv run pytest services/strategy-worker/tests/test_replay_lookahead.py -q
......                                                                   [100%]
6 passed in 58.62s

$ uv run pytest infra/scripts/tests/test_derive_variant_lineage.py -q
..............................                                           [100%]
30 passed in 2.31s

$ uv run ruff check <arquivos da tarefa>
All checks passed!

$ uv run pyright services/strategy-worker/ infra/scripts/derive_variant.py \
      packages/core/hunter_core/db/models/agents.py
  ...tests/test_replay_stress.py:35:50 - error: "_delayed" is private ... (reportPrivateUsage)
  ...tests/test_replay_stress.py:35:60 - error: "_plan_for" is private ... (reportPrivateUsage)
2 errors, 0 warnings, 0 informations
# os dois sao PRE-EXISTENTES, num arquivo que esta tarefa nao tocou (git diff vazio nele);
# os arquivos da T3.52, sozinhos, dao 0 errors.

$ uv run python infra/scripts/check_file_size.py
error   370 > 350  packages/core/hunter_core/strategies/mean_reversion_h1_v1.py
error   362 > 350  services/scanner-worker/hunter_scanner_worker/coverage.py
scanned 583 files; 2 over budget, 0 grandfathered
# os dois sao de outros agentes (T3.54 e T3.46f); os arquivos da T3.52 estao todos abaixo do teto
# (agents.py 350 exato, derive_variant.py 331 depois da extracao para variant.py).
```

**Disciplina de container declarada:** toda invocação de pytest com testcontainers rodou em
primeiro plano, **uma de cada vez**, nunca duas simultâneas (a regra do brief é no máximo duas; o
risco que ela protege é a concorrência, e a concorrência aqui foi zero). O arquivo de migrações
precisou de duas invocações porque a passada inteira ultrapassa o teto de 5 min por comando.

## 6. Números e suposições que tive de assumir (nenhum medido nesta tarefa)

1. **`MAX_STALENESS = 2 h`** — inventado aqui, e declarado: sob a regra do corte uma série completa
   nunca passa de 1 h de idade, então 2 h é exatamente uma hora de folga para o produtor. Acima
   disso o portão recusa (`stale`) em vez de decidir com o regime de anteontem. Não há medida de
   quantas vezes isso dispara na VPS; é a primeira coisa a olhar depois do deploy.
2. **27 % de `UNKNOWN`** — número da T3.43 (207 de 745 horas do backfill de 31 dias, medido no
   stack local em 2026-09-08), citado, não remedido. É o piso da perda de população de qualquer
   braço com portão, e está previsto no EXP-0020 como previsão a conferir.
3. **`regime_gate:unknown` cobre dois fatos** (linha ausente e `UNKNOWN` do classificador), como o
   brief pediu; a distinção fica em `detail` (`no_row`, `stale`, `classifier_warmup`), que vai para
   o log de avaliação e para o ledger do replay. Se a decomposição pedir os dois separados no
   próprio motivo, é mudança de vocabulário — barata, mas é decisão de quem lê o ledger.
4. **Custo por barra:** uma consulta indexada a mais por avaliação de versão com portão
   (`ix_market_regimes_scope_start`, `LIMIT 1`). Não medido; para o replay de 31 d × 4 mercados são
   ~12 mil leituras de uma linha. Versão sem portão: **nenhuma** consulta a mais.

## 7. O que fica em aberto (item 4 do brief — só depois do deploy pelo orquestrador)

Derivar `mean_reversion v9` (de v6, `SIDEWAYS`) e `momentum v9` (de v8, `BTC_BULL`), ativar como
`research_only`, replayar 31 d × 4 mercados, avaliar pareado contra o pai, estresse se K1
sobreviver, veredito e ate 10 linhas para o Everton. **Nada disso foi feito**; a VPS continua
somente-leitura para esta tarefa. Rascunho do experimento em
`.claude/state/exp-drafts/EXP-0020-regime-gate.md`.

Uma consequência do deploy que o orquestrador precisa saber: **o `strategy-worker` recusa iniciar
sem a `0017`**. O `compose.sh update` roda `alembic upgrade head` antes de subir os serviços
(DEPLOYMENT.md §3.4), então a ordem já é a certa — mas um rollback do banco sem rollback da imagem
deixaria o worker fora do ar, alto e visível, em vez de decidindo sem portão em silêncio. É a troca
escolhida.

## 8. Uma observação que não é desta tarefa, mas ficou medida

`uv run pytest packages/core/tests apps/api -q -m "not integration"` (as duas suítes no **mesmo**
processo) dá `1 failed, 1662 passed`:
`packages/core/tests/unit/test_runtime.py::test_role_registry_starts_empty_for_t03`. Isolado, o
mesmo teste passa (`1 passed`), e `packages/core/tests` sozinho dá `1140 passed`. É poluição de
registro global entre suítes (importar o app da API registra papéis antes do teste que exige o
registro vazio) — nada nesta tarefa registra papel nenhum, e nenhum arquivo de runtime foi tocado.
Registrado aqui porque foi medido, não porque é meu para consertar.

## T3.52c

**Escopo:** fechar três pendências deixadas por um agente anterior que travou sem gravar nada
durável — (1) teste de testcontainers para `health.migration_present`/`_objects_exist`, (2) teste
puro comparando `activate_derived.LINEAGE_RE` com `variant.LINEAGE_RE` e cobrindo `keep_lineage`
com o segmento `| policy=...`, (3) reordenar `docs/ACTIVATION.md` para §7c vir depois de §7b.

**Achado antes de escrever qualquer coisa:** (2) e (3) já estavam feitos na árvore compartilhada
(trabalho não commitado de outro agente para T3.52/T3.52b):

- `services/strategy-worker/tests/test_regime_gate_policy.py` já tem
  `test_the_two_written_out_copies_of_the_lineage_prefix_agree`
  (`ACTIVATE_DERIVED_LINEAGE_RE.pattern == LINEAGE_RE.pattern`) e
  `test_activation_keeps_the_policy_segment_when_only_the_gate_moved`
  (`keep_lineage` preservando `| policy=btc:SIDEWAYS`) — exatamente o que o brief pedia. Rodei o
  arquivo isolado para confirmar: `37 passed in 2.10s`. Não dupliquei o teste.
- `docs/ACTIVATION.md` já tem a ordem §7 (linha 196) → §7b (linha 257) → §7c (linha 318). Conferido
  com `grep`; nenhuma edição foi feita (nem toquei no arquivo).

Só (1) exigia código novo.

**Arquivo criado:** `services/strategy-worker/tests/test_health_migration_present.py` (56 linhas).
Duas classes de prova, uma classe de teste:

- `test_a_missing_required_column_turns_it_false`, parametrizado sobre `health._REQUIRED_COLUMNS`
  (a tupla real, importada — não reescrita — para que um typo lá vire teste vermelho em vez de
  sonda que nunca acusa): `ALTER TABLE <table> DROP COLUMN <column>` dentro da própria sessão,
  `_objects_exist(session) is False`, depois `session.rollback()` — DDL é transacional no Postgres,
  então o rollback devolve a coluna para a próxima parametrização e para o resto do container.
- `test_at_head_every_required_object_and_column_is_present`: `migration_present(db_session_factory)
  is True` no schema migrado até `head` pela fixture `migrated_db_url` do `conftest.py`.

**Comandos rodados (primeiro plano, `timeout 290`, um único arquivo de testcontainers, uma única
invocação):**

```
$ timeout 290 uv run pytest services/strategy-worker/tests/test_health_migration_present.py -q
...                                                                      [100%]
3 passed in 25.78s
```

(a primeira passada, antes do ajuste de `pyright: ignore`, também deu `3 passed in 27.95s` —
confirma que a correção de lint não mudou comportamento.)

```
$ timeout 120 uv run ruff check services/strategy-worker/tests/test_health_migration_present.py
All checks passed!
$ timeout 120 uv run ruff format --check services/strategy-worker/tests/test_health_migration_present.py
1 file already formatted
$ timeout 180 uv run pyright services/strategy-worker/tests/test_health_migration_present.py
0 errors, 0 warnings, 0 informations
```

`pyright` só reclamou de `reportPrivateUsage` para `_REQUIRED_COLUMNS`/`_objects_exist` — o brief
pede exatamente esses dois nomes privados, então segui o precedente já usado no repo
(`apps/api/tests/unit/test_radar_coverage_service.py`): `# pyright: ignore[reportPrivateUsage]`
por nome importado, não por linha inteira.

**Arquivos tocados por mim, e só estes:**
- Criado: `services/strategy-worker/tests/test_health_migration_present.py`
- Modificado: `.claude/state/notes-T3.52.md` (este apêndice)

Nada em `services/strategy-worker/hunter_strategy_worker/**`, `infra/scripts/derive_variant.py` ou
`packages/core/tests/integration/*` foi editado (só lidos, para entender o padrão de fixture e
confirmar que (2)/(3) já estavam prontos). Nenhum `git add`/`commit`/`stash`/`reset` rodado.

**Preocupação:** nenhuma nova. A árvore continua com o volume grande de mudanças não commitadas de
outros agentes descrito nas notas acima; não toquei em nenhum desses arquivos.

## T3.52b — as ressalvas R2/R4/R5 da revisão do arquiteto, fechadas

**Quando:** 2026-09-09, manhã BRT. **Quem:** database-architect. **Nada commitado, nada ativado, VPS somente-leitura.** Nenhuma migração nova: a `0017` é a mesma que o arquiteto revisou, e o schema não mudou uma linha.

### R2 — a prova de privilégio agora é feita **como o papel**

`test_0017_leaves_the_gate_readable_by_both_roles_and_writable_by_neither` pergunta ao catálogo (`has_column_privilege`), e um catálogo é uma afirmação sobre o que *deveria* acontecer. A recusa medida entrou no caso parametrizado de `packages/core/tests/integration/test_schema_privileges.py::test_the_worker_cannot_write_any_of_the_replication_columns` — `("eligibility_policy", "'{}'::jsonb")` —, que roda um `UPDATE` de verdade numa conexão `hunter_worker` e espera `permission denied`. As duas provas estão citadas lado a lado em `docs/DATABASE.md` §29.4, com o motivo de a segunda existir (é a lição da §15.6: ausência de `GRANT` não é recusa medida).

### R4 — `classifier_version` não tem lista fechada, e a §2 destas notas dizia que tinha

A frase da linha 38 foi corrigida no lugar. O nome do classificador nasce no produtor (T3.43); fechá-lo em gramática tornaria cada classificador novo uma migração. Quem fecha a lista é o banco, **na escrita**: `infra/scripts/derive_variant.py::_refuse_a_gate_with_no_series` recusa `--policy` quando não existe nenhuma linha de `market_regimes` para o par `(scope, classifier_version)`, e a mensagem nomeia o par. Vale no `--dry-run`. É `SELECT` puro pela conexão dona, sobre tabela global (sem RLS).

**Limite deliberado:** um portão **herdado** não é reconferido — ele já passou por aqui quando foi escrito, e reconferi-lo faria uma variante de `--set` ser recusada porque a série do produtor foi podada. Quem cobra série ausente em tempo de decisão é o próprio portão (`regime_gate:unknown`/`no_row`). Os dois lados estão provados em `services/strategy-worker/tests/test_derive_variant.py` (`..._whose_pair_has_no_series_in_market_regimes`, `..._inherited_gate_is_not_re_checked_...`). Escrito em `docs/DATABASE.md` §29.7.

**Custo declarado:** `infra/scripts/derive_variant.py` ficou em **350 linhas exatas** (o teto). Para caber, três docstrings do próprio arquivo foram condensadas e dois parágrafos do cabeçalho, fundidos — nenhum argumento se perdeu, todos estão na §29.7. O arquivo está cheio: a próxima coisa que entrar aqui exige extração, e o único destino é `hunter_strategy_worker.variant` (pacote instalado), que esta tarefa não podia tocar.

### R5 — a lista congelada é comparada inteira, não por substring

`packages/core/tests/integration/test_migrations.py` ganhou `_frozen_columns(body)`, que lê do corpo instalado a lista que o gatilho realmente compara (`NEW.x IS DISTINCT FROM OLD.x`, os dois lados capturados). `test_0017_widens_the_freeze_trigger_to_cover_the_policy` compara com `ddl.eligibility_policy._FROZEN_COLUMNS_0017` (**11** nomes) e `test_0017_reverses_on_a_database_where_nothing_is_gated` com `ddl.replication._FROZEN_COLUMNS_0012` (**10**, `replication_index` incluído). Um `in` passa em qualquer superconjunto: vê coluna chegar, nunca vê coluna sair.

**Achado, e não era teoria.** O `assert "promising_at" not in body` da `0017` **não podia falhar nem passar por mérito**: as palavras `promising_at` estão no corpo, no `HINT` que diz que o marcador continua mutável. Com a comparação exata, o teste falhou de verdade na primeira corrida e agora afirma o que queria afirmar — `{"promising_at", "promising_by"}` fora da lista congelada, e o `HINT` ainda dizendo isso ao operador.

### Provas (saída real)

```
$ uv run pytest packages/core/tests/integration/test_schema_privileges.py -q -p no:randomly -k eligibility
1 passed, 42 deselected in 23.87s

$ uv run pytest packages/core/tests/integration/test_migrations.py -q -p no:randomly -k "0017 or 0012"
1 failed, 34 passed, 76 deselected in 110.96s (0:01:50)
# o unico failed e PRE-EXISTENTE e nao e desta tarefa: ver "Pendencia" abaixo.

$ uv run pytest services/strategy-worker/tests/test_derive_variant.py -q -p no:randomly
2 failed, 14 passed in 68.80s (0:01:08)
# os dois failed sao da T3.54b (_refuse_unbudgeted_context, uncommitted, de outro agente): ver abaixo.

$ uv run pytest services/strategy-worker/tests/test_derive_variant.py -p no:randomly -k gate -v
5 passed, 11 deselected in 48.78s

$ uv run pytest packages/core/tests/integration/test_schema_rls.py -q -p no:randomly \
      -k "forced_on_every_relation or another_organizations_users or another_orgs_id_fails"
3 passed, 14 deselected in 36.84s

$ uv run ruff format --check <arquivos>; uv run ruff check <arquivos>
1 file already formatted / All checks passed!

$ uv run pyright infra/scripts/derive_variant.py packages/core/tests/integration/test_migrations.py \
      packages/core/tests/integration/test_schema_privileges.py \
      services/strategy-worker/tests/test_derive_variant.py
0 errors, 0 warnings, 0 informations

$ uv run python infra/scripts/check_file_size.py
scanned 584 files; 0 over budget, 0 grandfathered
```

`alembic upgrade head` em banco limpo, `alembic check` e `downgrade -1 && upgrade head` da `0017` estão **dentro** da corrida de migrações acima: a fixture `upgraded` é `command.upgrade(..., "head")` num banco recém-criado, e `test_0017_refuses_to_downgrade_while_a_version_is_gated` / `test_0017_reverses_on_a_database_where_nothing_is_gated` fazem o `downgrade -1`, o `upgrade head` e o `command.check(config)` — as duas passaram.

**Disciplina de container:** toda invocação em primeiro plano, uma de cada vez, nunca duas simultâneas. Foram cinco invocações com testcontainers (duas do arquivo de migrações e duas do `test_derive_variant.py`, porque a primeira de cada revelou uma falha que precisou de correção e reprova; uma do de privilégios; uma do de RLS). O teto do brief é sobre concorrência, e a concorrência foi zero.

### Pendências que **não** são desta tarefa (medidas, não consertadas)

1. **`test_0012_and_the_domain_constant_agree_on_the_cohort_grammar` depende da ordem dos testes.** Ele chama `migration_ddl("replication")` sem pedir nenhuma fixture, e quem põe `infra/migrations` no `sys.path` é `alembic_config`. Sozinho, `ModuleNotFoundError: No module named 'ddl'` em 2,75 s (sem container). Numa passada do arquivo inteiro ele passa por acidente de ordem. Conserto honesto: `migration_ddl` (em `packages/core/tests/integration/conftest.py`) garantir o `sys.path` que a própria docstring dela promete. Fora do escopo R2/R4/R5, e é conftest compartilhado com outros agentes.
2. **`TestActivatingTheVariant::test_activation_keeps_the_override_and_the_lineage` e `::test_a_dry_run_activation_writes_nothing` falham** por `Refused: no declared context window for variant_activate_dry_v1 v1: add its aggregate() call sites to hunter_strategy_worker.context_budget.WINDOWS`. Vem de `_refuse_unbudgeted_context`, adicionado **sem commit** a `infra/scripts/activate_strategy_version.py` pela T3.54b (outro agente, ainda na árvore). Nada desta tarefa toca esse caminho; é o dono da T3.54b que precisa declarar as janelas das chaves sintéticas desses testes.
3. **R6 fica como está**, como o brief pediu: `packages/core/hunter_core/db/models/agents.py` em 350 linhas exatas — no teto, não acima dele.
