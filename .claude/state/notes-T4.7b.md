# Notas T4.7b — migrações reais no teste da mesa (12/09/2026)

- `test_meme_desk_repository.py` (T4.7) apagado; DDL literal (0022 congelado) removida.
- Esquema agora vem de Alembic até `head` (`0022`→`0031`) via nova fixture aditiva
  `migrate_fresh_database` em `conftest.py` (fábrica: cria um banco próprio dentro do
  `postgres_container` e roda `upgrade head`). `MIGRATIONS_DIR` do conftest passou a
  respeitar `HUNTER_MIGRATIONS_DIR` (mesmo padrão de `packages/core`), mas o run real
  usou a árvore ao vivo: uma cópia externa em scratchpad não é visível ao processo
  nativo `uv run` (path existe para o Bash tool, não para o Python — reportado, não
  contornado; ver relatório final).
- Semente movida para `apps/api/tests/integration/meme_desk_seed.py`; nomes de
  `meme_rule_sets` trocados para `meme_desk_it_research`/`meme_desk_it_operator`
  (os nomes `meme_paper_v0`/`operator` já são semeados pela própria `0022`+`0029` e
  colidiriam em `(name, version)`). `mark_source='curve'` adicionado às apostas
  semeadas — `0029` exige `(mark_sol IS NULL) = (mark_source IS NULL)`; confirmado
  via quebra proposital (ver relatório).
- `TestManual` agora afere contra o `operator` real migrado (`operator/2` desde
  `0029`, pego por `repo.get_operator_rule_set()`), com `size_sol` sob o teto real
  de 0,05 SOL — antes usava um `operator/1` sintético e local.
- Suite dividida em `test_meme_desk_repository_{a,b}.py` (≤350 linhas cada); `xfail`
  de `test_http_approve_against_the_real_migration` removido (0022–0031 já na
  árvore; passa de verdade em `_b`).
- Nada tocado fora do escopo liberado; `infra/migrations/**` e `apps/api/hunter_api/**`
  só lidos.
