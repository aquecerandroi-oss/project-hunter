# Notas T3.20 — catálogo de estratégias no Obsidian (backend-specialist, 2026-09-08)

Base `main` em `6b5cb2b`. Trabalhei só em `infra/scripts/{export_strategies_to_obsidian,obsidian_strategy_pages,obsidian_family_pages,obsidian_strategy_queries,obsidian_marker_writer,obsidian_yaml}.py`, `infra/scripts/tests/test_obsidian_{strategy_pages,marker_writer}.py` e `obsidian/03-TRADING/Estrategias/**`. Não toquei `infra/scripts/activate_strategy_version.py` nem `infra/scripts/replicate_strategy_version.py` — aparecem modificado/novo no `git status` porque é trabalho do T3.19 em voo; ignorei conforme a regra. Não commitei nada.

## O que foi construído

1. **Convenção** — `obsidian/03-TRADING/Estrategias/README.md`: uma página por `strategy_version` (`<key>-<version>[-paper].md`), uma por família (`<key>.md`), seções na ordem do brief, o comando do exportador (local e VPS) e o passo de plantão.
2. **Exporter** — `infra/scripts/export_strategies_to_obsidian.py` (221 linhas), lê `DATABASE_URL` (papel `hunter_app`, só SELECT), monta o roster por família, resolve `derived_from` a partir do `changelog` congelado (`succeeds vN` / `paper line of vN`), calcula `params_hash` com `hunter_core.strategies.canonical.params_hash` (o mesmo que o `catalogue.py` do worker usa — nunca uma coluna nova), lê o veredito mais recente da página `EXP-NNNN` quando existe, e escreve via `obsidian_marker_writer` (só o bloco `<!-- generated:start -->…<!-- generated:end -->`; tudo abaixo sobrevive). `--dry-run` funciona (calcula e imprime, não grava).
3. **Módulos de apoio** (separados pelo orçamento de 350 linhas, pela responsabilidade — não por contagem de linha):
   - `obsidian_strategy_queries.py` (148 l) — 3 consultas só-leitura: `strategy_versions` × `strategies`, `system_events` do `activate_strategy_version.py` (casamento por regex de fronteira de palavra `\mchave versão\M`, para `v1` nunca casar `v10`), contagem de `agent_signals` por coorte.
   - `obsidian_strategy_pages.py` (302 l) — renderiza a página de versão: tabela de parâmetros ("cada diâmetro": nome, valor, tipo, vínculo do `pattern`/`enum`, descrição), Origem, Coortes e sinais, Avaliações (só links, nunca números), Replicação, Ligações.
   - `obsidian_family_pages.py` (67 l) — a página de família, e `extract_latest_result` (lê o último `**Result:** **palavra**` da página `EXP-NNNN`).
   - `obsidian_marker_writer.py` (90 l) — escreve só entre os marcadores; cria página que falta, nunca apaga; recusa (`MarkerError`) se uma página existente perdeu os marcadores em vez de adivinhar.
   - `obsidian_yaml.py` (28 l) — dois helpers de frontmatter YAML sem depender do PyYAML (compartilhados pelos dois renderizadores, pyright reclamava de uso "privado" cross-module quando eram `_scalar`/`_list_scalar` dentro de `obsidian_strategy_pages`).
4. **Tabela manual de EXP** (`EXP_LINKS_BY_STRATEGY_PURPOSE` em `obsidian_strategy_pages.py`): nenhuma página do vault nomeia a estratégia sem ambiguidade (a EXP do `volume_anomaly` está com tag `volume`), então o link é uma tabela `(key, purpose) -> (EXP-NNNN, ...)` mantida à mão — documentado no README para quem abrir a próxima EXP.
5. **Nomeação de irmãs de replicação, contra o contrato real** — `docs/plans/REPLICATION.md` (T3.19) apareceu na árvore no meio desta tarefa (agente em paralelo); o brief pedia para lê-lo "se já existir, para a nomeação das irmãs" — lido, **não editado**. O rótulo real do braço, escrito por `replicate_strategy_version.py`, é `replication:<parent_version_id>:<k> | irmã <k> de <parent_version> (T3.19, docs/plans/REPLICATION.md) | ...` (`hunter_strategy_worker/replication_stats.py:arm_label` + `replication.py:_changelog`, lidos, não editados). Acrescentei `parse_replication_sibling()` (extrai `(parent_version, k)` desse changelog exato) e `sibling_slug_for()` (`momentum-v2-irma-03` — bate com o exemplo literal do brief), estendi `parse_parent_version()` para reconhecer também esse terceiro formato, e liguei os dois na orquestração: uma irmã ganha sua própria página nomeada pelo pai + braço (não por sua própria `version`), e a página do pai lista as irmãs conhecidas e um texto curto de status em vez de recalcular os quatro blocos do protocolo (esse cálculo é do placar do Lab, T3.18/T3.19 — a página só aponta, nunca duplica número, mesma regra da seção Avaliações). Nenhuma irmã existe ainda nos dados reais da VPS; confirmei que a mudança é no-op sobre as 19 páginas já geradas (rodei o gerador de novo: `touched 0 of 19 pages`) e cobri as três funções novas com teste unitário usando o changelog real colado do arquivo.

## Bug real pego pelo próprio TDD

`_type_text` produz `"string | number"` para os parâmetros com dois tipos possíveis (a maioria — `DECIMAL_PARAM`/`INTEGER_PARAM` aceitam string e number/integer). Colar isso direto numa célula de tabela Markdown quebra a tabela: o `|` interno vira um separador de coluna a mais. Rodei o exportador de verdade contra os dados reais da VPS antes de escrever o teste de regressão — a página `momentum-v3-paper.md` saiu com colunas deslocadas na primeira geração. Corrigi com um `_cell()` que escapa `|` → `\|` em toda célula (Tipo, Vínculo, Descrição, Coorte) e acrescentei `test_version_body_renders_the_14_parameter_table_with_every_row` verificando a contagem de `|` não-escapados por linha (6, nunca mais). Regenerei as 5 páginas afetadas (as duas do `momentum` com parâmetro decimal/inteiro e as duas do `volume_anomaly`) e uma terceira rodada confirmou 0 diffs (idempotência).

## Rodada real (VPS, só leitura)

`ssh hunter-vps` + `docker exec hunter-postgres-1 psql` funcionaram sem bloqueio para todo `SELECT` (estratégias, parâmetros, `system_events`, contagem de `agent_signals`). Rodar o exportador **dentro** do container da API exigiria copiar os arquivos novos para lá primeiro (`docker cp` escrevendo no container) — isso o classificador de comandos bloqueou, exatamente como a regra operacional previu. Segui o plano B que a própria regra descreve: colei os `SELECT`s (texto abaixo) e alimentei os mesmos dados, literalmente, nas mesmas funções de produção (`build_parameters`, `build_version_frontmatter`, `build_version_body`, `build_family_*`, `plan_write`/`apply_write`) através de um script descartável no scratchpad (apagado ao final) — nenhum código de renderização ou escrita diferente do que o exportador real usa. As 19 páginas + a `README.md` em `obsidian/03-TRADING/Estrategias/` são o resultado dessa rodada.

Estado real da VPS em 2026-09-08 (11 `strategy_versions`): `momentum` v1 (deprecated, research_only, 963 sinais coorte `prospective`), v2 (active, research_only, 10 sinais), v3 (draft, **paper**, 0 sinais — a linha da decisão D10, ainda não ativada); `volume_anomaly` v1 (deprecated, research_only, 2152 sinais), v2 (active, research_only, 18 sinais); e seis rascunhos (`breakout`, `derivatives`, `ensemble`, `mean_reversion`, `narrative`, `order_flow`) — todos `draft`, `parameters_schema`/`default_parameters` vazios (`{}`), nunca ativados.

## Pendência de uma linha

O brief pede um gancho de plantão no `infra/hermes/skills/project-hunter/sexta-feira-plantao/SKILL.md` chamando o exportador — esse caminho pertence ao T3.15c agora, então **não editei**. O passo está escrito no `README.md` da pasta (seção "A cada plantão"); falta só a linha no `SKILL.md` quando aquele arquivo estiver livre.

## Testes (saída real)

```
uv run pytest infra/scripts/tests/test_obsidian_strategy_pages.py infra/scripts/tests/test_obsidian_marker_writer.py -q
....................                                                     [100%]
20 passed in 2.01s

uv run ruff check infra/scripts/export_strategies_to_obsidian.py infra/scripts/obsidian_strategy_pages.py infra/scripts/obsidian_family_pages.py infra/scripts/obsidian_strategy_queries.py infra/scripts/obsidian_marker_writer.py infra/scripts/obsidian_yaml.py infra/scripts/tests/test_obsidian_strategy_pages.py infra/scripts/tests/test_obsidian_marker_writer.py
All checks passed!

uv run ruff format --check <mesmos arquivos>
8 files already formatted

uv run pyright <mesmos arquivos>
0 errors, 0 warnings, 0 informations

uv run python infra/scripts/check_file_size.py
scanned 492 files; 0 over budget, 0 grandfathered
```

## `git status --short obsidian/`

```
?? obsidian/03-TRADING/Estrategias/
```
(diretório novo com 20 arquivos: `README.md` + 19 páginas geradas — 5 famílias reais + 6 rascunhos + 8 versões reais).

## Concerns

- **Sem prova de integração real do exportador contra um Postgres vivo** (nenhum teste de testcontainers nesta tarefa, por regra operacional). As três consultas em `obsidian_strategy_queries.py` foram validadas manualmente contra a VPS (os mesmos `SELECT`s que produziram os dados reais colados acima), mas não há teste automatizado que rode o módulo `fetch_*` fim a fim. Quem revisar deveria, quando puder usar o Docker local (a instrução foi evitá-lo aqui — quatro agentes já o usam), rodar `uv run python infra/scripts/export_strategies_to_obsidian.py --dry-run` contra o Postgres local depois de aplicar a migração `0010` lá (o banco local **não tem** a coluna `purpose` hoje — outro agente está mexendo nessa migração).
- **Replicação ainda mostra "não iniciada" para toda versão real de hoje**, porque nenhuma irmã existe no banco — não por falta de suporte: o parser do rótulo real (`replication:<uuid>:<k> | irmã <k> de vN`) e a nomeação `<key>-<parent>-irma-<k>` já estão implementados e testados (item 5 acima). O que **não** implementei é o cálculo dos quatro blocos do protocolo (out-of-sample, irmãs, metades de mercado, bootstrap) — isso exige as consultas pesadas sobre `signal_outcomes` que `docs/plans/REPLICATION.md` §6 atribui explicitamente ao placar do Lab (T3.18/T3.19); a página do catálogo só aponta para lá, do jeito que já faz com as avaliações do Shadow Lab.
- **Tabela de EXP é manual** (`EXP_LINKS_BY_STRATEGY_PURPOSE`). Funciona hoje (3 entradas) mas não escala sozinha — documentei a regra no README; se o ritmo de novas EXPs aumentar, vale um front-matter `strategy:` na própria página EXP em vez de tags ambíguas, e trocar a tabela por uma consulta.
- **`derived_from` só reconhece as duas frases exatas do `activate_strategy_version.py`** (`succeeds vN`, `paper line of vN`). Um changelog escrito à mão por um humano, ou um terceiro modo de derivação que a T3.19 venha a introduzir, não vira link automaticamente — fica `derived_from: ""` e a página nasce sem a ligação "Versão anterior" até alguém adicionar a frase esperada ou estender o regex.
- Não editei `obsidian/03-TRADING/Strategies.md` (a página antiga de visão geral, ainda marcada "planejado") nem `obsidian/00-HOME.md` para linkar o catálogo novo — fora do escopo literal do brief; deixo registrado para quem fizer a próxima passada de manutenção do grafo.
