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
  `--force-paper` **e** sem checagem limpa de `positions` (via `agents.strategy_version_id`) e
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
- `seed.py` caiu de 349 para 349→350 linhas líquidas depois de podar o docstring para caber o
  ponteiro a `seed_cli.py` (o file-size gate mede exatamente 350, no limite).

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
