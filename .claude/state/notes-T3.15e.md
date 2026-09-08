# Notas T3.15e — conteúdo próprio na ativação de linha derivada, uma coorte só na ponte, `purpose` visível

Executado por backend-specialist em 2026-09-08. Base `main` em `e4b531a` (T3.15c já
commitada: bridge lê `v.purpose`/`envelope_purpose`, `0011` existe). Itens 1, 2, 3 e 4
completos. Nada commitado.

## Item 1 — `activate` de uma linha `paper` preserva o conteúdo copiado

`infra/scripts/activate_strategy_version.py::activate()`: quando a linha já carrega
conteúdo próprio (`purpose != research_only` **ou** `changelog` começa com
`"paper line of"` — a segunda condição é defesa em profundidade caso `purpose` um dia
carregue outro rótulo derivado), a ativação chama a nova
`hunter_strategy_worker.activate_derived.activate_derived()` em vez do caminho que lê
`strategy.parameters_schema`/`default_parameters` do build atual. Essa função:
confere que o `code_ref` recalculado bate com o da linha (recusa com a frase exata do
brief, "deploy the matching build or derive again", caso contrário), valida os
parâmetros da própria linha contra o próprio schema, e — só então — escreve **apenas**
`status`, `activated_at`, `changelog` (nunca `code_ref`/`parameters_schema`/
`default_parameters`/`params_format`).

`_activate_derived` nasceu inline no script e foi extraída para
`services/strategy-worker/hunter_strategy_worker/activate_derived.py` (novo arquivo,
80 linhas) porque a versão inline levou o script a 424 linhas — acima do teto de 350
mesmo depois de cortar comentários/docstring no módulo (`infra/scripts/
activate_strategy_version.py` fechou em exatamente 350).

`services/strategy-worker/hunter_strategy_worker/activation_db.py::load_row` ganhou
`v.changelog` no `SELECT` (precisava dele para o segundo ramo da condição de "linha
derivada").

**Testes** (`services/strategy-worker/tests/test_activate_paper_line.py`, 2 novos, 8
no arquivo):
- `test_activating_the_derived_line_preserves_its_own_copied_content`: deriva `v2` de
  `v1`, ativa com `dry_run=False`, confirma que `default_parameters`/
  `parameters_schema`/`params_format`/`code_ref` da `v2` continuam byte a byte iguais
  aos da `v1`, `changelog` é o novo texto passado (não o "paper line of..."), e a linha
  `v1` (research) permanece intocada (`purpose`/`status` inalterados).
- `test_a_derived_line_whose_code_drifted_is_refused_not_rewritten`: insere uma linha
  `paper`/`draft` com um `code_ref` congelado que não bate com o build atual (simula um
  deploy que tocou `volume_anomaly_v1.py` depois da derivação) e confirma que
  `activate()` recusa com "deploy the matching build or derive again" — a linha
  continua `draft`/`activated_at IS NULL`, a linha research continua `active`.

## Item 2 — a ponte admite uma coorte só (`prospective`)

`services/execution-worker/hunter_execution_worker/bridge_repo.py`: `ShadowSignal`
ganhou `cohort: str`, extraído de `envelope.get("cohort") or meta.get("cohort") or ""`
(mesmo padrão de fallback de `envelope_purpose`) — não há coluna durável para cohort em
`agent_signals` (confirmado: nenhuma migração cria uma, e a T3.19 não estava no meu
escopo de edição), então o dado vem do JSONB que
`hunter_strategy_worker.record.build_record` grava (`envelope["cohort"]`/
`meta["cohort"]`), e é o mesmo dado que `hunter_core.domain.enums.ShadowCohort` valida
no lado de gravação do strategy-worker.

`services/execution-worker/hunter_execution_worker/bridge_screen.py::screen_signal`:
novo portão logo depois do portão de `purpose` (`unknown_purpose`) — `signal.cohort !=
ShadowCohort.PROSPECTIVE` recusa `cohort_not_live`. Isso pega tanto `replay:<run_id>`
quanto qualquer `replication:<parent_version_id>:<k>` que a T3.19 vier a emitir sob o
mesmo `strategy_version_id`/`purpose` de uma linha paper ativa — a ordem do orquestrador
foi "recuse tudo que não for a coorte viva da versão", que é exatamente `!=
"prospective"`.

`services/execution-worker/hunter_execution_worker/metrics.py`: docstring do counter
`hunter_bridge_candidates_total` atualizada para citar `cohort_not_live`.

`services/execution-worker/tests/shadow_builders.py`: `envelope()` e `emit_signal()`
ganharam `cohort: str` (default `ShadowCohort.PROSPECTIVE`) — sem isso, todo teste
existente (que nunca gravava `cohort` no envelope) teria passado a ser recusado
`cohort_not_live` por ausência do campo (fail-closed no vazio, como `unknown_purpose`
já fazia para `purpose` ausente). `ShadowSignal` é um dataclass sem default para
`cohort` (mesmo padrão de `purpose`/`envelope_purpose`), então os dois testes que
constroem `ShadowSignal` manualmente (`test_bridge_eligibility.py`,
`test_bridge_refusal_dedupe.py`) ganharam `cohort="prospective"`.

**Testes novos** (`services/execution-worker/tests/test_bridge_eligibility.py`, 18 no
arquivo):
- `test_a_replay_cohort_signal_of_a_paper_version_is_refused_cohort_not_live`: versão
  `paper` ativa, sinal com `cohort=f"replay:{uuid4()}"` ⇒ `["cohort_not_live"]`.
- `test_a_prospective_cohort_signal_passes_the_cohort_gate`: mesma versão, `cohort=
  "prospective"` ⇒ `[None]` (candidato elegível).

Não filtrei `cohort` no `_SIGNAL_SELECT` (SQL) — ao contrário da recomendação original
da revisão de "filtrar em SQL e defender em `screen_signal`" — porque isso teria
tornado o teste de `cohort_not_live` invisível ao pipeline completo (`pending_signals`
nunca devolveria o sinal, então `screen_signal` nunca rodaria sobre ele, e o teste não
poderia provar a recusa via `_screen()`, só via unit direto). O portão em
`screen_signal` sozinho já é fail-closed e simétrico ao portão de `purpose` (que também
não é filtrado em SQL, só julgado aqui). Registrado como concern abaixo.

## Item 3 — `purpose` visível na página do Lab

Toquei apenas os caminhos que o brief liberou explicitamente (nem `lab_summary.py` nem
`lab-version-card.tsx` estavam sujos no `git status` no início da task — confirmado
antes de editar):
- `apps/api/hunter_api/repositories/lab_summary.py`: `VersionMeta` ganhou `purpose:
  str`, lido de `sv.purpose` em `activated_versions()`.
- `apps/api/hunter_api/schemas/lab_summary.py`: `VersionSummaryOut` ganhou `purpose:
  str` (é aqui que o schema mora — `contract-S3-lab.md`/S3, não em `lab_versions*`).
- `apps/api/hunter_api/services/lab_summary.py::build_version_summary`: passa
  `purpose=meta.purpose`.
- `apps/web/lib/api/lab-types.ts`: `VersionSummaryOut` (espelho hand-written, mesmo
  padrão de `SignalListItemOut.purpose`) ganhou `purpose: string`.
- `apps/web/components/lab/lab-version-card.tsx`: reaproveitei o chip que já existe em
  `lab-strategy-cell.tsx` (`purposeLabel`: `research_only` → "pesquisa", `paper` →
  "paper", `live` → "live") — mesmo componente que a tabela de sinais já usa, sem criar
  um segundo mapa de rótulos. O chip fica ao lado do nome da versão no cabeçalho do
  card.
- `apps/web/tests/fixtures/lab.ts`: `exampleVersionSummary()` ganhou `purpose: "paper"`
  (precisava para o TS compilar: toda literal `VersionSummaryOut` agora exige o campo).
- `apps/web/tests/lab-version-card.test.tsx`: dois testes novos (`purpose=paper` mostra
  chip "paper"; `purpose=research_only` mostra chip "pesquisa").

`routers/lab.py` só importa o tipo `VersionSummaryOut` para anotação — não o
constrói — então ficou intocado (estava sujo/T3.18 de qualquer forma, fora do meu
escopo).

## Item 4 — folga do ciclo do worker, medida por 10 min na stack local

Stack local já rodando (`docker-execution-worker-1`, saudável há 22h+ no momento da
medição). Config real lida de dentro do container:
`admission_poll_s=1.0`, `mtm_poll_s=60.0`, `enable_paper_autonomy=False` (a ponte não
estava ativa; a medição cobre admission + MTM, que rodam de qualquer forma).

**Método:** sem alterar código, um script (`/tmp/measure_cycles.py`, escrito e apagado
dentro do container via `docker exec` — nunca tocou o repositório) importa as mesmas
`hunter_execution_worker.cycles.Cycles.admission`/`.mark_to_market` que o processo real
usa, conectando ao mesmo Postgres/Redis (mesmas `DATABASE_URL`/`REDIS_URL` do
container), e cronometra cada chamada com `time.perf_counter()`: `admission()` a cada
~1 s (mesma cadência de produção — é idempotente, então rodar em paralelo ao loop real
não duplica decisões, só antecipa em microssegundos o que a próxima maré de 1 s já
faria), `mark_to_market()` a cada ~60 s (mesma cadência de produção, para não injetar
pontos extras na curva além da granularidade normal). Três blocos de 200 s em primeiro
plano (regra operacional: ≤ 5 min por comando) somam 600 s = 10 min exatos.

**Resultado** (n=600 admission, n=12 mtm, 0 erros em 612 amostras):

| ciclo     | orçamento | p50     | p95     | max     | folga no p95 | folga no max |
|-----------|-----------|---------|---------|---------|--------------|--------------|
| admission | 1 s       | 17.0 ms | 56.5 ms | 127.6 ms | ~94,3%      | ~87,2%       |
| mtm       | 60 s      | 138.6 ms | 368.3 ms | 789.3 ms | ~99,4%     | ~98,7%       |

Nenhum ciclo chegou perto do orçamento (D10, condição 6): a maior amostra de admission
usou 12,8% de 1 s; a maior de MTM usou 1,3% de 60 s. **Nenhuma mudança de código foi
necessária** — a instrução do brief era só corrigir se algum ciclo estourasse, e
nenhum chegou perto.

Os únicos eventos logados durante a janela foram `equity_point_stale_marks`/
`mtm_marks_stale` (avisos pré-existentes, não erros, sobre um mercado sem marca fresca
— comportamento esperado com o stream de dados local ocioso), zero exceções.

Os arquivos temporários (`/tmp/measure_cycles.py`, `/tmp/cycle_samples.jsonl`) foram
apagados do container ao final; nada foi deixado para trás.

## Concerns

1. **Item 2, decisão de design**: não adicionei o filtro `AND
   s.supporting_features->>'cohort' = 'prospective'` no `_SIGNAL_SELECT` de
   `bridge_repo.py` que a revisão original sugeriu como "defesa em profundidade e
   economia de ciclo" — só o portão em `screen_signal`. Motivo: com o filtro em SQL, um
   sinal de coorte de replay nunca chegaria a `screen_signal`, e o teste que prova a
   recusa via `_screen()` (o caminho que os outros 17 testes do arquivo usam) deixaria
   de conseguir observar `cohort_not_live` — só um unit test direto contra
   `screen_signal` provaria o ramo, quebrando a simetria com o portão de `purpose`
   (que também não é filtrado em SQL). Se o guardian preferir os dois filtros (SQL +
   screen), é um `AND` a mais no `_SIGNAL_SELECT` e a suíte continua verde do mesmo
   jeito — registrando aqui para a revisão decidir.
2. **Sem coluna durável para `cohort`**: ao contrário de `purpose` (que a T3.15c
   corrigiu para vir da coluna congelada, não do JSONB), `cohort` continua sendo lido
   inteiramente de `agent_signals.supporting_features`/`signal_outcomes.meta` — não
   existe hoje uma coluna equivalente em `agent_signals`, e criar uma seria uma
   migração, fora do escopo permitido desta task (`infra/migrations/**` é caminho
   proibido). O `hunter_worker` pode escrever esse JSONB livremente (mesma tabela do
   B1 original), então o portão `cohort_not_live` tem a mesma fragilidade estrutural
   que `purpose_mismatch` resolveu para o propósito: um `INSERT`/`UPDATE` direto do
   papel do worker poderia, em teoria, gravar `cohort: "prospective"` para um sinal que
   na verdade veio de um `SHADOW_COHORT=replay:...`. Não é uma regressão desta entrega
   (o mesmo já valia para `purpose` antes da T3.15c), e não bloqueia nada hoje porque
   nenhum código de produção grava `cohort` fora de `record.py` — mas fica registrado
   para uma eventual `T3.15f`/coluna dura, se o guardian achar que o risco justifica.
3. **Item 1, `activate_derived.py` é código novo, não só extraído**: a lógica em si
   (checar `code_ref`, validar contra o próprio schema, escrever só três colunas) é
   nova desta entrega — só a *extração para arquivo próprio* foi motivada pelo teto de
   350 linhas. Achei mais simples revisar assumindo isso do que fingir que foi um
   refactor puro.
4. **Item 4 não cobre o cenário com duas coortes ativas simultaneamente**: a D10 pede
   medir a folga "com duas coortes ativas" (research + paper rodando junto no mesmo
   worker), mas hoje só existe a coorte `research_only` em produção local (nenhuma
   linha `paper` foi derivada/ativada ainda — é exatamente o que os itens 1/2 desta
   task preparam). A medição registrada aqui é do **execution-worker** (admission +
   MTM), que é o que o brief pediu; a condição da D10 sobre o **strategy-worker** rodar
   duas coortes de avaliação por ciclo continua pendente de uma medição própria depois
   que a linha paper existir de fato — não é a mesma métrica, e não escondi a
   diferença.

5. **Contaminação de árvore compartilhada, descoberta ao final**: `apps/web/components/
   lab/lab-version-card.tsx` — o arquivo que eu editei para o item 3 — apareceu **sem
   diff contra `HEAD`** quando fui conferir o diff final, porque outro processo (o
   orquestrador ou outro agente) rodou um `git add`/`commit` amplo enquanto minha
   edição já estava no working tree e a absorveu no commit `2e0dc084` ("feat(web):
   T3.17b — the Lab table..."), sem relação com T3.15e. Confirmado por `git blame`: as
   linhas do chip de `purpose` estão atribuídas a `2e0dc084`, com meu comentário
   original ("T3.15e, review-T3.15-risk.md item 5") intacto. **Efeito colateral
   importante**: esse commit isolado (`2e0dc084` sozinho, sem o resto do meu diff)
   referencia `version.purpose`, mas `apps/web/lib/api/lab-types.ts` — onde adicionei o
   campo `purpose: string` em `VersionSummaryOut` — **continua não commitado** (`git
   diff HEAD` mostra a adição pendente). Ou seja: `HEAD` sozinho tem um erro de tipo
   TypeScript latente (`lab-version-card.tsx` usa um campo que `VersionSummaryOut` não
   declara) até que meu `lab-types.ts` seja commitado também. No working tree atual
   (com meu diff pendente por cima), tudo compila limpo (`tsc --noEmit` já rodou sem
   erro nos meus arquivos, ver TESTS) — o problema só existe se alguém olhar `HEAD`
   isoladamente ou descartar meu diff pendente sem commitar `lab-types.ts` junto. Não
   tentei corrigir isso com cirurgia de git (nenhum `reset`/`commit --amend`,
   proibidos pela regra operacional) — só registro para o orquestrador decidir como
   commitar (`lab-types.ts` + o restante do meu diff, incluindo o que já está em
   `2e0dc084`, precisam entrar juntos ou o `purpose` do card fica quebrado). Nenhum
   outro arquivo meu foi absorvido — conferido um a um contra `HEAD`.

## Comandos e saída real

Ver seção TESTS do relatório final entregue ao orquestrador (mesmos comandos, saída
integral).
