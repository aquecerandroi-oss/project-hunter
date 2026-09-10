# notes-obsidian-2026-09-10b — plantão de arquivamento diurno (09:00–15:30 BRT)

**Escopo de escrita:** `obsidian/**` e este arquivo. Nenhum código tocado, nenhuma suíte de
código rodada (só o linter da base), `.env*` intocado, nada commitado. `git log`/`git status`/`ls`
só lidos (foreground, `timeout 290`).

## Fontes lidas (todas, verbatim, antes de escrever)

`git -C C:/dev/project-hunter log --since="2026-09-10 09:00" --format="%h %s"` e a variante com
`--date=format-local:"%H:%M"` para ordenar por hora real (13 commits, `5a7bbcc..e81d53e`, 11:52–15:23
BRT) · `.claude/state/notes-T3.76.md` · `.claude/state/notes-T3.74c.md` (inclui §8, T3.74d) ·
`.claude/state/notes-T3.80.md` · `.claude/state/notes-T3.81.md` · `.claude/state/notes-T3.79.md` ·
`.claude/state/notes-T3.78.md` (inclui §7 web e §8 T3.78b) · `.claude/state/notes-T3.77.md` (inclui
T3.77b/T3.77c) · `.claude/state/notes-T3.65b.md` · `.claude/state/notes-T3.75.md` (só para a
proveniência de `recompute_funding.py --apply`, citada como pendência do Everton) ·
`.claude/state/notes-T3.61.md`/`-T3.73.md` (só para a proveniência de `mean_reversion v14` e
`--force-paper`) · `.claude/state/plantao/2026-09-10-0730-lane1.md` e `-0630-lane4.md` (lidos, já
arquivados no dia — **não duplicados**) · `docs/OBSIDIAN.md` ·
`obsidian/11-KNOWLEDGE/_TEMPLATE-NOTE.md` · `obsidian/09-OPERATIONS/Diario/2026-09-10.md` (estado
antes da edição) · `obsidian/05-EXPERIMENTS/EXP-0026-regime-como-estrategia.md` (já escrita pelo
T3.76 — só linkada, não editada) · `obsidian/03-TRADING/Estrategias/mean_reversion.md` e
`momentum.md` (já linkavam `EXP-0026` — confirmado, não duplicado) · `obsidian/11-KNOWLEDGE/Index.md`
· `ls obsidian/11-KNOWLEDGE` (para o próximo número livre: KB-0087).

## Arquivos escritos

- `obsidian/09-OPERATIONS/Diario/2026-09-10.md` (editado) — seção nova "## Tarde (09:00–15:30 BRT)"
  com quatro callouts (veredito/medido/alerta/decisao) e nove subseções numeradas (5–9): o lote
  T3.76/EXP-0026 e as quatro aposentadorias, o deploy `e81d53e` (o que foi ao ar de sete tarefas
  paradas desde 13:45 BRT), a tabela de latência do T3.79, o lucro real/meta diária do T3.78/T3.78b,
  e uma nota sobre o consumo do orquestrador. Tabela "Roster depois das aposentadorias" nova. Tabela
  "O que está no ar" atualizada (imagem `e81d53e`, com ressalva explícita de que os tags vêm da
  instrução do turno, não de `docker inspect` desta sessão). Tabela "Decisões em aberto" atualizada:
  item 1 riscado como feito (`5a7bbcc`), item 2 mantido como único pendente de §8, itens 5 e 6 novos
  (`recompute_funding.py --apply`; a guarda `--force-paper` de `mean_reversion v14`). "Relacionadas"
  ampliada com `EXP-0026`, `KB-0087`, a decisão nova, `momentum` e `mean_reversion_h1`.
- `obsidian/11-KNOWLEDGE/KB-0087-o-atraso-de-decisao-e-as-tres-correcoes.md` (novo) — próximo número
  livre depois de KB-0086 (confirmado por `ls`). Consolida as três causas do atraso decisão-menos-
  barra (despacho serial, replay dentro do worker vivo, flush de 1,0 s fixo) e as três correções
  medidas (T3.74c/d, T3.80, T3.81), todas implantadas no deploy `e81d53e` e ainda não relidas em
  produção — declarado como tal, sem inventar o número "depois". Registrada em `Index.md` (tabela de
  temas + tabela de notas).
- `obsidian/11-KNOWLEDGE/Index.md` (editado) — linha de KB-0087 na tabela de temas ("Diagnóstico do
  nosso próprio resultado") e na tabela de notas; `updated` para 2026-09-10.
- `obsidian/08-CHANGELOG/Changelog.md` (editado) — 13 entradas novas dentro do bloco `## 2026-09-10`
  já existente (depois das 9 da madrugada), uma por commit, ordenadas por hora real (`5a7bbcc` 11:52
  → `e81d53e` 15:23 BRT — a ordem de `git log` por padrão é do commit mais novo para o mais velho;
  reordenei pela hora local para bater com a convenção "mais antigo primeiro dentro do bloco" que o
  resto do arquivo já usa), com um parágrafo introdutório em itálico como o da madrugada.
- `obsidian/06-DECISIONS/2026-09-10-validacao-em-um-dia-e-lucro-real.md` (novo) — as três regras do
  Everton citadas hoje, cada uma com a citação literal e o arquivo de origem: "90 dias é muita coisa,
  precisamos validar dentro de 1 dia" + a regra permanente "as que estão dando ruim pode matar"
  (`brief-T3.76...md`, `notes-T3.76.md` §7) para a regra 1; "quero tudo instantâneo"
  (`notes-T3.79.md` §8) para a regra 2, com a tabela de alvos por trecho; e a citação direta sobre
  lucro em USDT+BRL (`notes-T3.78.md` §8, T3.78b) para a regra 3. `decided_on`/`by: everton`
  conforme `docs/OBSIDIAN.md` §1.

## O que eu NÃO fiz

- Não dupliquei os plantões de mercado (`2026-09-10-0730-lane1.md`, `-0630-lane4.md`) — já estavam no
  dia (KB-0085/0086/0084, hipóteses D-P13..D-P16/H-P16, já presentes no Index e nas notas
  correspondentes antes desta sessão).
- Não editei `EXP-0026-regime-como-estrategia.md`, `mean_reversion.md` nem `momentum.md` — as três já
  linkavam corretamente (escritas pelo próprio T3.76); confirmei por leitura, não reescrevi.
- Não toquei `docs/**` nem código de nenhum serviço.
- Não rodei `docker`/SSH/`psql` — todos os números desta sessão vêm das notas dos agentes, nunca de
  uma leitura própria da VPS.
- Não commitei nada.

## Verificação

```
$ cd C:/dev/project-hunter && timeout 290 uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 246 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0,
Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0,
Reescrita de experimentos (append-only): 0.

RESULTADO: base limpa
```
