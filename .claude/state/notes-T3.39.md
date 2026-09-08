# T3.39 — `--deprecate` auditado e `seed.py --dry-run`/`--only` (notas do backend-specialist)

## O que existia e o que faltava
- `activate_strategy_version.py` já tinha `activate`/`--supersede`/`--paper-line`. `--supersede`
  só serve para uma sucessora de **código**: quando o `code_ref` já bate (uma variante por
  parâmetro, `derive_variant.py`), ele recusa de propósito ("already frozen against this code").
  Não havia via auditada para aposentar `breakout v1` (0 decisões, K1) nem `breakout v2`
  (recomendação: descartar) — versões cuja sucessora é um parâmetro, ou que não têm sucessora.
- `seed.py` sempre rodou tudo numa transação, sem `--dry-run` nem `--only`, e uma reexecução
  podia reescrever `risk_profiles` (as três presets genéricas) sem aviso — só `paper_v1` já era
  protegido (`_refuse_diverging_preset`).

## `--deprecate` (T3.39)
- `services/strategy-worker/hunter_strategy_worker/deprecate.py` (novo): `UPDATE status =
  'deprecated'` — o único campo que a trigger de congelamento (`0002_shadow_lab`, DATABASE.md
  §16.1) deixa mutável. Recusa `purpose = 'live'` sempre; recusa `purpose = 'paper'` sem
  `--force-paper` **e** sem checagem limpa de `positions` (~~via `agents.strategy_version_id`~~ —
  **afirmação obsoleta, corrigida na T3.39b/ALTA-1**: `positions.agent_id` nunca é escrito pelo
  execution-worker; o caminho real é `positions.metadata->>'proposal_id' -> orders.proposal_id ->
  trade_proposals.agent_id -> agents.strategy_version_id`) e
  `shadow_episodes.open_outcome_signal_id` — a diretriz do risk-engine-guardian para esta tarefa
  ("uma versão sendo aposentada nunca pode ser a linha paper com posições abertas"). `--successor
  v<n>` é só uma nota auditada (o script nunca ativa uma sucessora); recusa um sucessor que não
  existe. Todo run grava `system_events` (`strategy_version_deprecated`), com o `code_ref` e o
  `params_hash` congelados.
- O roster do worker (`load_version_roster`) já filtra por `status = StrategyVersionStatus.ACTIVE`
  — confirmado lendo `catalogue.py` e o teste existente `test_ready_turns_red_when_no_active_
  version_is_runnable` (que já fazia exatamente esse `UPDATE status='deprecated'` à mão). Adicionei
  um teste dedicado (`test_the_roster_drops_the_deprecated_version_at_the_next_reload`) que passa
  pelo `--deprecate` real em vez de SQL cru.
- `activate_strategy_version.py` já estava em 348/350 linhas antes desta tarefa; para caber o
  `--deprecate` sem estourar o orçamento, extraí também `supersede()`/`_next_version()` para
  `services/strategy-worker/hunter_strategy_worker/supersede.py` (mesmo padrão de
  `paper_line.py`/`activate_derived.py`). `activate_strategy_version.py` ficou com 293 linhas.

## `seed.py --dry-run`/`--only`/`--yes` (T3.39)
- **Decisão de design**: `seed()` (a função que ~30 chamadas em
  `packages/core/tests/integration/test_schema_seed_and_partitions.py` já usam, retornando
  `dict[str, int]`) ficou **inalterada**. Toda a lógica nova vive em `seed_cli.py` (novo,
  `seed_with_report()` + `main()`) e `seed_dry_run.py` (novo, o motor de diff). Isso evitou
  quebrar o contrato de retorno que dezenas de testes existentes já assumem.
- `seed_dry_run.py`: tira uma foto (`snapshot`) das quatro tabelas diferenciáveis
  (`strategies`, `risk_profiles`, `feature_definitions`, `opportunity_weights`) por chave
  natural, **dentro da mesma transação**, antes e depois do escritor real rodar — o diff nunca
  pode discordar do que foi de fato escrito, porque nada mais lê ou escreve aquelas linhas
  enquanto isso. `risk_profiles_would_change()` faz a mesma leitura para decidir o portão do
  `--yes`.
- `seed_cli.py`: `--dry-run` roda tudo que a invocação rodaria e desfaz a transação;
  `--only <tabela>` restringe a transação a essa tabela (`strategies` inclui `strategy_versions`
  junto, como o `seed()` padrão já faz; `risk_profiles` inclui `paper_v1` junto); sem `--only`,
  uma mudança de limite em `risk_profiles` (qualquer uma das três presets ou `paper_v1`) recusa
  sem `--yes` — a diretriz do Everton (`.claude/state/directive-risk-engine-2026-09-06.md`).
- `seed.py` ficou em **349 linhas** depois de podar o docstring para caber o ponteiro a
  `seed_cli.py` — **correção T3.39b**: a nota original ("caiu de 349 para 349→350") estava
  incoerente consigo mesma e com o arquivo real; `wc -l infra/scripts/seed.py` mede 349, um abaixo
  do orçamento de 350 do file-size gate, não no limite exato como dito antes.

## Achado não relacionado (não corrigido, fora do escopo)
`packages/core/tests/integration/test_schema_seed_and_partitions.py::
test_seeding_twice_leaves_the_same_rows` falha hoje em `main` (`assert counts_after_first
["strategies"] == 8`, recebe 9) — pré-existente, do commit `3ed17bb` (T3.33c, que acrescentou
`session_orb` ao catálogo) sem atualizar essa asserção. Confirmado com `git diff HEAD --
packages/core/tests/... seed_reference.py`: nenhum dos dois arquivos foi tocado nesta tarefa.
Não corrigi por estar fora do escopo do brief (`packages/core/tests/**` não está na lista de
arquivos autorizados) — registrando para o orquestrador decidir se abre uma tarefa.

## Flakiness observada (ambiente, não código)
`infra/scripts/tests/test_seed_dry_run.py` passou limpo (9/9) na maioria das corridas, mas em
duas rodadas um teste aleatório diferente (nunca o mesmo) falhou com
`ConnectionResetError: [WinError 64]` durante o handshake SSL do asyncpg contra o Postgres do
testcontainer — sintoma de rede Docker Desktop/Windows, não da lógica testada (cada teste abre
sua própria engine; a falha não se repete no mesmo teste em corridas diferentes). Reexecutar
resolve.

## Documentação
`docs/ACTIVATION.md`: adicionei `## 7b. Aposentar uma versão substituída por parâmetro
(--deprecate, T3.39)` logo após a seção existente `## 7. Derivar uma variante...` (não renumerei
o `## 7.` original nem o `## §8` checklist já existentes, para não quebrar referências cruzadas
em outros documentos/Obsidian) e `## 9. Re-seed seguro (seed.py --dry-run / --only, T3.39)` perto
do fim, com os comandos exatos da VPS e a pendência do operador de hoje (`seed.py --only
strategies` para trazer `session_orb` e corrigir descrições; `--deprecate breakout v1` e
`--deprecate breakout v2`, sucessor nenhum, motivo K1). Também corrigi a frase desatualizada em
"Como desligar" que dizia `--deprecate` "não existe".

## T3.39b — fecha a revisão do risk-engine-guardian sobre 4929b99

Brief `.claude/state/brief-T3.39b-deprecate-review-fixes.md`. Base `main` em `e10fca4`.

**ALTA-1 (trava de posições pelo caminho real).** `positions.agent_id` nunca é escrito em
produção — confirmado lendo `hunter_execution_worker.positions.open_position`: o `INSERT` não
tem essa coluna. A trava de `_open_paper_exposure` (agora `open_paper_exposure`, movida para
`activation_db.py` para servir os dois escritores) passou a seguir o caminho real:
`positions.metadata->>'proposal_id' -> orders.proposal_id -> trade_proposals.agent_id ->
agents.strategy_version_id`, o mesmo trio de tabelas que `ddl/paper.py`'s própria checagem de
consistência já junta (`orders o JOIN trade_proposals p ON p.id = o.proposal_id`). A consulta
conta `count(DISTINCT p.id)` (uma proposta pode ter mais de um `orders` linkado) com
`p.status <> 'closed' AND NOT p.is_residual` — a própria definição do projeto de "posição viva"
(BAIXA-6). `services/strategy-worker/tests/builders.py` ganhou `seed_paper_exposure` (org,
workspace, portfolio, agent, `trade_proposals`, `orders`, `positions` — sem `agent_id` na
posição, de propósito) substituindo o fixture anterior que escrevia `positions.agent_id`
diretamente e por isso nunca teria pego o bug em produção.

**BAIXA-7 (metade shadow_episodes).** `builders.seed_shadow_exposure` cria um `agent_signals` +
`signal_outcomes` + `shadow_episodes` com `open_outcome_signal_id` preenchido; novo teste em
`test_deprecate.py` prova a recusa por esse lado, independente de qualquer posição.

**ALTA-2 (`--supersede` com a mesma trava; `purpose` copiado).** `supersede()` ganhou
`force_paper: bool = False` e os dois mesmos refuses estruturais de `deprecate()`
(`purpose='live'` sempre recusa; `purpose='paper'` exige `--force-paper` e
`open_paper_exposure` limpo) — um escritor que move uma versão congelada para fora de `active`
não podia ser mais frouxo que o outro. O `INSERT` da sucessora passou a nomear `purpose`
explicitamente (`row.purpose`), porque a coluna tem `DEFAULT 'research_only'`
(`0010_strategy_purpose`) e a ausência da coluna no `INSERT` fazia toda sucessora de uma linha
`paper` virar `research_only` em silêncio. `activate_strategy_version.py` passou a chamar
`supersede(..., force_paper=args.force_paper)` em vez do despacho genérico
`action(conn, ...)` que não sabia passar essa flag.

**MÉDIA-3 (flags só com os modos certos, ajustado para o ALTA-2).** `main()` agora valida,
depois de `parse_args()`: `--successor` sem `--deprecate` é `parser.error`; `--force-paper` sem
`--deprecate` **nem** `--supersede` é `parser.error` — a redação original do achado ("só com
`--deprecate`") ficou estreita demais depois do ALTA-2 pedir `--force-paper` também em
`--supersede`; a síntese fica registrada aqui porque o brief não previu os dois ao mesmo tempo.
Testado em `services/strategy-worker/tests/test_activate_strategy_version_cli.py` (novo,
`pytest.mark.unit`, sem banco: `_run` é substituído por um stub para provar que o parser aceitou
sem tocar `DATABASE_URL_MIGRATIONS`).

**MÉDIA-4 (diff antes do commit; trava de TTY).** `seed_cli.seed_with_report` ganhou `emit`
(callback de impressão, `print` por padrão) chamado **antes** da decisão de commit/rollback, e
`attended: bool = True` — `main()` mede `sys.stdin.isatty()` e passa o valor real; todo outro
chamador (testes, código) continua recebendo o comportamento de sempre por causa do default.
Quando o diff não é vazio, não é `--dry-run`, não tem `--yes` **e** `attended=False`, o run
recusa e desfaz a transação — nunca escreve silenciosamente num pipe (`docker exec -i ... python
-`, o padrão que os runbooks da VPS usam). Testado em quatro casos novos (`TestUnattendedGate`),
incluindo um `emit` que explode na primeira linha para provar que nada comita antes da
impressão.

**MÉDIA-5 (paridade de tabelas).** Novo teste `TestRunEverythingMatchesSeededTables` compara
`set(await seed_cli._run_everything(conn))` com uma cópia local de `SEEDED_TABLES` (o mesmo
conjunto que `packages/core/tests/integration/test_schema_seed_and_partitions.py` já usa).

**BAIXA-9 (diff de `strategy_versions` sob `--only strategies`).** `seed_dry_run.snapshot()`
agora inclui `strategy_versions` (chave `"<key> v1"`, join com `strategies`) sempre que
`"strategies"` está entre as tabelas pedidas — full run ou `--only strategies`.

**BAIXA-10 (teste independente de ordem).** `TestDryRunWritesNothing` não assume mais que roda
antes de qualquer outro teste do módulo (banco compartilhado por `seed_db_url`,
`scope="module"`): cada teste agora apaga uma `strategies.key` conhecida antes de rodar (garante
uma linha `NEW` determinística) e compara contagens ao valor de **antes**, nunca a zero.

**BAIXA-11 (`params_format` na auditoria).** A mensagem de `strategy_version_deprecated` em
`system_events` agora inclui `params_format={row.params_format}`, ao lado de `code_ref` e
`params_hash`. Testado (`test_it_records_params_format_in_the_audit_event`).

**BAIXA-12 (duas afirmações obsoletas + nota de TTL).** Corrigidas nesta mesma nota, acima: (1) a
descrição da trava de posições dizia "via `agents.strategy_version_id`" sem citar o caminho
real; (2) "`seed.py` caiu de 349 para 349→350 linhas" era incoerente consigo mesma (o arquivo
mede 349, não 350). `docs/ACTIVATION.md` §7b ganhou a nota do TTL de 60 s do roster
(`ShadowConfig.version_refresh_s`/`SHADOW_VERSION_REFRESH_S`): uma versão recém-aposentada ou
superada continua avaliando por até um minuto.

**Achado não relacionado, fora do escopo (não corrigido).** `services/strategy-worker/tests/
test_activation.py::TestEveryRunIsAuditedEvenOnAnUnexpectedFailure` (dois testes:
`test_a_forced_exception_is_audited_and_exits_2`,
`test_a_refusal_still_rolls_back_before_the_audit_write`) já falhava em `main` na base
`e10fca4` (confirmado com `git show e10fca4:services/strategy-worker/tests/test_activation.py`
— conteúdo idêntico ao atual): os dois constroem `argparse.Namespace(strategy=..., version=...,
changelog=..., dry_run=..., paper_line=..., supersede=...)` sem os campos `deprecate`,
`successor`, `force_paper` que a T3.39 original já tinha acrescentado a `_run()`; `args.deprecate`
lança `AttributeError`, capturado pelo `except Exception` genérico, que audita e sai com
`SystemExit(2)` em vez do comportamento que cada teste espera. Pré-existente à T3.39b, e
`test_activation.py` não está na lista de arquivos autorizados deste brief — registrando para o
orquestrador decidir se abre uma tarefa.

**Ferramentas:** `ruff check .` limpo; `ruff format --check` limpo nos onze arquivos tocados
(um precisou de `ruff format` automático); `pyright services/strategy-worker infra/scripts`
limpo (só o erro pré-existente e não relacionado de `test_replay_stress.py`, arquivo não
tocado); `check_file_size.py` limpo (0 arquivos acima do orçamento; `services/strategy-worker/
tests/**` e `infra/scripts/tests/**` ficam fora do escopo do gate por estarem em `tests/`).

**Testes (saída real, um arquivo por invocação de pytest):**
- `services/strategy-worker/tests/test_deprecate.py`: 13 passed
- `services/strategy-worker/tests/test_supersede.py`: 12 passed
- `services/strategy-worker/tests/test_activate_strategy_version_cli.py` (novo): 5 passed
- `infra/scripts/tests/test_seed_dry_run.py`: 15 passed
- `services/strategy-worker/tests/test_activate_paper_line.py` (regressão): 8 passed
- `services/strategy-worker/tests/test_activate_derived_guard.py` (regressão): 7 passed
