# notes-obsidian-2026-09-10 — plantão de arquivamento (00:20–03:10 BRT)

**Escopo de escrita:** `obsidian/**` e este arquivo. Nenhum código tocado, nenhuma suíte rodada,
`.env*` intocado, nada commitado. `git status`/`git log` só lidos (foreground, `timeout 290`).

## Fontes lidas (todas, verbatim, antes de escrever)

`.claude/state/notes-T3.62b.md` · `.claude/state/notes-D-P9.md` · `.claude/state/notes-T3.73.md` ·
`.claude/state/notes-T3.74.md` · `.claude/state/notes-T3.69.md` · `.claude/state/notes-T3.70.md` ·
`.claude/state/notes-T3.71.md` · `.claude/state/plantao/2026-09-10-0045-lane2.md` ·
`.claude/state/notes-T3.68.md` · `.claude/state/notes-T3.72.md` ·
`git -C C:/dev/project-hunter log --since="2026-09-10 00:00" --format="%h %s"` (9 commits,
`6008eb8..40bb39a`) · `docs/OBSIDIAN.md` · `obsidian/11-KNOWLEDGE/_TEMPLATE-NOTE.md` ·
`obsidian/05-EXPERIMENTS/_TEMPLATE-EXP.md` · `docs/ACTIVATION.md` §8a/§8b (para os comandos citados
no diário) — leitura, não edição.

## Arquivos escritos

- `obsidian/09-OPERATIONS/Diario/2026-09-10.md` (novo) — a onda "M3 pronto para uso" (T3.68/T3.69/
  T3.71 no ar ou provados; T3.72/T3.72b prontas, em revisão, **não implantadas**), o estado honesto
  da família `mean_reversion` (90 dias, K3 disparado nas três versões), o que está no ar
  (api/strategy-worker `40bb39a`, web `d450038`), e a tabela de decisões para o Everton (os dois
  comandos de `ACTIVATION.md` §8b, a transação SQL de `agents` do §8a, o residual T3.69b, `late:delay`
  sem correção de causa).
- `obsidian/05-EXPERIMENTS/EXP-0025-mean-reversion-90-dias.md` (novo) — não havia EXP arquivado para
  o replay de 16 mercados/90 dias da T3.62/T3.62b (confirmado por grep; EXP-0022/0023/0024 só existem
  como rascunhos de outros temas em `.claude/state/exp-drafts/`, não sobre esta pergunta). Número
  seguinte livre no vault: `EXP-0025`. Hipótese, portão (não aplicável — reavaliação, não desenho
  novo), protocolo (três braços `v1`/`v2`/`v10`, mesmo `code_ref`) e uma avaliação datada
  (2026-09-10) com todas as tabelas de `notes-T3.62b.md`: cobertura das 36 corridas, resultado pooled
  por versão, as três janelas de 30 dias, Δ(J3−J1J2), 4 originais vs. 12 novos, funil K1–K6, C5,
  estresse. Registrada em `Experiments Index.md` (tabela principal + registro de IDs).
- `obsidian/03-TRADING/Estrategias/mean_reversion.md` (editado) — tabela de versões (`v1`/`v2`/`v10`)
  atualizada para o veredito de 90 dias, link para `EXP-0025` em Ligações, e uma seção "Acréscimo de
  2026-09-10" no corpo de Notas, append (as leituras antigas de 31/17/7 dias não foram apagadas —
  continuam nas páginas de EXP de origem).
- `obsidian/11-KNOWLEDGE/KB-0083-uma-hora-de-34-r-deriva-e-impulso.md` (novo) — próximo número livre
  depois de KB-0082 (confirmado por `ls obsidian/11-KNOWLEDGE`). A hora de −34 R decomposta (9 apostas
  × 4,3 versões, deriva + impulso de amplitude, BTC não caiu) e os dois achados de instrumento (spot
  duplicando aposta única com `funding_schedule_unknown`; denominador escondido de `late:delay`).
  Registrada em `11-KNOWLEDGE/Index.md` (tabela de temas + tabela de notas).
- `obsidian/08-CHANGELOG/Changelog.md` (editado) — bloco `## 2026-09-10` com as 9 entradas do
  `git log`, uma por commit, na ordem cronológica do dia (mais antigo primeiro dentro do bloco, como o
  resto do arquivo), com o resumo verbatim de cada mensagem de commit e link para a nota Obsidian que
  a arquiva quando existe (`EXP-0025`, `KB-0083`, `Open Bugs`).
- `obsidian/09-OPERATIONS/Diario/2026-09-10.md` também linka (sem reescrever) as entradas T3.73/T3.74
  já existentes em `obsidian/07-BUGS/Open Bugs.md` — não editei esse arquivo.

## O que eu NÃO fiz

- Não toquei `obsidian/07-BUGS/Open Bugs.md` — as entradas de T3.73/T3.74 já existiam, escritas pelos
  próprios agentes; só linkadas do diário.
- Não criei página própria para `mean_reversion-v10.md` (o catálogo é gerado por
  `infra/scripts/export_strategies_to_obsidian.py`, T3.20, e o host não alcança o Postgres da VPS
  nesta sessão — mesma limitação já registrada nas notas anteriores da família).
- Não editei código, `docs/**`, nem qualquer arquivo fora de `obsidian/**`.
- Não commitei nada.

## Verificação

```
$ timeout 290 uv run python infra/scripts/obsidian_lint.py
LINT DA BASE OBSIDIAN — 240 NOTA(S) ANALISADA(S)
Resumo — Links mortos: 0, Links ambíguos: 0, Notas órfãs: 0, Frontmatter incompleto: 0,
Valores fora do vocabulário: 0, Procedência da Knowledge Base (KB-*): 0,
Reescrita de experimentos (append-only): 0.
Info: 1 experimento(s) fora do HEAD ignorado(s) na checagem append-only.

RESULTADO: base limpa
```
