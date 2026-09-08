# Notas T3.15c — fechando as revisões da 0010 (bridge lê a coluna, worker não ativa, DSN do dono, instalador fixado)

Executado por backend-specialist em 2026-09-08. Base `main` em `b8f3d3f`. Itens
1, 2, 3 e 5 do brief completos. Item 4 (compose) **adiado**: `git status`
mostrava `infra/docker/docker-compose.yml` e `infra/vps/docker-compose.prod.yml`
sujos (T3.0f em voo) — escrito como `.claude/state/brief-T3.15d-owner-dsn.md`.

## Item 1 — a ponte decide pela coluna, não pelo envelope

`services/execution-worker/hunter_execution_worker/bridge_repo.py`:
`_SIGNAL_SELECT` agora traz `v.purpose AS version_purpose`; `ShadowSignal.purpose`
é essa coluna e `ShadowSignal.envelope_purpose` guarda o rótulo do envelope
(`supporting_features`/`meta`) só como contraprova.

`services/execution-worker/hunter_execution_worker/bridge_screen.py`:
`screen_signal` compara os dois **antes** de qualquer outra triagem — divergência
é recusada `purpose_mismatch`, logada em `warning` (não `info`). `report_refusal`/
`_refuse` ganharam um parâmetro `level`.

`services/execution-worker/hunter_execution_worker/metrics.py`: docstring do
counter atualizada com `purpose_mismatch`.

Testes (`services/execution-worker/tests/`):
- `shadow_builders.py::create_version` ganhou `purpose: str = PURPOSE_PAPER`
  (grava a coluna real, antes só a `0010` não expunha isso ao helper).
- `test_bridge_eligibility.py`: `_setup` ganhou `version_purpose`; ajustadas
  `test_research_only_is_refused_at_the_door` e
  `test_a_live_signal_is_refused_live_forbidden` para casar coluna e envelope;
  `test_an_unknown_purpose_is_refused_unknown_purpose` virou
  `test_an_unknown_column_purpose_is_refused_unknown_purpose` — unitário direto
  contra `screen_signal`, porque o CHECK da `0010` torna um rótulo inválido na
  coluna irrepresentável em banco; adicionadas as duas de mismatch pedidas pelo
  brief (`paper`×`research_only` e o inverso).
- `test_bridge_refusal_dedupe.py`: `_signal()` ganhou `envelope_purpose="paper"`.

## Item 2 — migração `0011_strategy_activation_owner`

Novos: `infra/migrations/ddl/strategy_activation_owner.py`,
`infra/migrations/versions/0011_strategy_activation_owner.py`. Revoga de
`hunter_worker` em `strategy_versions`: `UPDATE` em `status`, `activated_at`,
`deprecated_at`, `code_ref`, `parameters_schema`, `default_parameters`,
`params_format`; `DELETE` de tabela inteira; `INSERT` por completo (nada insere
como o worker — `seed.py`/`paper_line.py`/o script de ativação rodam na conexão
de dono). Sobra `UPDATE` em `id`, `strategy_id`, `version`, `changelog`,
`created_at` (computado por subtração das duas listas congeladas, nunca
retiado). Sem `ACCESS EXCLUSIVE`, sem guarda de downgrade (reverter não perde
dado, só regranta o que `0001`/`0010` já davam).

`docs/DATABASE.md`: §16.1 (lista congelada agora cita `purpose`), §17.6 (nota
sobre `strategy_versions` não ser mais grant de tabela), §15.6 (extensão do
histórico de `lock_timeout` cobrindo `0006`–`0011`), §22 (fix "22" → "21"
caracteres) + nova §22.6 (o fix do item 1) + nova §23 completa sobre a `0011`.
`infra/migrations/versions/0010_strategy_purpose.py`: fix "20 characters" → "21".

Testes: `packages/core/tests/integration/test_schema_privileges.py` ganhou
`_insert_strategy_version_as_owner` (o worker não insere mais nada nessa
tabela, então o fixture precisa nascer com o papel resetado para o dono da
sessão) e a suíte de `0011` (não ativa, não apaga, ainda lê, só `SELECT` de
tabela, e um teste que prova que as duas listas de
`ddl.strategy_activation_owner` particionam exatamente o grant da `0010`).
`test_migrations.py`: `HEAD_REVISION` → `0011_strategy_activation_owner`,
nova `STRATEGY_PURPOSE_REVISION`; os dois testes de downgrade da `0010`
(`test_0010_refuses_to_downgrade_...` e `test_0010_reverses_on_a_populated...`)
precisaram descer um degrau extra (`command.downgrade(config,
STRATEGY_PURPOSE_REVISION)`) antes do `"-1"`, porque agora há uma revisão acima
da `0010`; nova `test_0011_reverses_and_restores_0010s_grant` (round trip +
`alembic check`).

**Efeito colateral descoberto e corrigido** (fora do escopo do brief, mas
necessário para os testes passarem): revogar `INSERT` por completo quebrou todo
fixture de teste que inseria `strategy_versions` como `hunter_worker` via SQL
cru. Corrigidos:
- `services/strategy-worker/tests/builders.py::activate_version` — o reset de
  papel (`RESET ROLE`/`SET LOCAL ROLE`) que já existia só para a coluna
  `purpose` (desde a `0010`) agora envolve o `INSERT` inteiro.
- `services/strategy-worker/tests/test_activation.py` —
  `test_it_refuses_a_version_this_build_has_no_code_for` ganhou o mesmo
  reset de papel.
- `services/strategy-worker/tests/test_version_roster.py` — três `UPDATE
  strategy_versions SET status = ...` como `hunter_worker` (armar/desarmar o
  cenário "roster cego") ganharam o mesmo reset.

**Não corrigido, fora do escopo permitido** — ver Concerns.

## Item 3 — o script de ativação audita toda falha

`infra/scripts/activate_strategy_version.py`: o `try/except` de `_run` saiu de
dentro do `async with conn.begin():` para fora — uma exceção que sai desse
bloco já dispara o rollback da própria transação sozinha, então o registro do
evento (numa conexão nova) nunca compete com a escrita que falhou. `except
Refused` grava `strategy_version_activation_refused` (nível `warning`) e
retorna 1; `except Exception` grava `strategy_version_activation_error` (nível
`error`) e levanta `SystemExit(2)`. A escrita do evento
(`record_failure`, antes `_record_failure`) foi movida para
`services/strategy-worker/hunter_strategy_worker/activation_db.py` — o módulo
que já hospeda `record_event` e o resto do que os três modos compartilham —
porque a versão original em `activate_strategy_version.py` estourava o teto de
350 linhas (362).

Testes: `services/strategy-worker/tests/test_activation.py` ganhou
`TestEveryRunIsAuditedEvenOnAnUnexpectedFailure` — uma exceção forçada
(`monkeypatch.setattr(script, "activate", ...)`) prova o `system_events` de
erro e o `SystemExit(2)`; um segundo teste prova que a recusa continua
auditada corretamente depois da mudança de estrutura.

## Item 5 — cadeia de suprimento do instalador

`infra/hermes/install.sh`: `obsidian-mcp@2` (faixa flutuante) →
`obsidian-mcp@2.0.1` (`OBSIDIAN_MCP_VERSION`, versão publicada hoje via `npm
view obsidian-mcp version`), com instruções de como auditar e subir a versão no
próprio comentário. Cabeçalho corrigido: não é mais "never reads .env" sem
qualificação — diz que o script não lê o `.env` do **repositório**, mas
`profile create --clone` clona o `.env` do perfil ativo do Hermes.

`docs/HERMES.md`: nova seção explicando o pin, como bumpar, e que um perfil
`sexta-feira` já instalado precisa ter a seção `mcp_servers.obsidian` do seu
`config.yaml` apagada manualmente uma vez (o instalador só escreve quando a
seção está ausente) para pegar a versão fixada.

## Item 4 — adiado

`git status` mostrava os dois compose files sujos (T3.0f); escrito como
`.claude/state/brief-T3.15d-owner-dsn.md`, pronto para rodar depois que T3.0f
aterrissar. Confirmação adicional: `docker compose -f
infra/vps/docker-compose.prod.yml config` nem chega a parsear no estado atual
(edição em andamento) — reforça que mexer agora seria pisar em cima de outro
agente, não só uma questão de `git status` sujo.

## Saída real dos comandos

Ver seção TESTS do relatório final entregue ao orquestrador.

## Concerns

1. **`services/market-worker/tests/test_universe_tracking_hold.py::_open_tracking`
   quebra com a `0011`** — insere `strategy_versions (id, strategy_id, version,
   status)` como `hunter_worker` dentro de `held_market` (fixture usada por
   `TestUniverseTrackingHold` e outras). Está em `services/market-worker/**`,
   fora do meu escopo permitido nesta task (T3.0f está em voo lá). Precisa do
   mesmo tratamento que apliquei em `services/strategy-worker/tests/builders.py`
   e `test_version_roster.py`: `RESET ROLE` antes do `INSERT`, `SET LOCAL ROLE
   hunter_worker` depois. Não toquei no arquivo. **Quem pegar T3.15d ou
   qualquer brief seguinte em market-worker precisa aplicar esse fix antes que
   a suíte rode contra um banco em `0011` ou além.**
2. **Ambiente compartilhado sem isolamento por agente**: durante esta task,
   arquivos que eu tinha acabado de editar (`bridge_repo.py`,
   `docs/DATABASE.md`, `0010_strategy_purpose.py`) apareceram momentaneamente
   como se tivessem revertido para o estado anterior às minhas edições — sem
   nenhuma ação minha. Investigação mostrou que as edições estavam de fato
   intactas (checado via `git diff --stat` e `grep` direto no arquivo); o
   sintoma real foi um artefato de uma consulta minha malformada (grep com
   alternância `\|` que não bateu como esperado). Mas achei
   `.claude/state/tmp/dbmd-after-stash.patch` no `git status` — nome que sugere
   que outro agente rodou `git stash` no repositório compartilhado em algum
   momento desta sessão. Como não há worktree por agente, um `git stash`/`reset`
   de qualquer um dos quatro agentes concorrentes pode, em teoria, arrastar
   junto o trabalho não commitado de outro. Nada se perdeu desta vez, mas vale
   registrar o risco.
3. **`test_migrations.py` teve 4 falhas transitórias na primeira rodada**
   (`ConnectionResetError [WinError 64]`, um hiccup de rede Windows/Docker sob
   carga — quatro agentes compartilhando o mesmo Docker Desktop). Re-executei o
   arquivo inteiro uma segunda vez: 50/50 passou. Não é um bug de lógica; é
   contenção de recursos. Se o `T3.15c` review quiser reproduzir, rode em um
   momento de menos concorrência de Docker.
4. **Decisão de design em `0011`**: o brief pediu revogar `UPDATE` em sete
   colunas nomeadas e `DELETE`/`INSERT` por completo, deixando `id`,
   `strategy_id`, `version`, `changelog`, `created_at` ainda com `UPDATE` para
   `hunter_worker`. Nenhum código de produção escreve essas cinco colunas
   também (confirmado no `grep`), então um estreitamento mais agressivo (SELECT
   puro) seria possível — não fiz isso por não estar no escopo literal do
   brief; registrado aqui caso uma `0012` futura queira fechar esse resto.
